"""Production alert handlers for operator surfaces."""

from __future__ import annotations

import logging
from datetime import timedelta

from django.utils import timezone

from shopman.shop.adapters import alert as alert_adapter
from shopman.shop.directives import PRODUCTION_LATE_CHECK
from shopman.shop.production_config import ProductionConfig

logger = logging.getLogger(__name__)


def connect() -> None:
    """Connect production alert receivers to Craftsman lifecycle signals."""
    from shopman.craftsman.signals import production_changed

    production_changed.connect(
        on_production_changed,
        dispatch_uid="shopman.shop.handlers.production_alerts.on_production_changed",
        weak=False,
    )


def on_production_changed(sender, product_ref, date, action, work_order, **kwargs):
    """Create operator alerts for production lifecycle events."""
    ensure_late_check_scheduled()
    if action == "finished":
        maybe_create_low_yield_alert(work_order)


def ensure_late_check_scheduled() -> bool:
    """Arma o heartbeat ``production.late_check`` se não houver um vivo.

    Chamado em qualquer ``production_changed``: loja com produção ativa sempre
    tem o heartbeat armado — nenhuma tela precisa estar aberta para o operador
    ser avisado de atraso ou esquecimento. Cadence 0 desliga.
    """
    cadence = _alerts_config().late_check_cadence_minutes
    if cadence <= 0:
        return False

    from shopman.orderman.models import Directive

    if Directive.objects.filter(
        topic=PRODUCTION_LATE_CHECK, status__in=("queued", "running")
    ).exists():
        return False

    Directive.objects.create(
        topic=PRODUCTION_LATE_CHECK,
        payload={},
        available_at=timezone.now() + timedelta(minutes=cadence),
    )
    return True


class ProductionLateCheckHandler:
    """Heartbeat de alertas de produção. Topic: production.late_check

    Auto-reagendável: roda as varreduras (started além da janela, planned
    esquecida) e reenfileira a si mesmo no cadence do ``ProductionConfig``,
    zerando ``attempts`` — um heartbeat perpétuo nunca esgota retries. Falha
    transitória segue o retry/backoff padrão do worker; se o heartbeat morrer
    (max attempts), o próximo ``production_changed`` rearma.

    Cadence 0 = desligado: conclui sem reagendar. Duplicatas colapsam
    mantendo a mais antiga viva.
    """

    topic = PRODUCTION_LATE_CHECK

    def handle(self, *, message, ctx: dict) -> None:
        from shopman.orderman.models import Directive

        if (
            Directive.objects.filter(
                topic=self.topic, status__in=("queued", "running"), pk__lt=message.pk
            )
            .exclude(pk=message.pk)
            .exists()
        ):
            return  # duplicata — o worker marca done; a mais antiga segue viva

        cadence = _alerts_config().late_check_cadence_minutes
        if cadence <= 0:
            return  # desligado — o worker marca done; production_changed rearma

        late = check_late_started_orders()
        forgotten = check_forgotten_planned_orders()
        if late or forgotten:
            logger.info(
                "production.late_check: %d atrasada(s), %d esquecida(s)", late, forgotten
            )

        message.status = "queued"
        message.attempts = 0
        message.available_at = timezone.now() + timedelta(minutes=cadence)
        message.save(update_fields=["status", "attempts", "available_at", "updated_at"])


def maybe_create_low_yield_alert(work_order) -> bool:
    """Create a low-yield alert when finished quantity is below threshold."""
    if work_order.finished is None:
        return False

    base_qty = work_order.started_qty or work_order.quantity
    if not base_qty:
        return False

    yield_rate = work_order.finished / base_qty
    if yield_rate >= _alerts_config().low_yield_threshold_decimal:
        return False

    message = (
        f"Produção {work_order.ref} ({work_order.output_sku}) fechou com "
        f"yield de {int(yield_rate * 100)}%."
    )
    if _recent_exists("production_low_yield", work_order.ref):
        return False
    alert_adapter.create(
        "production_low_yield",
        "warning",
        message,
        order_ref=work_order.ref,
    )
    return True


def check_late_started_orders(*, selected_date=None) -> int:
    """Create alerts for started work orders beyond their target window."""
    from shopman.craftsman.models import WorkOrder

    qs = WorkOrder.objects.filter(status=WorkOrder.Status.STARTED).select_related("recipe")
    if selected_date is not None:
        qs = qs.filter(target_date=selected_date)

    created = 0
    now = timezone.now()
    for work_order in qs:
        started_at = work_order.started_at or work_order.created_at
        target_minutes = _target_minutes(work_order)
        if started_at > now - timedelta(minutes=target_minutes):
            continue
        if _recent_exists("production_late", work_order.ref):
            continue
        alert_adapter.create(
            "production_late",
            "warning",
            (
                f"Produção {work_order.ref} ({work_order.output_sku}) está há "
                f"{int((now - started_at).total_seconds() // 60)} min em andamento."
            ),
            order_ref=work_order.ref,
        )
        created += 1
    return created


def check_forgotten_planned_orders(*, today=None) -> int:
    """Create alerts for planned work orders whose target date has passed."""
    from shopman.craftsman.models import WorkOrder

    today = today or timezone.localdate()
    qs = (
        WorkOrder.objects.filter(status=WorkOrder.Status.PLANNED, target_date__lt=today)
        .select_related("recipe")
    )

    created = 0
    for work_order in qs:
        if _recent_exists("production_forgotten", work_order.ref):
            continue
        alert_adapter.create(
            "production_forgotten",
            "warning",
            (
                f"Produção {work_order.ref} ({work_order.output_sku}) planejada para "
                f"{work_order.target_date:%d/%m} nunca foi iniciada."
            ),
            order_ref=work_order.ref,
        )
        created += 1
    return created


def create_stock_short_alert(*, work_order_ref: str, output_sku: str, error: str) -> None:
    """Create an alert for a failed finish caused by stock/inventory shortage."""
    if _recent_exists("production_stock_short", work_order_ref):
        return
    alert_adapter.create(
        "production_stock_short",
        "error",
        f"Produção {work_order_ref} ({output_sku}) falhou por estoque insuficiente: {error}",
        order_ref=work_order_ref,
    )


def _target_minutes(work_order) -> int:
    try:
        raw = (work_order.recipe.meta or {}).get("max_started_minutes")
        if raw not in (None, ""):
            value = int(raw)
            if value > 0:
                return value
    except Exception:
        logger.debug("production_alerts.invalid_target_minutes work_order=%s", work_order.pk, exc_info=True)
    return _alerts_config().default_max_started_minutes


def _alerts_config() -> ProductionConfig.Alerts:
    try:
        return ProductionConfig.load().alerts
    except Exception:
        logger.debug("production_alerts.config_load_failed", exc_info=True)
        return ProductionConfig.Alerts()


def _recent_exists(alert_type: str, work_order_ref: str) -> bool:
    return alert_adapter.recent_exists(
        alert_type,
        timezone.now() - timedelta(hours=12),
        message_contains=work_order_ref,
    )
