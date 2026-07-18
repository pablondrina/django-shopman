"""Stock-back alerts ("Me avise quando disponível") — subscribe + notify.

Subscribe is open to anonymous shoppers (phone only) and logged-in customers.
The notify path is triggered by a stock-arrival receiver and is idempotent: it
only fires for *pending* subscriptions of a SKU that is *now* available, and
stamps ``notified_at`` so each subscription notifies exactly once.
"""

from __future__ import annotations

import logging

from django.utils import timezone

logger = logging.getLogger(__name__)


def has_pending(sku: str, *, alert_type: str = "") -> bool:
    """Cheap guard for the arrival/bake receivers (indexed exists())."""
    from shopman.storefront.models import StockAlertSubscription

    qs = StockAlertSubscription.objects.filter(sku=sku, notified_at__isnull=True)
    if alert_type:
        qs = qs.filter(alert_type=alert_type)
    return qs.exists()


def subscribed_skus(*, customer=None, phone: str = "") -> set[str]:
    """SKUs com inscrição PENDENTE para este viewer (cliente logado e/ou telefone).

    Usado pela projeção para persistir o estado do sino "Me avise" entre reloads.
    """
    from django.db.models import Q

    from shopman.storefront.models import StockAlertSubscription

    customer_ref = (getattr(customer, "ref", "") or "").strip()
    contact = (phone or getattr(customer, "phone", "") or "").strip()
    if not customer_ref and not contact:
        return set()

    cond = Q()
    if customer_ref:
        cond |= Q(customer_ref=customer_ref)
    if contact:
        cond |= Q(contact_phone=contact)
    return set(
        StockAlertSubscription.objects.filter(notified_at__isnull=True)
        .filter(cond)
        .values_list("sku", flat=True)
    )


def subscribe(
    sku: str,
    *,
    channel_ref: str = "web",
    customer=None,
    phone: str = "",
    alert_type: str = "",
):
    """Register a pending alert. Returns the subscription or None.

    Dedupes a pending alert per (sku, alert_type, target) — quem quer saber da
    reposição e da próxima fornada assina os dois, sem um sobrescrever o outro.
    ``customer`` is a Guestman Customer (or None for anonymous); ``phone`` is
    the anonymous contact.
    """
    from shopman.storefront.models import StockAlertSubscription

    alert_type = alert_type or StockAlertSubscription.AlertType.STOCK_BACK
    customer_ref = (getattr(customer, "ref", "") or "").strip()
    contact = (phone or getattr(customer, "phone", "") or "").strip()
    if not customer_ref and not contact:
        return None

    pending = StockAlertSubscription.objects.filter(
        sku=sku, alert_type=alert_type, notified_at__isnull=True
    )
    existing = (
        pending.filter(customer_ref=customer_ref).first()
        if customer_ref
        else pending.filter(contact_phone=contact).first()
    )
    if existing:
        return existing

    return StockAlertSubscription.objects.create(
        sku=sku,
        alert_type=alert_type,
        channel_ref=channel_ref or "web",
        customer_ref=customer_ref,
        contact_phone=contact,
    )


def notify_back_in_stock(sku: str) -> int:
    """Notify pending ``stock_back`` subscribers once ``sku`` is available again.

    Idempotent: marks ``notified_at`` only on a successful send, so a failed
    delivery is retried on the next stock arrival. Returns count notified.
    """
    from shopman.storefront.models import StockAlertSubscription

    return _notify(sku, alert_type=StockAlertSubscription.AlertType.STOCK_BACK)


def notify_bake_ready(sku: str) -> int:
    """Notify pending ``production_ready`` subscribers quando sai uma fornada.

    Mesmo gate de disponibilidade do ``stock_back``: fornada concluída que ainda
    não virou estoque vendável no canal não vira aviso, porque o aviso promete
    "pode pedir agora". Frustrar quem pediu para ser avisado é pior que calar.
    """
    from shopman.storefront.models import StockAlertSubscription

    return _notify(sku, alert_type=StockAlertSubscription.AlertType.PRODUCTION_READY)


#: Cada gatilho tem sua copy: "chegou" e "saiu do forno" prometem coisas diferentes.
_EVENT_BY_ALERT_TYPE = {
    "stock_back": "stock.arrived",
    "production_ready": "production.ready",
}


def _notify(sku: str, *, alert_type: str) -> int:
    from shopman.storefront.models import StockAlertSubscription
    from shopman.storefront.services import sku_state

    pending = list(
        StockAlertSubscription.objects.filter(
            sku=sku, alert_type=alert_type, notified_at__isnull=True
        )
    )
    if not pending:
        return 0

    product_name = _product_name(sku)
    event = _EVENT_BY_ALERT_TYPE.get(alert_type, "stock.arrived")
    notified = 0
    for sub in pending:
        try:
            state = sku_state.resolve(sku=sku, channel_ref=sub.channel_ref or "web")
        except Exception:
            logger.debug("stock_alerts: availability check failed sku=%s", sku, exc_info=True)
            continue
        if not state.can_add_to_cart:
            continue  # still unavailable for this channel — keep pending
        if _deliver(sub, product_name=product_name, event=event):
            sub.notified_at = timezone.now()
            sub.save(update_fields=["notified_at"])
            notified += 1
    if notified:
        logger.info(
            "stock_alerts: notified %s subscriber(s) for sku=%s type=%s",
            notified, sku, alert_type,
        )
    return notified


# ── private ──────────────────────────────────────────────────────────


def _product_name(sku: str) -> str:
    # Read through the shop projection (surface modules don't import kernels).
    from shopman.shop.projections import catalog_context

    product = catalog_context.get_product(sku)
    return product.name if product is not None else sku


def _deliver(sub, *, product_name: str, event: str = "stock.arrived") -> bool:
    """Send the subscription's notification via the channel's backend. True on success."""
    from shopman.shop.config import ChannelConfig
    from shopman.shop.notifications import notify
    from shopman.shop.services import storefront_links

    # subscribe() stores contact_phone = phone OR the customer's phone, so a
    # bare customer_ref without phone has no reachable recipient.
    recipient = (sub.contact_phone or "").strip()
    if not recipient:
        logger.debug("stock_alerts: no recipient for sub=%s", sub.pk)
        return False

    try:
        backend = (ChannelConfig.for_channel(sub.channel_ref or "web").notifications.backend) or "manychat"
    except Exception:
        logger.debug("stock_alerts: backend resolve failed, default manychat", exc_info=True)
        backend = "manychat"

    try:
        result = notify(
            event=event,
            recipient=recipient,
            context={
                "sku": sub.sku,
                "product_name": product_name,
                "product_url": storefront_links.product_url(sub.sku),
                # Placeholders do template compartilhado de stock.arrived: aqui
                # não há reserva nem prazo — cliente sem hold ("Me avise").
                "reserve_note": "",
                "deadline_note": "",
                "cta": "Garanta o seu:",
                "action_url": storefront_links.product_url(sub.sku),
            },
            backend=backend,
        )
        return bool(getattr(result, "success", False))
    except Exception:
        logger.warning("stock_alerts: delivery failed sub=%s sku=%s", sub.pk, sub.sku, exc_info=True)
        return False
