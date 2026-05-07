"""Operational observability helpers.

These helpers keep production signals boring and durable: structured log events
for machines, debounced OperatorAlert rows for humans.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from django.utils import timezone

logger = logging.getLogger("shopman.operational")


def operational_event(event: str, *, level: int = logging.INFO, **fields: Any) -> None:
    """Emit a structured operational event."""
    payload = {"event": event}
    payload.update(_compact(fields))
    logger.log(level, event, extra=payload)


def create_operator_alert(
    *,
    type: str,
    severity: str,
    message: str,
    order_ref: str = "",
    debounce_minutes: int = 15,
    dedupe_key: str = "",
    **fields: Any,
):
    """Create a debounced OperatorAlert and log the decision."""
    message = str(message or "").strip()
    if not message:
        return None

    dedupe_text = (dedupe_key or message[:120]).strip()
    cutoff = timezone.now() - timedelta(minutes=max(1, int(debounce_minutes)))

    try:
        from shopman.shop.adapters import alert as alert_adapter

        if alert_adapter.recent_exists(
            type,
            cutoff,
            message_contains=dedupe_text or None,
            order_ref=order_ref or None,
        ):
            operational_event(
                "operator_alert.debounced",
                level=logging.INFO,
                alert_type=type,
                severity=severity,
                order_ref=order_ref,
                dedupe_key=dedupe_text,
                **fields,
            )
            return None

        alert = alert_adapter.create(
            type,
            severity,
            _alert_message(message, dedupe_text=dedupe_text),
            order_ref=order_ref,
        )
    except Exception:
        logger.exception(
            "operator_alert.create_failed",
            extra={
                "event": "operator_alert.create_failed",
                "alert_type": type,
                "severity": severity,
                "order_ref": order_ref,
                **_compact(fields),
            },
        )
        return None

    operational_event(
        "operator_alert.created",
        level=logging.WARNING if severity != "critical" else logging.ERROR,
        alert_type=type,
        severity=severity,
        order_ref=order_ref,
        alert_id=getattr(alert, "pk", None),
        dedupe_key=dedupe_text,
        **fields,
    )
    return alert


def record_webhook_failure(
    *,
    provider: str,
    reason: str,
    status_code: int = 0,
    external_ref: str = "",
    order_ref: str = "",
    severity: str = "error",
    exc: BaseException | None = None,
    context: dict[str, Any] | None = None,
):
    """Log and alert an inbound webhook processing failure."""
    exception_class = exc.__class__.__name__ if exc else ""
    details = {
        "provider": provider,
        "reason": reason,
        "status_code": status_code,
        "external_ref": external_ref,
        "order_ref": order_ref,
        "exception_class": exception_class,
        "context": context or {},
    }
    operational_event("webhook.failed", level=logging.ERROR, **details)
    return create_operator_alert(
        type="webhook_failed",
        severity=severity,
        order_ref=order_ref,
        message=(
            f"Webhook {provider} falhou ({reason}). "
            f"external_ref={external_ref or '-'} status={status_code or '-'}"
        ),
        dedupe_key=f"{provider}:{reason}:{external_ref or order_ref or exception_class}",
        **_without_order_ref(details),
    )


def record_payment_reconciliation_failure(
    *,
    gateway: str,
    intent_ref: str = "",
    order_ref: str = "",
    code: str = "",
    context: dict[str, Any] | None = None,
    exc: BaseException | None = None,
):
    """Log and alert a payment reconciliation drift."""
    exception_class = exc.__class__.__name__ if exc else ""
    details = {
        "gateway": gateway,
        "intent_ref": intent_ref,
        "order_ref": order_ref,
        "code": code,
        "exception_class": exception_class,
        "context": context or {},
    }
    operational_event("payment_reconciliation.failed", level=logging.ERROR, **details)
    return create_operator_alert(
        type="payment_reconciliation_failed",
        severity="critical",
        order_ref=order_ref,
        message=(
            f"Reconciliação de pagamento falhou ({gateway}). "
            f"intent={intent_ref or '-'} code={code or exception_class or '-'}"
        ),
        dedupe_key=f"{gateway}:{intent_ref}:{code or exception_class}",
        **_without_order_ref(details),
    )


def _alert_message(message: str, *, dedupe_text: str) -> str:
    if not dedupe_text or dedupe_text in message:
        return message
    return f"{message}\n\nDedupe: {dedupe_text}"


def _compact(fields: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in fields.items() if value not in ("", None, {}, [])}


def _without_order_ref(fields: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in fields.items() if key != "order_ref"}


__all__ = [
    "create_operator_alert",
    "operational_event",
    "record_payment_reconciliation_failure",
    "record_webhook_failure",
]
