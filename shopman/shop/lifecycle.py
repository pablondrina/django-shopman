"""
Declarative dispatch — lifecycle coordination for orders.

Signal `order_changed` → dispatch(order, phase) → services.

dispatch() reads ChannelConfig and calls the appropriate services based on
payment.timing, fulfillment.timing, confirmation.mode, and stock.check_on_commit.

No lifecycle classes — behavior is purely configuration-driven.

Timing × Phase table:
    payment.timing:
        "external"    → no payment.initiate (cash/marketplace)
        "at_commit"   → payment.initiate on commit
        "post_commit" → payment.initiate on confirmed (default)

    fulfillment.timing:
        "at_commit"   → fulfillment.create on commit
        "post_commit" → fulfillment.create on ready (default)
        "external"    → no fulfillment.create

    stock.check_on_commit:
        True  → per-item availability check before stock.hold (POS, marketplace)
        False → skip check (web storefront validates during checkout)

    confirmation.mode:
        "immediate"    → auto-confirm on commit
        "auto_confirm" → auto-confirm after timeout if operator doesn't cancel
        "auto_cancel"  → auto-CANCEL after timeout if operator doesn't confirm
        "manual"       → wait for operator, no timeout
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.utils import timezone
from shopman.orderman.models import Directive, Order

from shopman.shop.config import ChannelConfig
from shopman.shop.services import (
    availability,
    customer,
    fiscal,
    fulfillment,
    loyalty,
    notification,
    payment,
    stock,
)
from shopman.shop.services.business_calendar import next_operational_deadline
from shopman.shop.services.order_helpers import get_commitment_date

logger = logging.getLogger(__name__)


def has_availability_approval(order) -> bool:
    """Return True when the order carries an explicit positive availability decision."""
    decision = (order.data or {}).get("availability_decision", {})
    if decision.get("approved") is not True:
        return False
    if "decisions" in decision:
        return True
    return bool(decision.get("items"))


def ensure_confirmable(order) -> None:
    """Enforce the operational precondition for moving an order into CONFIRMED.

    This checks availability only. Payment capture is guarded separately by
    :func:`ensure_payment_captured` on every path that can move an order into
    ``CONFIRMED``.
    """
    from shopman.orderman.exceptions import InvalidTransition

    if has_availability_approval(order):
        return

    try:
        config = ChannelConfig.for_channel(order.channel_ref)
        if config.payment.timing == "external":
            return
    except Exception:
        # Config lookup failed — fall through to strict path (require approval).
        logger.warning("ensure_confirmable: config lookup failed for channel=%s", order.channel_ref)

    raise InvalidTransition(
        code="availability_not_approved",
        message="Pedido não pode ser confirmado sem decisão positiva de disponibilidade",
        context={
            "order_ref": order.ref,
            "status": order.status,
            "availability_decision": (order.data or {}).get("availability_decision"),
        },
    )


# Payment methods que NÃO passam por captura de intent (Payman).
# Canonical refs: cash, credit, debit, external.
# "pix" e "card" NÃO estão aqui — esses precisam de intent captured.
_OFFLINE_PAYMENT_METHODS = {
    "external",
    "cash", "credit", "debit",
    "",
}
_UPFRONT_DIGITAL_PAYMENT_METHODS = {"pix", "card"}
_ACCEPTED_PAYMENT_STATUSES = {"captured", "paid"}


def ensure_payment_captured(order) -> None:
    """Raise InvalidTransition when an upfront Shopman payment intent is not captured.

    Guard is skipped for channels whose ``payment.timing`` is ``external``
    (marketplace, POS) — those payments are handled outside Shopman and the
    order payload's ``payment.method`` string is not a Payman intent.
    """
    from shopman.orderman.exceptions import InvalidTransition

    payment = (order.data or {}).get("payment") or {}

    # External timing channels (iFood, POS) manage payment outside Shopman;
    # the guard doesn't apply.
    try:
        config = ChannelConfig.for_channel(order.channel_ref)
        if config.payment.timing == "external":
            return
    except Exception:
        # Config lookup failed — fall through to strict path (check payment).
        logger.warning("ensure_payment_captured: config lookup failed for channel=%s", order.channel_ref)
        config = ChannelConfig()

    requires_upfront_payment = _requires_captured_payment_before_confirmation(order, config)
    if not requires_upfront_payment:
        return

    method = _payment_method(order, config)
    if method in _OFFLINE_PAYMENT_METHODS:
        return

    intent_ref = payment.get("intent_ref")
    if _payment_is_captured(order):
        return

    raise InvalidTransition(
        code="payment_not_captured",
        message="Pagamento ainda não foi confirmado. Aguarde a captura antes de confirmar o pedido.",
        context={
            "order_ref": order.ref,
            "status": order.status,
            "payment_method": method,
            "payment_status": (payment.get("status") or None),
            "intent_ref": intent_ref,
        },
    )


def dispatch(order, phase: str) -> None:
    """Resolve ChannelConfig and call services for the given phase.

    Exceptions propagate — an order stuck in an inconsistent state is worse
    than a visible error. Callers (signal handlers) are responsible for
    surfacing failures appropriately.
    """
    config = ChannelConfig.for_channel(order.channel_ref)

    handler = _PHASE_HANDLERS.get(phase)
    if handler is None:
        logger.warning("dispatch: unknown phase %s for order %s", phase, order.ref)
        return
    handler(order, config)


# ── Phase handlers ──


def _on_commit(order, config: ChannelConfig) -> None:
    """Order created: ensure customer, check availability, hold stock,
    redeem loyalty, handle confirmation."""
    customer.ensure(order)

    if config.stock.check_on_commit:
        if not _check_availability(order, config):
            return  # order cancelled

    stock.hold(order)

    if config.stock.check_on_commit and (order.data or {}).get("hold_ids"):
        if not _verify_holds(order):
            return  # order cancelled

    decisions = (order.data or {}).get("availability_decision", {}).get("decisions")
    if not decisions:
        decisions = [
            {
                "approved": True,
                "sku": item.get("sku"),
                "requested_qty": item.get("qty"),
                "available_qty": item.get("qty"),
                "reason_code": None,
                "is_paused": False,
                "is_planned": False,
                "target_date": get_commitment_date(order).isoformat() if get_commitment_date(order) else None,
                "failed_sku": None,
                "source": "stock.hold",
            }
            for item in order.snapshot.get("items", [])
        ]
    _record_availability_decision(
        order,
        approved=True,
        source="stock.check_on_commit" if config.stock.check_on_commit else "stock.hold",
        decisions=decisions,
    )

    loyalty.redeem(order)

    if _should_initiate_payment_on_commit(order, config):
        payment.initiate(order)
    if config.fulfillment.timing == "at_commit":
        fulfillment.create(order)

    # Fire "order_received" for non-immediate modes: o cliente fica esperando
    # (auto_confirm 5min, manual indefinido) — sem esse aviso, silêncio total.
    # Em `immediate`, o _on_confirmed dispara `order_confirmed` logo em seguida,
    # então duplicar aqui seria ruído.
    if config.confirmation.mode != "immediate":
        notification.send(order, "order_received")

    _handle_confirmation(order, config)


def _on_confirmed(order, config: ChannelConfig) -> None:
    """Order confirmed: dispatch KDS tickets, initiate payment (if post_commit),
    fulfill stock (if no digital payment), notify."""

    if _requires_payment_before_physical_work(order, config) and not _payment_is_captured(order):
        if _payment_method(order, config) == "card" and _payment_is_authorized(order):
            payment.capture(order)
        elif config.payment.timing == "post_commit":
            payment.initiate(order)

        if not _payment_is_captured(order):
            notification.send(order, "payment_requested")
            return

    physical_work_dispatched = _dispatch_physical_work(order)

    if config.payment.timing == "external" and config.payment.method != "external":
        # Counter payment — no digital payment step, fulfill immediately
        stock.fulfill(order)
    elif _payment_is_captured(order):
        # Payment may have arrived while the order was still NEW. In that case
        # the paid hook deliberately waited for operational confirmation.
        stock.fulfill(order)
    notification.send(order, "order_confirmed")
    if physical_work_dispatched:
        _mark_preparing_after_physical_work_dispatch(order)


def _on_paid(order, config: ChannelConfig) -> None:
    """Payment confirmed (via webhook).

    Handles race condition: if order was already cancelled,
    refund and alert instead.
    """
    if order.status == Order.Status.CANCELLED:
        payment.refund(order)
        _create_alert(order, "payment_after_cancel")
        return
    if order.status == Order.Status.NEW:
        _create_alert(order, "payment_awaiting_confirmation")
        if config.confirmation.mode in ("auto_confirm", "auto_cancel"):
            _schedule_confirmation_timeout(
                order,
                config,
                action="confirm" if config.confirmation.mode == "auto_confirm" else "cancel",
                source="payment_confirmed",
            )
        notification.send(order, "payment_confirmed")
        return
    physical_work_dispatched = False
    if order.status == Order.Status.CONFIRMED:
        physical_work_dispatched = _dispatch_physical_work(order)
    stock.fulfill(order)
    notification.send(order, "payment_confirmed")
    if physical_work_dispatched:
        _mark_preparing_after_physical_work_dispatch(order)


def _on_preparing(order, config: ChannelConfig) -> None:
    """Order in preparation: notify."""
    notification.send(order, "order_preparing")


def _on_ready(order, config: ChannelConfig) -> None:
    """Order ready: create fulfillment (if post_commit) + notify."""
    if config.fulfillment.timing == "post_commit":
        fulfillment.create(order)
    notification.send(order, "order_ready")


def _on_dispatched(order, config: ChannelConfig) -> None:
    """Order dispatched: notify."""
    notification.send(order, "order_dispatched")


def _on_delivered(order, config: ChannelConfig) -> None:
    """Order delivered: notify, then close the internal post-handoff work."""
    notification.send(order, "order_delivered")
    _complete_after_handoff(order)


def _on_completed(order, config: ChannelConfig) -> None:
    """Order completed: loyalty points + fiscal emission."""
    loyalty.earn(order)
    fiscal.emit(order)


def _on_cancelled(order, config: ChannelConfig) -> None:
    """Order cancelled: cancel KDS tickets (if enabled) + release stock + refund + notify."""
    try:
        from shopman.shop.services import kds
        kds.cancel_tickets(order)
    except ImportError:
        pass
    stock.release(order)
    payment.refund(order)
    notification.send(order, "order_cancelled")


def _on_returned(order, config: ChannelConfig) -> None:
    """Order returned: revert stock + refund + cancel fiscal + notify."""
    stock.revert(order)
    payment.refund(order)
    fiscal.cancel(order)
    notification.send(order, "order_returned")


_PHASE_HANDLERS = {
    "on_commit": _on_commit,
    "on_confirmed": _on_confirmed,
    "on_paid": _on_paid,
    "on_preparing": _on_preparing,
    "on_ready": _on_ready,
    "on_dispatched": _on_dispatched,
    "on_delivered": _on_delivered,
    "on_completed": _on_completed,
    "on_cancelled": _on_cancelled,
    "on_returned": _on_returned,
}


def _complete_after_handoff(order) -> None:
    """Move delivered orders to completed so fiscal/loyalty closure is automatic."""
    if getattr(order, "status", "") != Order.Status.DELIVERED:
        return
    if not order.can_transition_to(Order.Status.COMPLETED):
        logger.warning("order_auto_complete_blocked order=%s status=%s", order.ref, order.status)
        return
    order.transition_status(Order.Status.COMPLETED, actor="system:post_handoff")


# ── Helpers ──


def _handle_confirmation(order, config: ChannelConfig) -> None:
    """Route confirmation by mode.

    - ``immediate``    → transition NEW → CONFIRMED synchronously.
    - ``auto_confirm`` → schedule a ``confirmation.timeout`` directive that
      auto-confirms if the operator does not explicitly cancel within the
      timeout. The operator can still cancel in the window.
    - ``auto_cancel``  → schedule a ``confirmation.timeout`` directive that
      auto-CANCELS if the operator does not explicitly confirm within the
      timeout. The operator can confirm in the window; if they do, the
      directive fires and noops (status != NEW).
    - ``manual``       → no directive; status stays NEW until the operator
      explicitly confirms or cancels. No timeout.
    """
    mode = config.confirmation.mode

    if mode == "immediate":
        ensure_confirmable(order)
        from shopman.orderman.exceptions import InvalidTransition

        try:
            ensure_payment_captured(order)
        except InvalidTransition as exc:
            if getattr(exc, "code", "") == "payment_not_captured":
                _create_alert(order, "payment_awaiting_confirmation")
                notification.send(order, "order_received")
                return
            raise
        order.transition_status(Order.Status.CONFIRMED, actor="auto_confirm")
        return

    if mode in ("auto_confirm", "auto_cancel"):
        action = "confirm" if mode == "auto_confirm" else "cancel"
        if _requires_captured_payment_before_confirmation(order, config) and not _payment_is_captured(order):
            return
        _schedule_confirmation_timeout(order, config, action=action, source="order_commit")
        return

    # manual: aguarda operador, mas agenda alerta de "stale" se configurado.
    stale_minutes = getattr(config.confirmation, "stale_new_alert_minutes", 0)
    if stale_minutes and stale_minutes > 0:
        alert_at = timezone.now() + timedelta(minutes=stale_minutes)
        Directive.objects.create(
            topic="order.stale_new_alert",
            payload={
                "order_ref": order.ref,
                "alert_at": alert_at.isoformat(),
            },
            available_at=alert_at,
        )


def _payment_is_captured(order) -> bool:
    """Return True when Payman shows enough captured balance for the order."""
    try:
        return payment.has_sufficient_captured_payment(order) is True
    except Exception:
        logger.warning("lifecycle.payment_status_lookup_failed order=%s", order.ref, exc_info=True)
        return False


def _payment_method(order, config: ChannelConfig) -> str:
    payment = (order.data or {}).get("payment") or {}
    method = str(payment.get("method") or "").lower()
    if method:
        return method

    configured = config.payment.available_methods
    if len(configured) == 1:
        return str(configured[0] or "").lower()
    return ""


def _should_initiate_payment_on_commit(order, config: ChannelConfig) -> bool:
    if config.payment.timing == "external":
        return False
    if config.payment.timing == "at_commit":
        return True
    if config.payment.timing == "post_commit":
        return _payment_method(order, config) == "card"
    return False


def _requires_captured_payment_before_confirmation(order, config: ChannelConfig) -> bool:
    """Return True when confirmation must wait for an upfront digital capture."""
    if config.payment.timing in {"external", "post_commit"}:
        return False

    payment = (order.data or {}).get("payment") or {}
    selected_method = str(payment.get("method") or "").lower()
    has_live_intent = bool(payment.get("intent_ref") or payment.get("status"))
    method = _payment_method(order, config)
    if method in _OFFLINE_PAYMENT_METHODS:
        return False

    if selected_method in _UPFRONT_DIGITAL_PAYMENT_METHODS:
        return True

    if has_live_intent and method in _UPFRONT_DIGITAL_PAYMENT_METHODS:
        return True

    configured_methods = {str(method or "").lower() for method in config.payment.available_methods}
    return (
        config.payment.timing == "at_commit"
        and bool(configured_methods & _UPFRONT_DIGITAL_PAYMENT_METHODS)
    )


def _requires_payment_before_physical_work(order, config: ChannelConfig) -> bool:
    if config.payment.timing == "external":
        return False
    method = _payment_method(order, config)
    return method in _UPFRONT_DIGITAL_PAYMENT_METHODS


def _payment_is_authorized(order) -> bool:
    try:
        status = (payment.get_payment_status(order) or "").lower()
    except Exception:
        logger.warning("lifecycle.payment_status_lookup_failed order=%s", order.ref, exc_info=True)
        return False
    return status == "authorized"


def _dispatch_physical_work(order) -> bool:
    try:
        from shopman.shop.services import kds
        tickets = kds.dispatch(order)
    except ImportError:
        return False

    if tickets:
        return True
    try:
        return bool(order.kds_tickets.exists())
    except Exception:
        return False


def _mark_preparing_after_physical_work_dispatch(order) -> bool:
    if order.status != Order.Status.CONFIRMED:
        return False
    if not order.can_transition_to(Order.Status.PREPARING):
        return False
    order.transition_status(Order.Status.PREPARING, actor="system:kds_dispatch")
    return True


def _schedule_confirmation_timeout(
    order,
    config: ChannelConfig,
    *,
    action: str,
    source: str,
) -> Directive | None:
    """Schedule or rebase the store-decision timer for a NEW order."""
    expires_at, calendar_state = next_operational_deadline(
        timeout=timedelta(minutes=config.confirmation.timeout_minutes),
    )
    if expires_at is None:
        logger.warning(
            "confirmation_timeout_not_scheduled_no_next_opening order=%s action=%s source=%s",
            order.ref,
            action,
            source,
        )
        return None
    payload = {
        "order_ref": order.ref,
        "action": action,
        "expires_at": expires_at.isoformat(),
        "source": source,
    }
    if calendar_state.is_closed:
        payload.update(
            {
                "outside_business_hours": True,
                "deferred_until": (
                    calendar_state.next_open_at.isoformat()
                    if calendar_state.next_open_at
                    else None
                ),
                "closed_reason": calendar_state.closed_reason,
                "closure_source": calendar_state.closure_source,
            }
        )
    existing = (
        Directive.objects.filter(
            topic="confirmation.timeout",
            payload__order_ref=order.ref,
            status="queued",
        )
        .order_by("available_at", "id")
        .first()
    )
    if existing:
        if (
            existing.payload.get("action") == action
            and existing.payload.get("source") == source
        ):
            return existing
        existing.payload = payload
        existing.available_at = expires_at
        existing.save(update_fields=["payload", "available_at", "updated_at"])
        return existing

    return Directive.objects.create(
        topic="confirmation.timeout",
        payload=payload,
        available_at=expires_at,
    )


def _check_availability(order, config: ChannelConfig) -> bool:
    """Per-item availability check. Returns False if order was cancelled."""
    channel_ref = order.channel_ref or None
    target_date = get_commitment_date(order)
    rejected: list[tuple[str, str]] = []
    item_decisions: list[dict] = []

    for item in order.snapshot.get("items", []):
        sku = item["sku"]
        qty = item["qty"]
        status = availability.decide(
            sku,
            qty,
            channel_ref=channel_ref,
            target_date=target_date,
        )
        item_decisions.append(status)
        if not status["approved"]:
            rejected.append((sku, status.get("reason_code") or "unavailable"))

    if rejected:
        reasons = ", ".join(f"{sku}:{code}" for sku, code in rejected)
        logger.info("dispatch.on_commit: rejecting order %s — %s", order.ref, reasons)
        _record_availability_decision(
            order,
            approved=False,
            source="stock.promise_decision",
            rejected=rejected,
            decisions=item_decisions,
        )
        _create_alert(order, "rejected_unavailable")
        order.transition_status(Order.Status.CANCELLED, actor="auto_reject_unavailable")
        return False

    return True


def _verify_holds(order) -> bool:
    """Defense-in-depth: verify held SKUs match ordered SKUs after stock.hold().
    Returns False if order was cancelled."""
    held_skus = {h.get("sku") for h in (order.data or {}).get("hold_ids", []) if h.get("hold_id") or h.get("untracked")}
    ordered_skus = {item["sku"] for item in order.snapshot.get("items", [])}
    missing = ordered_skus - held_skus

    if missing:
        _record_availability_decision(
            order,
            approved=False,
            source="stock.verify_holds",
            rejected=[(sku, "missing_hold") for sku in sorted(missing)],
        )
        _create_alert(order, "rejected_oos")
        order.transition_status(Order.Status.CANCELLED, actor="auto_reject_oos")
        stock.release(order)
        return False

    return True


def _record_availability_decision(
    order,
    *,
    approved: bool,
    source: str,
    rejected: list[tuple[str, str]] | None = None,
    decisions: list[dict] | None = None,
) -> None:
    """Persist a lightweight audit of the operational availability decision."""
    target_date = get_commitment_date(order)
    payload = {
        "approved": approved,
        "source": source,
        "checked_at": timezone.now().isoformat(),
        "target_date": target_date.isoformat() if target_date else None,
        "channel_ref": order.channel_ref,
        "hold_ids": [entry.get("hold_id") for entry in (order.data or {}).get("hold_ids", []) if entry.get("hold_id")],
        "items": [
            {
                "sku": item.get("sku"),
                "qty": item.get("qty"),
            }
            for item in order.snapshot.get("items", [])
        ],
    }
    if decisions is not None:
        payload["decisions"] = decisions
    if rejected:
        payload["rejected"] = [
            {"sku": sku, "reason": reason}
            for sku, reason in rejected
        ]

    order.data["availability_decision"] = payload
    order.save(update_fields=["data", "updated_at"])


def _create_alert(order, alert_type: str) -> None:
    """Create an OperatorAlert for exceptional situations.

    Alerting is a best-effort side effect: a failure to persist the alert
    must not abort the phase handler that called it. The broad ``except``
    is intentional, but imports and message preparation are deliberately
    kept *outside* the try block so that structural bugs (missing model,
    bad field, typo) surface loudly instead of being silently swallowed.
    """
    from shopman.shop.adapters import alert as alert_adapter

    message = f"Pedido {order.ref}: {alert_type.replace('_', ' ')}"
    try:
        alert_adapter.create(alert_type, "warning", message, order_ref=order.ref)
    except Exception:
        logger.exception("lifecycle._create_alert: failed for order %s", order.ref)
