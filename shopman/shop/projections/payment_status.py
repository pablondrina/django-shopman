"""Payment — read-side Projection of data (surface-agnostic).

The policy-laden, semantic read model for the customer-facing payment gate. It
decides the payment promise state machine, the terminal flags (paid/cancelled/
expired), the available ``Action`` items and whether the surface should redirect
out of the gate — and emits it as **data**: enums/keys, ``_q`` cents, ISO
timestamps, booleans and refs. It carries **no** rendered copy, money
formatting, label or HTML — those are Presentation, resolved per surface in
``<surface>/presentation/payment.py`` from this projection plus the copy catalog
(``shop.projections.copy``).

Actions carry resolved ``label`` strings (ADR-012: "copy curta pronta para a
superfície"), resolved here because the orchestrator owns copy
(``OMOTENASHI_DEFAULTS``); no money/locale/HTML formatting happens here.

Payment *policy* (``get_payment_status``/``has_sufficient_captured_payment``/
``can_cancel``) stays in ``shop.services.payment_status`` (write-side facade,
consumed by lifecycle/handlers); this module imports it to decide the flags.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from shopman.shop.omotenashi import resolve_copy
from shopman.shop.projections.types import Action
from shopman.shop.services import payment_status as payment_policy
from shopman.shop.services import storefront_links

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Data DTOs — frozen, semantic, surface-agnostic
# ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PaymentPromiseData:
    """Customer-facing payment promise as data.

    The promise *state machine* is policy and lives here; ``state`` plus the
    surrounding flags let Presentation pick the title/message/next-step copy.
    No rendered strings are stored (``Action.label`` excepted — ADR-012).
    """

    state: str
    tone: str
    actions: tuple[Action, ...]
    deadline_at: str | None
    deadline_kind: str | None
    deadline_action: str
    requires_active_notification: bool
    stale_after_seconds: int | None = None


@dataclass(frozen=True)
class PaymentData:
    """Canonical full payment page projection — data only."""

    order_ref: str
    method: str
    order_status: str
    payment_status: str | None
    total_q: int
    promise: PaymentPromiseData
    pix_qr_code: str | None
    pix_copy_paste: str | None
    pix_expires_at: str | None
    checkout_url: str | None
    status_url: str
    server_now_iso: str
    actions: tuple[Action, ...]
    error_message: str | None
    is_debug: bool


@dataclass(frozen=True)
class PaymentStatusData:
    """Canonical payment status polling projection — data only."""

    order_ref: str
    order_status: str
    promise: PaymentPromiseData
    is_paid: bool
    is_cancelled: bool
    is_expired: bool
    is_terminal: bool
    redirect_url: str
    should_redirect: bool


# ──────────────────────────────────────────────────────────────────────
# Builders
# ──────────────────────────────────────────────────────────────────────


def build_payment(order, *, is_debug: bool = False) -> PaymentData:
    """Build payment page data from order payment metadata."""
    payment = (order.data or {}).get("payment") or {}
    method = payment.get("method") or "pix"

    pix_qr_code: str | None = None
    pix_copy_paste: str | None = None
    pix_expires_at: str | None = None
    if method == "pix":
        pix_qr_code = _qr_image_src(payment.get("qr_code") or payment.get("pix_qr_code") or None)
        pix_copy_paste = (
            payment.get("copy_paste")
            or payment.get("pix_copy_paste")
            or payment.get("pix_code")
            or None
        )
        pix_expires_at = payment.get("expires_at") or None

    checkout_url: str | None = None
    if method == "card":
        checkout_url = payment.get("checkout_url") or None

    payment_state = (payment_policy.get_payment_status(order) or payment.get("status") or "").lower()
    error_message = payment.get("error") or None
    promise = _build_payment_promise(
        order=order,
        method=method,
        payment_state=payment_state,
        pix_expires_at=pix_expires_at,
        checkout_url=checkout_url,
        error_message=error_message,
    )

    return PaymentData(
        order_ref=order.ref,
        method=method,
        order_status=str(getattr(order, "status", "") or ""),
        payment_status=payment_state or None,
        total_q=int(order.total_q),
        promise=promise,
        pix_qr_code=pix_qr_code,
        pix_copy_paste=pix_copy_paste,
        pix_expires_at=pix_expires_at,
        checkout_url=checkout_url,
        status_url=f"/api/v1/payment/{order.ref}/status/",
        server_now_iso=timezone.now().isoformat(),
        actions=_build_payment_actions(order, is_debug=is_debug),
        error_message=error_message,
        is_debug=is_debug,
    )


def build_payment_status(order) -> PaymentStatusData:
    """Build payment polling state, degrading malformed expiry to non-expired."""
    payment = (order.data or {}).get("payment") or {}
    payment_state = (payment_policy.get_payment_status(order) or payment.get("status") or "").lower()
    is_paid, is_cancelled, is_expired = _payment_flags(
        order=order,
        expires_at_str=payment.get("expires_at"),
    )
    redirect_url = storefront_links.order_tracking_url(order.ref)
    promise = _build_payment_promise(
        order=order,
        method=payment.get("method") or "pix",
        payment_state=payment_state,
        pix_expires_at=payment.get("expires_at") or None,
        checkout_url=payment.get("checkout_url") or None,
        error_message=payment.get("error") or None,
    )

    return PaymentStatusData(
        order_ref=order.ref,
        order_status=str(getattr(order, "status", "") or ""),
        promise=promise,
        is_paid=is_paid,
        is_cancelled=is_cancelled,
        is_expired=is_expired,
        is_terminal=is_paid or is_cancelled or is_expired,
        redirect_url=redirect_url,
        should_redirect=_payment_status_should_redirect(
            promise=promise,
            is_paid=is_paid,
            is_cancelled=is_cancelled,
            is_expired=is_expired,
        ),
    )


# ──────────────────────────────────────────────────────────────────────
# Redirect / terminal logic
# ──────────────────────────────────────────────────────────────────────


def promise_has_pending_payment_action(promise) -> bool:
    """Whether the promise still offers an actionable payment step.

    Works on any promise carrying ``actions: tuple[Action, ...]`` (data or
    presentation), so surfaces can reuse it without re-deriving policy.
    """
    return any(
        action.enabled and action.ref not in {"track_order"}
        for action in promise.actions
    )


def _payment_status_should_redirect(
    *,
    promise: PaymentPromiseData,
    is_paid: bool,
    is_cancelled: bool,
    is_expired: bool,
) -> bool:
    if is_paid or is_cancelled or is_expired:
        return True
    return not promise_has_pending_payment_action(promise)


def _payment_flags(
    *,
    order,
    expires_at_str: str | None,
) -> tuple[bool, bool, bool]:
    is_paid = payment_policy.has_sufficient_captured_payment(order)
    is_cancelled = order.status == "cancelled"
    is_expired = False
    if expires_at_str and not is_paid and not is_cancelled:
        try:
            expires_at = parse_datetime(expires_at_str)
            if expires_at and timezone.now() > expires_at:
                is_expired = True
        except Exception:
            logger.warning("payment_status_expiry_parse_failed order=%s", order.ref, exc_info=True)
    return is_paid, is_cancelled, is_expired


# ──────────────────────────────────────────────────────────────────────
# Actions (Action.label resolved from config — orchestrator owns copy)
# ──────────────────────────────────────────────────────────────────────


def _qr_image_src(value: str | None) -> str | None:
    if not value:
        return None
    qr_image = str(value)
    if qr_image.startswith("data:image/"):
        return qr_image
    return f"data:image/png;base64,{qr_image}"


def _copy_title(key: str, fallback: str) -> str:
    try:
        entry = resolve_copy(key, moment="*", audience="*")
        return entry.title or fallback
    except Exception:
        logger.debug("payment_copy_failed key=%s", key, exc_info=True)
        return fallback


def _action(
    *,
    ref: str,
    kind: str,
    label: str,
    priority: str = "primary",
    href: str = "",
    enabled: bool = True,
    reason: str = "",
    method: str = "",
    payload_schema: dict | None = None,
    idempotency: str = "none",
    confirmation: dict | None = None,
) -> Action:
    return Action(
        ref=ref,
        kind=kind,
        label=label,
        priority=priority,
        enabled=enabled,
        reason=reason,
        href=href,
        method=method,
        payload_schema=payload_schema or {},
        idempotency=idempotency,
        confirmation=confirmation or {},
    )


def _can_mock_confirm_payment(order, *, is_debug: bool) -> bool:
    if not is_debug:
        return False
    if order.status not in {"new", "confirmed"}:
        return False
    payment = (order.data or {}).get("payment") or {}
    method = str(payment.get("method") or "").lower()
    if method not in {"pix", "card"} or not payment.get("intent_ref"):
        return False
    status = (payment_policy.get_payment_status(order) or "").lower()
    return status not in {"", "unknown", "captured", "paid", "refunded", "cancelled", "failed"}


def _build_payment_actions(order, *, is_debug: bool) -> tuple[Action, ...]:
    if not _can_mock_confirm_payment(order, is_debug=is_debug):
        return ()
    return (
        _action(
            ref="mock_confirm_payment",
            kind="mutation",
            label=_copy_title("PAYMENT_DEV_CONFIRM_CTA", "Confirmar pagamento teste"),
            priority="quiet",
            href=f"/api/v1/payment/{order.ref}/mock-confirm/",
            method="POST",
            payload_schema={
                "type": "object",
                "properties": {
                    "idempotency_key": {"type": "string"},
                },
            },
            idempotency="recommended",
        ),
    )


# ──────────────────────────────────────────────────────────────────────
# Promise state machine (policy → data; copy resolved in Presentation)
# ──────────────────────────────────────────────────────────────────────


def _build_payment_promise(
    *,
    order,
    method: str,
    payment_state: str,
    pix_expires_at: str | None,
    checkout_url: str | None,
    error_message: str | None,
) -> PaymentPromiseData:
    is_paid, is_cancelled, is_expired = _payment_flags(
        order=order,
        expires_at_str=pix_expires_at,
    )
    if is_paid:
        return PaymentPromiseData(
            state="paid",
            tone="success",
            actions=(
                _action(
                    ref="track_order",
                    kind="link",
                    label=_copy_title("CONFIRMATION_TRACK_CTA", "Acompanhar pedido"),
                    priority="secondary",
                    href=storefront_links.order_tracking_url(order.ref),
                ),
            ),
            deadline_at=None,
            deadline_kind=None,
            deadline_action="redirect_tracking",
            requires_active_notification=False,
            stale_after_seconds=None,
        )
    if is_cancelled:
        return PaymentPromiseData(
            state="cancelled",
            tone="danger",
            actions=(
                _action(
                    ref="track_order",
                    kind="link",
                    label=_copy_title("PAYMENT_VIEW_ORDER_CTA", "Ver pedido"),
                    priority="secondary",
                    href=storefront_links.order_tracking_url(order.ref),
                ),
            ),
            deadline_at=None,
            deadline_kind=None,
            deadline_action="none",
            requires_active_notification=False,
            stale_after_seconds=None,
        )
    if is_expired:
        return PaymentPromiseData(
            state="expired",
            tone="warning",
            actions=(
                _action(
                    ref="track_order",
                    kind="link",
                    label=_copy_title("PAYMENT_VIEW_ORDER_CTA", "Ver pedido"),
                    priority="secondary",
                    href=storefront_links.order_tracking_url(order.ref),
                ),
            ),
            deadline_at=None,
            deadline_kind="payment",
            deadline_action="show_payment_expired",
            requires_active_notification=True,
            stale_after_seconds=None,
        )
    if method == "card" and payment_state == "authorized":
        return PaymentPromiseData(
            state="card_authorized",
            tone="info",
            actions=(),
            deadline_at=None,
            deadline_kind=None,
            deadline_action="none",
            requires_active_notification=False,
            stale_after_seconds=45,
        )
    if error_message:
        return PaymentPromiseData(
            state="intent_error",
            tone="warning",
            actions=(
                _action(
                    ref="retry_payment",
                    kind="link",
                    label=_copy_title("PAYMENT_RETRY_CTA", "Tentar novamente"),
                    href=storefront_links.order_payment_url(order.ref),
                ),
            ),
            deadline_at=pix_expires_at,
            deadline_kind="payment" if pix_expires_at else None,
            deadline_action="retry_payment_intent",
            requires_active_notification=False,
            stale_after_seconds=30,
        )
    if method == "card":
        if checkout_url:
            if order.status != "confirmed":
                return PaymentPromiseData(
                    state="card_authorization_requested",
                    tone="info",
                    actions=(
                        _action(
                            ref="authorize_card",
                            kind="external",
                            label=_copy_title("PAYMENT_PROMISE_CARD_PRECONFIRMATION_ACTION", "Autorizar cartão"),
                            href=checkout_url,
                        ),
                    ),
                    deadline_at=None,
                    deadline_kind=None,
                    deadline_action="wait_gateway_return",
                    requires_active_notification=False,
                    stale_after_seconds=45,
                )
            return PaymentPromiseData(
                state="card_checkout_requested",
                tone="info",
                actions=(
                    _action(
                        ref="pay_card",
                        kind="external",
                        label=_copy_title("PAYMENT_PROMISE_CARD_ACTION", "Pagar com cartão"),
                        href=checkout_url,
                    ),
                ),
                deadline_at=None,
                deadline_kind=None,
                deadline_action="wait_gateway_return",
                requires_active_notification=False,
                stale_after_seconds=45,
            )
        return PaymentPromiseData(
            state="card_checkout_pending",
            tone="warning",
            actions=(
                _action(
                    ref="retry_payment",
                    kind="link",
                    label=_copy_title("PAYMENT_RETRY_CTA", "Tentar novamente"),
                    href=storefront_links.order_payment_url(order.ref),
                ),
            ),
            deadline_at=None,
            deadline_kind=None,
            deadline_action="retry_payment_intent",
            requires_active_notification=False,
            stale_after_seconds=30,
        )
    if order.status != "confirmed":
        return PaymentPromiseData(
            state="pix_payment_before_confirmation",
            tone="info",
            actions=(
                _action(
                    ref="copy_pix",
                    kind="copy",
                    label=_copy_title("PAYMENT_PROMISE_PIX_ACTION", "Copiar código PIX"),
                ),
            ),
            deadline_at=pix_expires_at,
            deadline_kind="payment" if pix_expires_at else None,
            deadline_action="cancel_order_on_timeout" if pix_expires_at else "none",
            requires_active_notification=True,
            stale_after_seconds=45,
        )
    return PaymentPromiseData(
        state="pix_payment_requested",
        tone="info",
        actions=(
            _action(
                ref="copy_pix",
                kind="copy",
                label=_copy_title("PAYMENT_PROMISE_PIX_ACTION", "Copiar código PIX"),
            ),
        ),
        deadline_at=pix_expires_at,
        deadline_kind="payment" if pix_expires_at else None,
        deadline_action="cancel_order_on_timeout" if pix_expires_at else "none",
        requires_active_notification=True,
        stale_after_seconds=45,
    )


__all__ = [
    "PaymentData",
    "PaymentPromiseData",
    "PaymentStatusData",
    "build_payment",
    "build_payment_status",
    "promise_has_pending_payment_action",
]
