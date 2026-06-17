from __future__ import annotations

import logging
from collections import Counter

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Diagnostica um pedido remoto lendo fontes canonicas, sem alterar estado."

    def add_arguments(self, parser):
        parser.add_argument("ref", help="Order.ref do pedido remoto.")

    def handle(self, *args, **options):
        from shopman.orderman.models import Directive, Order

        from shopman.shop.projections.channel_policy import resolve_channel_policy
        from shopman.shop.services import payment_status
        from shopman.shop.services.conversation import build_order_conversation

        ref = str(options["ref"]).strip()
        try:
            order = Order.objects.get(ref=ref)
        except Order.DoesNotExist as exc:
            raise CommandError(f"Pedido nao encontrado: {ref}") from exc

        data = order.data if isinstance(order.data, dict) else {}
        payment = data.get("payment") if isinstance(data.get("payment"), dict) else {}
        intent_ref = payment.get("intent_ref") or ""
        method = str(payment.get("method") or "").lower() or "none"
        payment_state = str(payment_status.get_payment_status(order) or payment.get("status") or "unknown")
        has_captured = payment_status.has_sufficient_captured_payment(order)
        channel_policy = resolve_channel_policy(order.channel_ref)
        directives = list(Directive.objects.filter(payload__order_ref=order.ref).order_by("id"))
        directive_counts = Counter(str(d.status) for d in directives)
        failed_directives = [d for d in directives if str(d.status) == "failed"]
        queued_directives = [d for d in directives if str(d.status) in {"queued", "running"}]
        hold_summary = _hold_summary(data.get("hold_ids") or [])

        self.stdout.write(
            "result=OK "
            f"order={order.ref} status={order.status} channel={order.channel_ref} "
            f"created_at={order.created_at.isoformat()}"
        )
        self.stdout.write(
            "result=OK "
            f"channel_policy can_cancel={channel_policy.can_cancel} "
            f"requires_payment_gate={channel_policy.requires_payment_gate} "
            f"supports_access_link={channel_policy.supports_access_link}"
        )
        payment_result = "OK"
        if method in {"pix", "card"} and not has_captured and order.status in {"confirmed", "new"}:
            payment_result = "WARN"
        self.stdout.write(
            f"result={payment_result} payment method={method} state={payment_state} "
            f"intent_ref={intent_ref or '-'} captured={has_captured}"
        )

        directive_result = "OK"
        if failed_directives:
            directive_result = "FAIL"
        elif queued_directives:
            directive_result = "WARN"
        self.stdout.write(
            f"result={directive_result} directives total={len(directives)} "
            f"queued={directive_counts.get('queued', 0)} running={directive_counts.get('running', 0)} "
            f"failed={directive_counts.get('failed', 0)} done={directive_counts.get('done', 0)}"
        )
        if failed_directives:
            refs = ",".join(f"{d.pk}:{d.topic}:{d.error_code or '-'}" for d in failed_directives[:5])
            self.stdout.write(f"result=FAIL directive_failed refs={refs}")

        self.stdout.write(
            f"result={hold_summary['result']} holds total={hold_summary['total']} "
            f"expired={hold_summary['expired']} missing={hold_summary['missing']}"
        )

        try:
            conversation = build_order_conversation(order, channel_ref=order.channel_ref)
            action_ref = next((action.ref for action in conversation.actions if action.enabled), "-")
            self.stdout.write(
                "result=OK "
                f"conversation source={conversation.source_projection} state={conversation.state} "
                f"action={action_ref} deadline_at={conversation.deadline_at or '-'}"
            )
        except Exception as exc:
            logger.debug("diagnose_remote_order.handle degraded; using fallback", exc_info=True)
            self.stdout.write(f"result=WARN conversation error={str(exc)[:160]}")

        for recommendation in _recommendations(
            order=order,
            method=method,
            has_captured=has_captured,
            failed_directives=failed_directives,
            queued_directives=queued_directives,
            hold_summary=hold_summary,
        ):
            self.stdout.write(f"recommendation={recommendation}")


def _hold_summary(hold_ids: list) -> dict[str, int | str]:
    if not isinstance(hold_ids, (list, tuple, set)):
        hold_ids = [hold_ids]
    if not hold_ids:
        return {"result": "OK", "total": 0, "expired": 0, "missing": 0}
    try:
        from shopman.stockman.models import Hold
    except Exception:
        logger.debug("diagnose_remote_order._hold_summary degraded; using fallback", exc_info=True)
        return {"result": "WARN", "total": len(hold_ids), "expired": 0, "missing": len(hold_ids)}

    holds = list(Hold.objects.filter(id__in=hold_ids))
    now = timezone.now()
    expired = sum(1 for hold in holds if getattr(hold, "expires_at", None) and hold.expires_at <= now)
    missing = max(len(hold_ids) - len(holds), 0)
    result = "FAIL" if expired or missing else "OK"
    return {"result": result, "total": len(holds), "expired": expired, "missing": missing}


def _recommendations(
    *,
    order,
    method: str,
    has_captured: bool,
    failed_directives: list,
    queued_directives: list,
    hold_summary: dict,
) -> list[str]:
    recommendations = []
    if method in {"pix", "card"} and not has_captured and order.status in {"new", "confirmed"}:
        recommendations.append("python manage.py reconcile_payments --since=4h --dry-run")
    if failed_directives or queued_directives:
        recommendations.append("python manage.py process_directives --limit=50")
    if hold_summary.get("expired") or hold_summary.get("missing"):
        recommendations.append("python manage.py release_expired_holds --dry-run")
    if not recommendations:
        recommendations.append("acompanhar tracking/payment projections; nenhuma correcao automatica indicada")
    return recommendations
