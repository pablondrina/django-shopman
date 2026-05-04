"""Canonical payment projections for customer-facing payment surfaces."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from shopman.utils.monetary import format_money

from shopman.shop.omotenashi import resolve_copy
from shopman.shop.services import payment as payment_service

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PaymentPromiseProjection:
    """Customer-facing payment promise contract.

    Mirrors the tracking promise shape for the payment gate: the page must say
    what is happening now, what the customer must do, what deadline matters,
    what happens next, and how recovery works.
    """

    state: str
    title: str
    message: str
    tone: str
    customer_action: str
    customer_action_label: str
    customer_action_url: str | None
    deadline_at: str | None
    deadline_kind: str | None
    deadline_action: str
    requires_active_notification: bool
    next_event: str
    recovery: str
    active_notification: str
    stale_after_seconds: int | None = None


@dataclass(frozen=True)
class PaymentProjection:
    """Canonical full payment page projection."""

    order_ref: str
    method: str
    total_display: str
    promise: PaymentPromiseProjection
    pix_qr_code: str | None
    pix_copy_paste: str | None
    pix_expires_at: str | None
    checkout_url: str | None
    status_url: str
    server_now_iso: str
    error_message: str | None
    is_debug: bool
    can_mock_confirm: bool


@dataclass(frozen=True)
class PaymentStatusProjection:
    """Canonical payment status polling projection."""

    order_ref: str
    promise: PaymentPromiseProjection
    is_paid: bool
    is_cancelled: bool
    is_expired: bool
    is_terminal: bool
    redirect_url: str


def get_payment_status(order) -> str | None:
    """Return payment status from Payman via the payment service."""
    return payment_service.get_payment_status(order)


def has_sufficient_captured_payment(order) -> bool:
    """Return whether captured funds still cover the order total."""
    return payment_service.has_sufficient_captured_payment(order) is True


def can_cancel(order) -> bool:
    return payment_service.can_cancel(order)


def build_payment(order, *, is_debug: bool = False) -> PaymentProjection:
    """Build payment page data from order payment display metadata."""
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

    payment_state = (get_payment_status(order) or payment.get("status") or "").lower()
    error_message = payment.get("error") or None
    promise = _build_payment_promise(
        order=order,
        method=method,
        payment_state=payment_state,
        pix_expires_at=pix_expires_at,
        checkout_url=checkout_url,
        error_message=error_message,
        redirect_url=f"/pedido/{order.ref}/",
    )

    return PaymentProjection(
        order_ref=order.ref,
        method=method,
        total_display=f"R$ {format_money(order.total_q)}",
        promise=promise,
        pix_qr_code=pix_qr_code,
        pix_copy_paste=pix_copy_paste,
        pix_expires_at=pix_expires_at,
        checkout_url=checkout_url,
        status_url=reverse("storefront:payment_status_partial", kwargs={"ref": order.ref}),
        server_now_iso=timezone.now().isoformat(),
        error_message=error_message,
        is_debug=is_debug,
        can_mock_confirm=bool(payment.get("intent_ref")),
    )


def _qr_image_src(value: str | None) -> str | None:
    if not value:
        return None
    qr_image = str(value)
    if qr_image.startswith("data:image/"):
        return qr_image
    return f"data:image/png;base64,{qr_image}"


def build_payment_status(order) -> PaymentStatusProjection:
    """Build payment polling state, degrading malformed expiry to non-expired."""
    payment = (order.data or {}).get("payment") or {}
    payment_state = (get_payment_status(order) or payment.get("status") or "").lower()
    is_paid, is_cancelled, is_expired = _payment_flags(
        order=order,
        payment_state=payment_state,
        expires_at_str=payment.get("expires_at"),
    )
    redirect_url = f"/pedido/{order.ref}/"
    promise = _build_payment_promise(
        order=order,
        method=payment.get("method") or "pix",
        payment_state=payment_state,
        pix_expires_at=payment.get("expires_at") or None,
        checkout_url=payment.get("checkout_url") or None,
        error_message=payment.get("error") or None,
        redirect_url=redirect_url,
    )

    return PaymentStatusProjection(
        order_ref=order.ref,
        promise=promise,
        is_paid=is_paid,
        is_cancelled=is_cancelled,
        is_expired=is_expired,
        is_terminal=is_paid or is_cancelled or is_expired,
        redirect_url=redirect_url,
    )


def _payment_flags(
    *,
    order,
    payment_state: str,
    expires_at_str: str | None,
) -> tuple[bool, bool, bool]:
    is_paid = has_sufficient_captured_payment(order)
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


def _build_payment_promise(
    *,
    order,
    method: str,
    payment_state: str,
    pix_expires_at: str | None,
    checkout_url: str | None,
    error_message: str | None,
    redirect_url: str,
) -> PaymentPromiseProjection:
    is_paid, is_cancelled, is_expired = _payment_flags(
        order=order,
        payment_state=payment_state,
        expires_at_str=pix_expires_at,
    )
    if is_paid:
        return PaymentPromiseProjection(
            state="paid",
            title=_copy_title("PAYMENT_PROMISE_PAID_TITLE", "Pagamento reconhecido"),
            message=_copy_message("PAYMENT_PROMISE_PAID_MESSAGE", "Recebemos a confirmação do pagamento."),
            tone="success",
            customer_action="track_order",
            customer_action_label=_copy_title("CONFIRMATION_TRACK_CTA", "Acompanhar pedido"),
            customer_action_url=redirect_url,
            deadline_at=None,
            deadline_kind=None,
            deadline_action="redirect_tracking",
            requires_active_notification=False,
            next_event=_copy_message("PAYMENT_PROMISE_PAID_NEXT", "Vamos mostrar o acompanhamento do pedido."),
            recovery="",
            active_notification="",
            stale_after_seconds=None,
        )
    if is_cancelled:
        return PaymentPromiseProjection(
            state="cancelled",
            title=_copy_title("PAYMENT_PROMISE_CANCELLED_TITLE", "Pedido cancelado"),
            message=_copy_message("PAYMENT_PROMISE_CANCELLED_MESSAGE", "Este pedido não aceita mais pagamento."),
            tone="danger",
            customer_action="track_order",
            customer_action_label=_copy_title("PAYMENT_VIEW_ORDER_CTA", "Ver pedido"),
            customer_action_url=redirect_url,
            deadline_at=None,
            deadline_kind=None,
            deadline_action="none",
            requires_active_notification=False,
            next_event="",
            recovery=_copy_message("PAYMENT_PROMISE_CANCELLED_RECOVERY", "Confira os detalhes do pedido ou faça um novo pedido quando quiser."),
            active_notification="",
            stale_after_seconds=None,
        )
    if is_expired:
        return PaymentPromiseProjection(
            state="expired",
            title=_copy_title("PAYMENT_PROMISE_EXPIRED_TITLE", "O prazo para pagamento expirou"),
            message=_copy_message("PAYMENT_PROMISE_EXPIRED_MESSAGE", "O pedido foi automaticamente cancelado e os itens foram liberados."),
            tone="warning",
            customer_action="track_order",
            customer_action_label=_copy_title("PAYMENT_VIEW_ORDER_CTA", "Ver pedido"),
            customer_action_url=redirect_url,
            deadline_at=None,
            deadline_kind="payment",
            deadline_action="show_payment_expired",
            requires_active_notification=True,
            next_event=_copy_message("PAYMENT_PROMISE_EXPIRED_NEXT", "Você pode refazer o pedido quando quiser."),
            recovery=_copy_message("PAYMENT_PROMISE_EXPIRED_RECOVERY", "Se precisar de ajuda, fale com o estabelecimento."),
            active_notification=_copy_message("PAYMENT_PROMISE_EXPIRED_ACTIVE_NOTIFICATION", "Também avisaremos pelos canais ativos da sua conta."),
            stale_after_seconds=None,
        )
    if error_message:
        return PaymentPromiseProjection(
            state="intent_error",
            title=_copy_title("PAYMENT_PROMISE_ERROR_TITLE", "Não conseguimos preparar o pagamento"),
            message=_copy_message("PAYMENT_PROMISE_ERROR_MESSAGE", "Seu pedido continua registrado. Tente gerar o pagamento novamente."),
            tone="warning",
            customer_action="retry",
            customer_action_label=_copy_title("PAYMENT_RETRY_CTA", "Tentar novamente"),
            customer_action_url=reverse("storefront:order_payment", kwargs={"ref": order.ref}),
            deadline_at=pix_expires_at,
            deadline_kind="payment" if pix_expires_at else None,
            deadline_action="retry_payment_intent",
            requires_active_notification=False,
            next_event=_copy_message("PAYMENT_PROMISE_ERROR_NEXT", "Se a tentativa funcionar, mostramos o Pix ou o ambiente seguro do cartão."),
            recovery=_copy_message("PAYMENT_PROMISE_ERROR_RECOVERY", "Se o erro continuar, fale com o estabelecimento para resolvermos sem perder o pedido."),
            active_notification="",
            stale_after_seconds=30,
        )
    if method == "card":
        if checkout_url:
            return PaymentPromiseProjection(
                state="card_checkout_requested",
                title=_copy_title("PAYMENT_PROMISE_CARD_TITLE", "Pagamento seguro com cartão"),
                message=_copy_message("PAYMENT_PROMISE_CARD_MESSAGE", "A disponibilidade foi confirmada. Finalize o pagamento no ambiente seguro do cartão."),
                tone="info",
                customer_action="redirect",
                customer_action_label=_copy_title("PAYMENT_PROMISE_CARD_ACTION", "Pagar com cartão"),
                customer_action_url=checkout_url,
                deadline_at=None,
                deadline_kind=None,
                deadline_action="wait_gateway_return",
                requires_active_notification=False,
                next_event=_copy_message("PAYMENT_PROMISE_CARD_NEXT", "Voltamos para o acompanhamento assim que o pagamento for confirmado."),
                recovery=_copy_message("PAYMENT_PROMISE_CARD_RECOVERY", "Se o ambiente seguro não abrir, tente novamente ou fale com o estabelecimento."),
                active_notification=_copy_message("PAYMENT_PROMISE_CARD_ACTIVE_NOTIFICATION", "Se houver confirmação ou falha, avisaremos pelos canais ativos da sua conta."),
                stale_after_seconds=45,
            )
        return PaymentPromiseProjection(
            state="card_checkout_pending",
            title=_copy_title("PAYMENT_PROMISE_CARD_PENDING_TITLE", "Preparando ambiente seguro"),
            message=_copy_message("PAYMENT_PROMISE_CARD_PENDING_MESSAGE", "Estamos preparando o ambiente seguro do cartão."),
            tone="warning",
            customer_action="retry",
            customer_action_label=_copy_title("PAYMENT_RETRY_CTA", "Tentar novamente"),
            customer_action_url=reverse("storefront:order_payment", kwargs={"ref": order.ref}),
            deadline_at=None,
            deadline_kind=None,
            deadline_action="retry_payment_intent",
            requires_active_notification=False,
            next_event=_copy_message("PAYMENT_PROMISE_CARD_PENDING_NEXT", "Quando estiver pronto, o botão de pagamento aparecerá aqui."),
            recovery=_copy_message("PAYMENT_PROMISE_CARD_PENDING_RECOVERY", "Se demorar, atualize a página ou fale com o estabelecimento."),
            active_notification="",
            stale_after_seconds=30,
        )
    return PaymentPromiseProjection(
        state="pix_payment_requested",
        title=_copy_title("PAYMENT_PROMISE_PIX_TITLE", "Pagamento Pix"),
        message=_copy_message("PAYMENT_PROMISE_PIX_MESSAGE", "A disponibilidade foi confirmada. Use o Pix abaixo para liberar o preparo."),
        tone="info",
        customer_action="pay_on_page",
        customer_action_label=_copy_title("PAYMENT_PROMISE_PIX_ACTION", "Use o QR Code ou copia e cola abaixo"),
        customer_action_url=None,
        deadline_at=pix_expires_at,
        deadline_kind="payment" if pix_expires_at else None,
        deadline_action="cancel_order_on_timeout" if pix_expires_at else "none",
        requires_active_notification=True,
        next_event=_copy_message("PAYMENT_PROMISE_PIX_NEXT", "Assim que o banco confirmar, seguimos para o preparo do pedido."),
        recovery=_copy_message("PAYMENT_PROMISE_PIX_RECOVERY", "Se o prazo expirar, o pedido será cancelado automaticamente e os itens serão liberados."),
        active_notification=_copy_message("PAYMENT_PROMISE_PIX_ACTIVE_NOTIFICATION", "Quando o pagamento for reconhecido, avisaremos pelos canais ativos da sua conta."),
        stale_after_seconds=45,
    )


def _copy_title(key: str, fallback: str) -> str:
    entry = resolve_copy(key, moment="*", audience="*")
    return entry.title or fallback


def _copy_message(key: str, fallback: str) -> str:
    entry = resolve_copy(key, moment="*", audience="*")
    return entry.message or fallback


__all__ = [
    "PaymentProjection",
    "PaymentPromiseProjection",
    "PaymentStatusProjection",
    "build_payment",
    "build_payment_status",
    "can_cancel",
    "get_payment_status",
    "has_sufficient_captured_payment",
]
