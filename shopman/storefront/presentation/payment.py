"""Payment — storefront Presentation.

Consumes the data Projection (``shop.projections.payment_status``) plus the copy
catalog (``shop.projections.copy``) and produces the display shape the payment
templates and the storefront REST surface consume: resolved promise copy, money
formatted ``R$``, the polling/terminal flags. **No policy** is decided here —
every decision (promise state, terminal flags, actions, redirect) already
arrived sealed in the data projection.

The canonical copy lives in the orchestrator (``OMOTENASHI_DEFAULTS``); the
strings passed to ``catalog.title``/``catalog.message`` are last-resort
fallbacks (per the copy.py contract: fallback PT-BR lives in Presentation).
"""

from __future__ import annotations

from dataclasses import dataclass

from shopman.utils.monetary import format_money

from shopman.shop.projections.copy import CopyCatalog, build_copy
from shopman.shop.projections.payment_status import (
    PaymentData,
    PaymentPromiseData,
    PaymentStatusData,
    promise_has_pending_payment_action,  # noqa: F401 — re-exported for the payment view
)
from shopman.shop.projections.payment_status import (
    build_payment as build_payment_data,
)
from shopman.shop.projections.payment_status import (
    build_payment_status as build_payment_status_data,
)
from shopman.shop.projections.types import Action

# state → (title_key, title_fb, message_key, message_fb,
#          next_key, next_fb, recovery_key, recovery_fb, active_key, active_fb)
_PROMISE_COPY: dict[str, tuple[str, str, str, str, str, str, str, str, str, str]] = {
    "paid": (
        "PAYMENT_PROMISE_PAID_TITLE", "Pagamento reconhecido",
        "PAYMENT_PROMISE_PAID_MESSAGE", "Recebemos a confirmação do pagamento.",
        "PAYMENT_PROMISE_PAID_NEXT", "Vamos mostrar o acompanhamento do pedido.",
        "", "", "", "",
    ),
    "cancelled": (
        "PAYMENT_PROMISE_CANCELLED_TITLE", "Pedido cancelado",
        "PAYMENT_PROMISE_CANCELLED_MESSAGE", "Este pedido não aceita mais pagamento.",
        "", "",
        "PAYMENT_PROMISE_CANCELLED_RECOVERY",
        "Confira os detalhes do pedido ou faça um novo pedido quando quiser.",
        "", "",
    ),
    "expired": (
        "PAYMENT_PROMISE_EXPIRED_TITLE", "O prazo para pagamento expirou",
        "PAYMENT_PROMISE_EXPIRED_MESSAGE",
        "O pedido foi automaticamente cancelado e os itens foram liberados.",
        "PAYMENT_PROMISE_EXPIRED_NEXT", "Você pode refazer o pedido quando quiser.",
        "PAYMENT_PROMISE_EXPIRED_RECOVERY", "Se precisar de ajuda, fale com o estabelecimento.",
        "PAYMENT_PROMISE_EXPIRED_ACTIVE_NOTIFICATION",
        "Também avisaremos pelos canais ativos da sua conta.",
    ),
    "card_authorized": (
        "PAYMENT_PROMISE_CARD_AUTHORIZED_TITLE", "Pagamento autorizado.",
        "PAYMENT_PROMISE_CARD_AUTHORIZED_MESSAGE", "Você não precisa fazer nada agora.",
        "", "",  # next_event resolved per order_status (see _card_authorized_next)
        "", "", "", "",
    ),
    "intent_error": (
        "PAYMENT_PROMISE_ERROR_TITLE", "Não conseguimos preparar o pagamento",
        "PAYMENT_PROMISE_ERROR_MESSAGE",
        "Seu pedido continua registrado. Tente gerar o pagamento novamente.",
        "PAYMENT_PROMISE_ERROR_NEXT",
        "Se a tentativa funcionar, mostramos o Pix ou o ambiente seguro do cartão.",
        "PAYMENT_PROMISE_ERROR_RECOVERY",
        "Se o erro continuar, fale com o estabelecimento para resolvermos sem perder o pedido.",
        "", "",
    ),
    "card_authorization_requested": (
        "PAYMENT_PROMISE_CARD_PRECONFIRMATION_TITLE", "Autorizar cartão",
        "PAYMENT_PROMISE_CARD_PRECONFIRMATION_MESSAGE",
        "Abra o ambiente seguro para autorizar o cartão. O estabelecimento ainda vai conferir a disponibilidade.",
        "PAYMENT_PROMISE_CARD_PRECONFIRMATION_NEXT",
        "Depois da autorização, acompanhe a confirmação do estabelecimento.",
        "PAYMENT_PROMISE_CARD_PRECONFIRMATION_RECOVERY",
        "Se o ambiente seguro não abrir, tente novamente ou fale com o estabelecimento.",
        "PAYMENT_PROMISE_CARD_PRECONFIRMATION_ACTIVE_NOTIFICATION",
        "Avisaremos quando o pagamento ou a confirmação da loja avançar.",
    ),
    "card_checkout_requested": (
        "PAYMENT_PROMISE_CARD_TITLE", "Pagamento seguro com cartão",
        "PAYMENT_PROMISE_CARD_MESSAGE",
        "A disponibilidade foi confirmada. Finalize o pagamento no ambiente seguro do cartão.",
        "PAYMENT_PROMISE_CARD_NEXT",
        "Voltamos para o acompanhamento assim que o pagamento for confirmado.",
        "PAYMENT_PROMISE_CARD_RECOVERY",
        "Se o ambiente seguro não abrir, tente novamente ou fale com o estabelecimento.",
        "PAYMENT_PROMISE_CARD_ACTIVE_NOTIFICATION",
        "Se houver confirmação ou falha, avisaremos pelos canais ativos da sua conta.",
    ),
    "card_checkout_pending": (
        "PAYMENT_PROMISE_CARD_PENDING_TITLE", "Preparando ambiente seguro",
        "PAYMENT_PROMISE_CARD_PENDING_MESSAGE", "Estamos preparando o ambiente seguro do cartão.",
        "PAYMENT_PROMISE_CARD_PENDING_NEXT", "Quando estiver pronto, o botão de pagamento aparecerá aqui.",
        "PAYMENT_PROMISE_CARD_PENDING_RECOVERY", "Se demorar, atualize a página ou fale com o estabelecimento.",
        "", "",
    ),
    "pix_payment_before_confirmation": (
        "PAYMENT_PROMISE_PIX_PRECONFIRMATION_TITLE", "Pagamento Pix",
        "PAYMENT_PROMISE_PIX_PRECONFIRMATION_MESSAGE",
        "Use o Pix abaixo para registrar o pagamento. O estabelecimento ainda vai conferir a disponibilidade.",
        "PAYMENT_PROMISE_PIX_PRECONFIRMATION_NEXT",
        "Depois do pagamento, acompanhe a confirmação do estabelecimento.",
        "PAYMENT_PROMISE_PIX_PRECONFIRMATION_RECOVERY",
        "Se o prazo expirar, o pedido será cancelado automaticamente e os itens serão liberados.",
        "PAYMENT_PROMISE_PIX_ACTIVE_NOTIFICATION",
        "Quando o pagamento for reconhecido, avisaremos pelos canais ativos da sua conta.",
    ),
    "pix_payment_requested": (
        "PAYMENT_PROMISE_PIX_TITLE", "Pagamento Pix",
        "PAYMENT_PROMISE_PIX_MESSAGE",
        "A disponibilidade foi confirmada. Use o Pix abaixo para liberar o preparo.",
        "PAYMENT_PROMISE_PIX_NEXT", "Assim que o banco confirmar, seguimos para o preparo do pedido.",
        "PAYMENT_PROMISE_PIX_RECOVERY",
        "Se o prazo expirar, o pedido será cancelado automaticamente e os itens serão liberados.",
        "PAYMENT_PROMISE_PIX_ACTIVE_NOTIFICATION",
        "Quando o pagamento for reconhecido, avisaremos pelos canais ativos da sua conta.",
    ),
}


# ──────────────────────────────────────────────────────────────────────
# Presentation DTOs (appearance) — what templates / serializers consume
# ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PaymentPromiseProjection:
    """Customer-facing payment promise contract, rendered."""

    state: str
    title: str
    message: str
    tone: str
    actions: tuple[Action, ...]
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
    """Canonical full payment page projection, rendered."""

    order_ref: str
    method: str
    order_status: str
    payment_status: str | None
    total_display: str
    promise: PaymentPromiseProjection
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
class PaymentStatusProjection:
    """Canonical payment status polling projection, rendered."""

    order_ref: str
    promise: PaymentPromiseProjection
    is_paid: bool
    is_cancelled: bool
    is_expired: bool
    is_terminal: bool
    redirect_url: str
    should_redirect: bool


# ──────────────────────────────────────────────────────────────────────
# Entry points
# ──────────────────────────────────────────────────────────────────────


def build_payment(order) -> PaymentProjection:
    """Build the full payment page projection for an Order."""
    from django.conf import settings

    return present_payment(build_payment_data(order, is_debug=settings.DEBUG))


def build_payment_status(order) -> PaymentStatusProjection:
    """Build the polling partial projection for an Order."""
    return present_payment_status(build_payment_status_data(order))


def present_payment(data: PaymentData) -> PaymentProjection:
    copy = build_copy("PAYMENT")
    return PaymentProjection(
        order_ref=data.order_ref,
        method=data.method,
        order_status=data.order_status,
        payment_status=data.payment_status,
        total_display=f"R$ {format_money(data.total_q)}",
        promise=_present_promise(data.promise, order_status=data.order_status, copy=copy),
        pix_qr_code=data.pix_qr_code,
        pix_copy_paste=data.pix_copy_paste,
        pix_expires_at=data.pix_expires_at,
        checkout_url=data.checkout_url,
        status_url=data.status_url,
        server_now_iso=data.server_now_iso,
        actions=data.actions,
        error_message=data.error_message,
        is_debug=data.is_debug,
    )


def present_payment_status(data: PaymentStatusData) -> PaymentStatusProjection:
    copy = build_copy("PAYMENT")
    return PaymentStatusProjection(
        order_ref=data.order_ref,
        promise=_present_promise(data.promise, order_status=data.order_status, copy=copy),
        is_paid=data.is_paid,
        is_cancelled=data.is_cancelled,
        is_expired=data.is_expired,
        is_terminal=data.is_terminal,
        redirect_url=data.redirect_url,
        should_redirect=data.should_redirect,
    )


# ──────────────────────────────────────────────────────────────────────
# Promise copy
# ──────────────────────────────────────────────────────────────────────


def _present_promise(
    data: PaymentPromiseData,
    *,
    order_status: str,
    copy: CopyCatalog,
) -> PaymentPromiseProjection:
    title, message, next_event, recovery, active_notification = _promise_copy(
        data,
        order_status=order_status,
        copy=copy,
    )
    return PaymentPromiseProjection(
        state=data.state,
        title=title,
        message=message,
        tone=data.tone,
        actions=data.actions,
        deadline_at=data.deadline_at,
        deadline_kind=data.deadline_kind,
        deadline_action=data.deadline_action,
        requires_active_notification=data.requires_active_notification,
        next_event=next_event,
        recovery=recovery,
        active_notification=active_notification,
        stale_after_seconds=data.stale_after_seconds,
    )


def _promise_copy(
    data: PaymentPromiseData,
    *,
    order_status: str,
    copy: CopyCatalog,
) -> tuple[str, str, str, str, str]:
    """Return (title, message, next_event, recovery, active_notification)."""
    spec = _PROMISE_COPY.get(data.state)
    if spec is None:
        return "", "", "", "", ""
    (
        title_key, title_fb, message_key, message_fb,
        next_key, next_fb, recovery_key, recovery_fb, active_key, active_fb,
    ) = spec
    title = copy.title(title_key, title_fb) if title_key else title_fb
    message = copy.message(message_key, message_fb) if message_key else message_fb
    if data.state == "card_authorized":
        next_event = _card_authorized_next(order_status, copy)
    else:
        next_event = copy.message(next_key, next_fb) if next_key else next_fb
    recovery = copy.message(recovery_key, recovery_fb) if recovery_key else recovery_fb
    active_notification = copy.message(active_key, active_fb) if active_key else active_fb
    return title, message, next_event, recovery, active_notification


def _card_authorized_next(order_status: str, copy: CopyCatalog) -> str:
    if order_status == "new":
        return copy.message(
            "PAYMENT_PROMISE_CARD_AUTHORIZED_NEXT_NEW",
            "O estabelecimento vai conferir a disponibilidade.",
        )
    return copy.message(
        "PAYMENT_PROMISE_CARD_AUTHORIZED_NEXT_CONFIRMED",
        "Assim que a confirmação financeira terminar, seguimos com o pedido.",
    )


__all__ = [
    "PaymentProjection",
    "PaymentPromiseProjection",
    "PaymentStatusProjection",
    "build_payment",
    "build_payment_status",
    "present_payment",
    "present_payment_status",
    "promise_has_pending_payment_action",
]
