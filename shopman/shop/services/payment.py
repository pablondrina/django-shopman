"""
Payment orchestration service.

Core: PaymentService (create_intent, authorize, capture, refund, cancel)
Adapter: get_adapter("payment", method=...) → payment_efi / payment_stripe / payment_mock

The contract between this service and the adapters is defined in
shopman.adapters.payment_types: adapters return PaymentIntent / PaymentResult
dataclasses, not dicts. This service consumes them by attribute access.

order.data["payment"] contract: {intent_ref, method} are the core keys.
Display keys (qr_code, copy_paste, client_secret, expires_at, amount_q) are also stored.
Payman is the live canonical source when an intent exists. Embedded status is
only a compatibility/read fallback for imported or legacy orders without an
intent.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from shopman.shop.adapters import get_adapter
from shopman.shop.adapters.payment_types import PaymentIntent

logger = logging.getLogger(__name__)


def initiate(order) -> None:
    """
    Create a payment intent for the order.

    Resolves the adapter by payment method (from order.data["payment"]["method"]),
    calls adapter.create_intent(), then saves intent_ref and display data
    in order.data["payment"].

    SYNC — needs the intent/QR data to show to the client.
    """
    payment_data = order.data.get("payment", {})
    method = payment_data.get("method")

    if not method or method in ("cash", "external"):
        return

    # Idempotent: skip if intent already exists
    if payment_data.get("intent_ref"):
        return

    amount_q = order.total_q
    existing_intent = _existing_active_intent(order, method=method, amount_q=amount_q)
    if existing_intent:
        _persist_intent(order, payment_data=payment_data, method=method, amount_q=amount_q, intent=existing_intent)
        logger.info(
            "payment.initiate: reused existing %s intent %s for order %s",
            method,
            existing_intent.intent_ref,
            order.ref,
        )
        return

    adapter = get_adapter("payment", method=method)
    if not adapter:
        logger.warning("payment.initiate: no adapter for method=%s", method)
        _record_initiate_error(
            order,
            payment_data=payment_data,
            method=method,
            amount_q=amount_q,
            error="Método de pagamento indisponível.",
        )
        return

    idempotency_key = _ensure_payment_idempotency_key(
        order,
        payment_data=payment_data,
        method=method,
        amount_q=amount_q,
    )
    adapter_config = _adapter_config(order, method=method)
    adapter_config["idempotency_key"] = idempotency_key
    try:
        intent = adapter.create_intent(
            order_ref=order.ref,
            amount_q=amount_q,
            currency="BRL",
            method=method,
            metadata={"method": method, "idempotency_key": idempotency_key},
            **adapter_config,
        )
    except Exception as exc:
        logger.error(
            "payment.initiate: create_intent failed for order %s method=%s: %s",
            order.ref,
            method,
            exc,
        )
        existing_intent = _existing_active_intent(order, method=method, amount_q=amount_q)
        if existing_intent:
            _persist_intent(order, payment_data=payment_data, method=method, amount_q=amount_q, intent=existing_intent)
            logger.warning(
                "payment.initiate: recovered existing %s intent %s for order %s after adapter error: %s",
                method,
                existing_intent.intent_ref,
                order.ref,
                exc,
            )
            return
        _record_initiate_error(
            order,
            payment_data=payment_data,
            method=method,
            amount_q=amount_q,
            error=str(exc),
        )
        return

    _persist_intent(order, payment_data=payment_data, method=method, amount_q=amount_q, intent=intent)
    logger.info(
        "payment.initiate: %s intent %s for order %s",
        method, intent.intent_ref, order.ref,
    )


def _persist_intent(
    order,
    *,
    payment_data: dict,
    method: str,
    amount_q: int,
    intent: PaymentIntent,
) -> None:
    # Build payment data to save — intent_ref + method + display fields only.
    # Status is NOT stored here; Payman (PaymentService) is the canonical source.
    result = {
        **payment_data,
        "intent_ref": intent.intent_ref,
        "amount_q": amount_q,
        "method": method,
    }
    result.pop("error", None)

    # Extract QR/client_secret data for UI display
    if method == "pix":
        qr_data = _extract_qr_data(intent)
        result["qr_code"] = (
            qr_data.get("imagemQrcode")
            or qr_data.get("qr_image")
            or qr_data.get("qr_code")
            or qr_data.get("qrcode")
        )
        result["copy_paste"] = (
            qr_data.get("brcode")
            or qr_data.get("copy_paste")
            or qr_data.get("qrcode")
        )
        if intent.expires_at:
            result["expires_at"] = intent.expires_at.isoformat()
    elif method == "card":
        # Stripe Checkout (hosted): redirect URL the client clicks to pay.
        checkout_url = (intent.metadata or {}).get("checkout_url")
        if checkout_url:
            result["checkout_url"] = checkout_url

    order.data["payment"] = result
    order.save(update_fields=["data", "updated_at"])
    _ack_payment_failed_alerts(order)
    if intent.expires_at:
        _schedule_payment_timeout(order, intent)


def capture(order) -> None:
    """
    Capture a previously authorized payment via adapter.

    Reads intent_ref from order.data["payment"] and calls adapter.capture().
    Uses Payman (PaymentService) as idempotency source.

    SYNC — capture must succeed.
    """
    payment_data = (order.data or {}).get("payment", {})
    intent_ref = payment_data.get("intent_ref")

    if not intent_ref:
        return

    # Idempotency via Payman — skip if already captured
    if _payman_intent_captured(intent_ref):
        return

    method = payment_data.get("method", "pix")
    adapter = get_adapter("payment", method=method)
    if not adapter:
        return

    result = adapter.capture(intent_ref)
    if result.success:
        payment_data["transaction_id"] = result.transaction_id
        order.data["payment"] = payment_data
        order.save(update_fields=["data", "updated_at"])
        _ack_payment_failed_alerts(order)
        cancel_stale_intents(order, keep_intent_ref=intent_ref)

        logger.info("payment.capture: captured %s for order %s", intent_ref, order.ref)


def refund(order) -> None:
    """
    Refund payment for the order.

    Smart no-op: if order has no payment intent, does nothing.
    Uses Payman (PaymentService) as idempotency source.

    SYNC — direct refund.
    """
    payment_data = (order.data or {}).get("payment", {})
    intent_ref = payment_data.get("intent_ref")

    if not intent_ref:
        # Smart no-op: no payment to refund (cash, external, etc.)
        return

    refundable_q = _payman_refundable_amount(intent_ref)

    # Idempotency via Payman — skip only when the captured balance is fully
    # refunded. Payman status REFUNDED can also mean a partial refund.
    if refundable_q is not None and refundable_q <= 0:
        return
    if refundable_q is None and _payman_intent_refunded(intent_ref):
        return

    method = payment_data.get("method", "pix")
    adapter = get_adapter("payment", method=method)
    if not adapter:
        return

    try:
        result = adapter.refund(
            intent_ref,
            amount_q=refundable_q,
            reason="order_cancelled",
        )
        if result.success:
            logger.info("payment.refund: refunded %s for order %s", intent_ref, order.ref)
    except Exception as exc:
        logger.warning("payment.refund: failed for order %s: %s", order.ref, exc)


def cancel(order, *, reason: str = "order_cancelled") -> None:
    """Cancel an unpaid payment intent.

    Captured payments are not cancelled here; those still go through
    ``refund()`` so Payman remains the canonical payment state.
    """
    payment_data = (order.data or {}).get("payment", {})
    intent_ref = payment_data.get("intent_ref")
    if not intent_ref:
        return

    status = (get_payment_status(order) or "").lower()
    if status in {"captured", "paid", "refunded", "cancelled", "unknown"}:
        return

    method = payment_data.get("method", "pix")
    adapter = get_adapter("payment", method=method)
    if not adapter or not hasattr(adapter, "cancel"):
        return

    try:
        result = adapter.cancel(intent_ref, reason=reason)
        if result.success:
            logger.info("payment.cancel: cancelled %s for order %s", intent_ref, order.ref)
    except Exception as exc:
        logger.warning("payment.cancel: failed for order %s: %s", order.ref, exc)


# ── facades ──

_CANCELLABLE_STATUSES = {"new", "confirmed"}
_PAID_STATUSES = {"captured", "paid"}
_UNCERTAIN_STATUSES = {"unknown"}


def cancel_stale_intents(order, *, keep_intent_ref: str) -> int:
    """Cancel same-order pending/authorized intents once one intent wins."""
    if not keep_intent_ref:
        return 0
    try:
        from shopman.payman import PaymentService

        count = 0
        for intent in PaymentService.get_by_order(order.ref):
            if intent.ref == keep_intent_ref:
                continue
            if intent.status not in {"pending", "authorized"}:
                continue
            try:
                PaymentService.cancel(intent.ref, reason="superseded_by_captured_payment")
                count += 1
            except Exception:
                logger.warning(
                    "payment.cancel_stale_intent_failed order=%s intent=%s",
                    order.ref,
                    intent.ref,
                    exc_info=True,
                )
        return count
    except Exception:
        logger.debug("payment.cancel_stale_intents_failed order=%s", order.ref, exc_info=True)
        return 0


def get_payment_status(order) -> str | None:
    """
    Retorna o status canônico de pagamento via Payman.

    Consulta PaymentService pelo intent_ref. Retorna None para pedidos sem
    intent/status (cash, external). Se existe intent mas Payman não responde,
    retorna ``"unknown"`` para impedir decisões operacionais fail-open.
    """
    payment_data = (order.data or {}).get("payment") or {}
    embedded_status = _embedded_payment_status(payment_data)
    intent_ref = payment_data.get("intent_ref")
    if not intent_ref:
        return embedded_status
    try:
        from shopman.payman import PaymentService
        intent = PaymentService.get(intent_ref)
        return intent.status
    except Exception:
        logger.warning(
            "get_payment_status: unable to read intent for order %s intent=%s",
            order.ref,
            intent_ref,
            exc_info=True,
        )
        return "unknown"


def captured_balance_q(order) -> int | None:
    """Return captured minus refunded amount for the order intent, if readable."""
    payment_data = (order.data or {}).get("payment") or {}
    intent_ref = payment_data.get("intent_ref")
    if not intent_ref:
        return None
    return _payman_captured_balance_q(intent_ref)


def has_sufficient_captured_payment(order) -> bool:
    """True when Payman shows captured funds still covering the order total."""
    payment_data = (order.data or {}).get("payment") or {}
    status = (get_payment_status(order) or "").lower()
    if status not in _PAID_STATUSES | {"refunded"}:
        return False

    intent_ref = payment_data.get("intent_ref")
    if not intent_ref:
        # Compatibility for imported/legacy orders without Payman intent.
        return status in _PAID_STATUSES

    balance_q = _payman_captured_balance_q(intent_ref)
    if balance_q is None:
        return False
    return balance_q >= int(getattr(order, "total_q", 0) or 0)


def can_cancel(order) -> bool:
    """
    True se o pedido pode ser cancelado pelo cliente.

    Requer: status in {new, confirmed} e pagamento comprovadamente não capturado.
    Estados incertos bloqueiam cancelamento para não cancelar um pedido que pode
    já estar pago.
    """
    if order.status not in _CANCELLABLE_STATUSES:
        return False
    status = (get_payment_status(order) or "").lower()
    if status in _UNCERTAIN_STATUSES or has_sufficient_captured_payment(order):
        return False
    return True


def mock_confirm(order) -> bool:
    """DEV helper: simulate capture for local payment testing.

    Payman remains the canonical status source. This helper simulates the
    gateway side only: authorize/capture the intent, record display metadata,
    and dispatch the same paid lifecycle hook used by production webhooks.
    It must not move ``Order.status`` directly.
    """
    current_status = (get_payment_status(order) or "").lower()
    if current_status == "captured":
        return False
    if current_status == "unknown":
        logger.warning("mock_confirm: refusing unknown payment state for order %s", order.ref)
        return False

    from shopman.payman import PaymentError, PaymentService

    payment_data = dict((order.data or {}).get("payment", {}))
    intent_ref = payment_data.get("intent_ref")
    if not intent_ref:
        logger.warning("mock_confirm: refusing order %s without payment intent", order.ref)
        return False

    try:
        intent = PaymentService.get(intent_ref)
        if intent.status == "pending":
            PaymentService.authorize(intent_ref, gateway_id=f"mock_confirm_{intent_ref}")
            intent = PaymentService.get(intent_ref)
        if intent.status in ("pending", "authorized"):
            PaymentService.capture(intent_ref)
    except PaymentError as exc:
        logger.warning(
            "mock_confirm: payment transition failed: %s",
            exc,
            extra={"intent_ref": intent_ref, "order_ref": order.ref},
        )
        return False

    payment_data["captured_at"] = timezone.now().isoformat()
    data = dict(order.data or {})
    data["payment"] = payment_data
    order.data = data
    order.save(update_fields=["data", "updated_at"])

    method = payment_data.get("method", "pix")
    order.emit_event(
        event_type="payment.captured",
        actor="mock_payment",
        payload={"method": method, "amount_q": payment_data.get("amount_q", order.total_q)},
    )

    from shopman.shop.lifecycle import dispatch

    dispatch(order, "on_paid")

    return True


# ── helpers ──


def _extract_qr_data(intent: PaymentIntent) -> dict:
    """Extract QR code data from intent metadata or client_secret."""
    if intent.metadata:
        return intent.metadata

    if intent.client_secret:
        try:
            return json.loads(intent.client_secret)
        except (json.JSONDecodeError, TypeError):
            pass

    return {}


def _ensure_payment_idempotency_key(
    order,
    *,
    payment_data: dict,
    method: str,
    amount_q: int,
) -> str:
    """Return a stable key for this payment attempt and persist it when possible."""
    existing = str(payment_data.get("idempotency_key") or "").strip()
    if existing:
        return existing

    key = f"order-payment:{order.ref}:{method}:{amount_q}:{uuid.uuid4().hex[:16]}"
    payment_data["idempotency_key"] = key
    data = dict(order.data or {})
    data["payment"] = payment_data
    order.data = data
    try:
        order.save(update_fields=["data", "updated_at"])
    except Exception:
        logger.warning("payment.idempotency_key_persist_failed order=%s", order.ref, exc_info=True)
    return key


def _existing_active_intent(order, *, method: str, amount_q: int) -> PaymentIntent | None:
    """Return a reusable Payman intent for this order/method/amount, if any."""
    try:
        from shopman.payman import PaymentService

        now = timezone.now()
        intents = (
            PaymentService.get_by_order(order.ref)
            .filter(method=method, amount_q=amount_q)
            .exclude(status__in={"failed", "cancelled", "refunded"})
            .order_by("-created_at", "-id")
        )
        candidates = list(intents)
        for intent in candidates:
            if intent.status == "captured":
                return _payment_intent_from_payman(intent)
        for intent in candidates:
            if intent.expires_at and intent.expires_at <= now:
                continue
            return _payment_intent_from_payman(intent)
    except Exception:
        logger.debug("payment.existing_intent_lookup_failed order=%s", order.ref, exc_info=True)
    return None


def _payment_intent_from_payman(intent) -> PaymentIntent:
    gateway_data = dict(intent.gateway_data or {})
    client_secret = gateway_data.get("client_secret")
    metadata = dict(gateway_data)
    if client_secret:
        try:
            parsed = json.loads(client_secret)
        except (TypeError, json.JSONDecodeError):
            parsed = {}
        if isinstance(parsed, dict):
            metadata.update(parsed)

    return PaymentIntent(
        intent_ref=intent.ref,
        status=intent.status,
        amount_q=intent.amount_q,
        currency=intent.currency,
        client_secret=client_secret,
        expires_at=intent.expires_at,
        gateway_id=intent.gateway_id,
        metadata=metadata,
    )


def _record_initiate_error(
    order,
    *,
    payment_data: dict,
    method: str,
    amount_q: int,
    error: str,
) -> None:
    error_message = str(error or "Falha ao gerar pagamento.")[:200]
    order.data["payment"] = {
        **payment_data,
        "method": method,
        "amount_q": amount_q,
        "error": error_message,
    }
    order.save(update_fields=["data", "updated_at"])
    _create_payment_failed_alert(order, method=method, error=error_message)
    _notify_payment_failed(order)


def _create_payment_failed_alert(order, *, method: str, error: str) -> None:
    try:
        from shopman.shop.adapters import alert as alert_adapter

        debounce_cutoff = timezone.now() - timedelta(minutes=15)
        if alert_adapter.recent_exists(
            "payment_failed",
            debounce_cutoff,
            order_ref=order.ref,
        ):
            return
        alert_adapter.create(
            "payment_failed",
            "error",
            (
                f"Falha ao gerar pagamento {method.upper()} do pedido {order.ref}. "
                "Cliente mantido na tela de pagamento para tentar novamente. "
                f"Erro: {error}"
            ),
            order_ref=order.ref,
        )
    except Exception:
        logger.warning("payment_failed_alert_create_failed order=%s", order.ref, exc_info=True)


def _notify_payment_failed(order) -> None:
    try:
        from shopman.shop.services import notification

        notification.send(order, "payment_failed")
    except Exception:
        logger.warning("payment_failed_notification_queue_failed order=%s", order.ref, exc_info=True)


def _ack_payment_failed_alerts(order) -> None:
    try:
        from shopman.shop.adapters import alert as alert_adapter

        alert_adapter.acknowledge("payment_failed", order_ref=order.ref)
    except Exception:
        logger.debug("payment_failed_alert_ack_failed order=%s", order.ref, exc_info=True)


def _embedded_payment_status(payment_data: dict) -> str | None:
    status = str(payment_data.get("status") or "").strip().lower()
    return status or None


def _schedule_payment_timeout(order, intent: PaymentIntent) -> None:
    """Queue cancellation for unpaid digital payments at the gateway deadline."""
    try:
        from shopman.orderman.models import Directive

        from shopman.shop.directives import PAYMENT_TIMEOUT

        dedupe_key = f"{PAYMENT_TIMEOUT}:{order.ref}:{intent.intent_ref}"
        payload = {
            "order_ref": order.ref,
            "intent_ref": intent.intent_ref,
            "expires_at": intent.expires_at.isoformat(),
        }
        existing = Directive.objects.filter(
            topic=PAYMENT_TIMEOUT,
            dedupe_key=dedupe_key,
            status__in=[Directive.Status.QUEUED, Directive.Status.RUNNING],
        ).first()
        if existing:
            existing.payload = payload
            existing.available_at = intent.expires_at
            existing.save(update_fields=["payload", "available_at", "updated_at"])
            return

        Directive.objects.create(
            topic=PAYMENT_TIMEOUT,
            payload=payload,
            available_at=intent.expires_at,
            dedupe_key=dedupe_key,
        )
    except Exception:
        logger.warning("payment.timeout_schedule_failed order=%s", order.ref, exc_info=True)


def _adapter_config(order, *, method: str) -> dict:
    try:
        from shopman.shop.config import ChannelConfig

        cfg = ChannelConfig.for_channel(order.channel_ref)
    except Exception:
        logger.debug("payment.adapter_config_failed order=%s", order.ref, exc_info=True)
        return {}

    config: dict = {}
    if method == "pix":
        config["pix_timeout_minutes"] = cfg.payment.timeout_minutes
        if getattr(settings, "SHOPMAN_MOCK_PIX_AUTO_CONFIRM", False):
            config["mock_pix_auto_confirm"] = True
            config["mock_pix_confirm_delay_seconds"] = getattr(
                settings,
                "SHOPMAN_MOCK_PIX_CONFIRM_DELAY_SECONDS",
                10,
            )
    if method == "card":
        config["capture_method"] = "manual"
    return config


def _payman_intent_captured(intent_ref: str) -> bool:
    """Return True if the Payman intent is already captured. Fails silently."""
    try:
        from shopman.payman import PaymentService
        intent = PaymentService.get(intent_ref)
        return intent.status in ("captured", "paid", "refunded")
    except Exception:
        logger.exception("payment._payman_intent_captured: error checking intent_ref=%s", intent_ref)
        return False


def _payman_captured_balance_q(intent_ref: str) -> int | None:
    """Return captured minus refunded amount for a Payman intent."""
    try:
        from shopman.payman import PaymentService

        return PaymentService.captured_total(intent_ref) - PaymentService.refunded_total(intent_ref)
    except Exception:
        logger.exception("payment._payman_captured_balance_q: error checking intent_ref=%s", intent_ref)
        return None


def _payman_refundable_amount(intent_ref: str) -> int | None:
    """Return remaining refundable captured balance, or None if unreadable."""
    balance_q = _payman_captured_balance_q(intent_ref)
    if balance_q is None:
        return None
    return max(0, balance_q)


def _payman_intent_refunded(intent_ref: str) -> bool:
    """Return True only if the Payman intent is fully refunded."""
    refundable_q = _payman_refundable_amount(intent_ref)
    if refundable_q is None:
        return False
    return refundable_q <= 0
