"""Storefront Payment API - Nuxt-facing payment contract."""

from __future__ import annotations

from django.http import Http404
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django_ratelimit.decorators import ratelimit
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.shop.omotenashi import resolve_copy
from shopman.shop.services import remote_mutations
from shopman.storefront.api.actions import retry_after_action
from shopman.storefront.api.projections import projection_data
from shopman.storefront.presentation import build_payment, build_payment_status
from shopman.storefront.services import orders as order_service


def _tracking_url(ref: str) -> str:
    return f"/tracking/{ref}"


PAYMENT_RATE_LIMIT_RETRY_SECONDS = 30


def _rate_limited_response() -> Response:
    return Response(
        {
            "detail": "Muitas tentativas. Aguarde um instante.",
            "error_code": "rate_limited",
            "retry_after_seconds": PAYMENT_RATE_LIMIT_RETRY_SECONDS,
            "actions": [retry_after_action(PAYMENT_RATE_LIMIT_RETRY_SECONDS)],
        },
        status=status.HTTP_429_TOO_MANY_REQUESTS,
        headers={"Retry-After": str(PAYMENT_RATE_LIMIT_RETRY_SECONDS)},
    )


def _is_digital_payment(order) -> bool:
    payment = (order.data or {}).get("payment") or {}
    return str(payment.get("method") or "").lower() in {"pix", "card"}


def _payment_copy() -> dict:
    """Copy estática da tela de pagamento (chrome + UI de PIX/cartão), resolvida do
    registro omotenashi (configurável no Admin). O painel de status vem do `promise`
    (fiado à parte); aqui só o que a tela hardcodava. O Vue consome com fallback."""
    def title(key: str, fb: str) -> str:
        return resolve_copy(key, moment="*", audience="*").title or fb

    def message(key: str, fb: str) -> str:
        return resolve_copy(key, moment="*", audience="*").message or fb

    return {
        "order_ref_label": title("PAYMENT_ORDER_REF_LABEL", "Pedido"),
        "total_label": title("PAYMENT_TOTAL_LABEL", "Total"),
        "meta_description": message("PAYMENT_PAGE_META_DESCRIPTION", "Pague seu pedido para seguirmos com o preparo"),
        "card_intro": message("PAYMENT_CARD_INTRO", "Conclua o pagamento no ambiente seguro do Stripe. A confirmação é automática. Volte aqui se quiser acompanhar seu pedido."),
        "card_security_note": message("PAYMENT_CARD_SECURITY_NOTE", "Pagamento processado por provedor seguro. Nós não recebemos os dados do seu cartão."),
        "pix_instruction": message("PAYMENT_PIX_INSTRUCTION", "Escaneie o QR Code ou copie o código Pix abaixo."),
        "pix_copy_label": title("PAYMENT_PIX_COPY_LABEL", "Copia e cola PIX"),
        "pix_copy_btn": title("PAYMENT_PIX_COPY_BTN", "Copiar código"),
        "pix_copied": title("PAYMENT_PIX_COPIED", "Código PIX copiado."),
        "pix_expires_label": message("PAYMENT_PIX_EXPIRES_LABEL", "Tempo para pagar"),
    }


def _payment_has_pending_payment_action(payment: dict | None) -> bool:
    if not payment:
        return False
    promise = payment.get("promise") or {}
    actions = promise.get("actions") or []
    return any(
        action.get("enabled") is not False
        and action.get("ref") != "track_order"
        for action in actions
        if isinstance(action, dict)
    )


@method_decorator(never_cache, name="dispatch")
@method_decorator(ratelimit(key="user_or_ip", rate="90/m", method="GET", block=False), name="dispatch")
class OrderPaymentView(APIView):
    """GET /api/v1/payment/<ref>/ - payment projection for Nuxt."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, ref: str):
        if getattr(request, "limited", False):
            return _rate_limited_response()

        try:
            order = order_service.get_accessible_order(request, ref)
        except Http404:
            return Response({"detail": "Pedido não encontrado."}, status=404)

        order_service.resolve_timeouts_if_due(order)
        if order_service.is_cancelled(order) or order_service.payment_is_sufficient(order):
            return Response({"redirect_url": _tracking_url(ref), "payment": None})

        intent_ready = order_service.ensure_payment_intent(order)
        if order_service.payment_is_sufficient(order):
            return Response({"redirect_url": _tracking_url(ref), "payment": None})
        if not intent_ready and not (_is_digital_payment(order) and order.status == "confirmed"):
            return Response({
                "redirect_url": _tracking_url(ref),
                "payment": None,
                "reason": "waiting_store_confirmation",
            })

        payment = projection_data(build_payment(order))
        payment["status_url"] = f"/api/v1/payment/{ref}/status/"
        payment["tracking_url"] = _tracking_url(ref)
        if not _payment_has_pending_payment_action(payment):
            return Response({
                "redirect_url": _tracking_url(ref),
                "payment": None,
                "reason": "no_payment_action",
            })
        return Response({
            "redirect_url": None,
            "intent_ready": bool(intent_ready),
            "payment": payment,
            "copy": _payment_copy(),
        })


@method_decorator(never_cache, name="dispatch")
@method_decorator(ratelimit(key="user_or_ip", rate="120/m", method="GET", block=False), name="dispatch")
class OrderPaymentStatusView(APIView):
    """GET /api/v1/payment/<ref>/status/ - polling payment state."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, ref: str):
        if getattr(request, "limited", False):
            return _rate_limited_response()

        try:
            order = order_service.get_accessible_order(request, ref)
        except Http404:
            return Response({"detail": "Pedido não encontrado."}, status=404)

        order_service.resolve_timeouts_if_due(order)
        status = projection_data(build_payment_status(order))
        status["redirect_url"] = _tracking_url(ref)
        return Response(status)


@method_decorator(never_cache, name="dispatch")
@method_decorator(ratelimit(key="user_or_ip", rate="30/m", method="POST", block=False), name="dispatch")
class OrderPaymentMockConfirmView(APIView):
    """POST /api/v1/payment/<ref>/mock-confirm/ - DEBUG-only mock payment confirmation."""

    permission_classes = [AllowAny]
    authentication_classes = [SessionAuthentication]

    def post(self, request, ref: str):
        if getattr(request, "limited", False):
            return _rate_limited_response()

        from shopman.storefront.presentation.payment import mock_payment_enabled

        if not mock_payment_enabled():
            raise Http404
        try:
            order = order_service.get_accessible_order(request, ref)
        except Http404:
            return Response({"detail": "Pedido não encontrado."}, status=404)

        key = remote_mutations.idempotency_key_from_request(
            request,
            fallback=f"mock-confirm:{ref}",
        )

        def execute_mock_confirm() -> tuple[dict, int]:
            order_service.resolve_timeouts_if_due(order)
            if not order_service.payment_is_sufficient(order):
                if order_service.ensure_payment_intent(order):
                    order_service.mock_confirm_payment(order)
                    order_service.resolve_confirmation_timeout_if_due(order)
            return {"redirect_url": _tracking_url(ref)}, status.HTTP_200_OK

        try:
            result = remote_mutations.run_idempotent_mutation(
                scope=f"payment-mock-confirm:{ref}",
                key=key,
                execute=execute_mock_confirm,
            )
        except remote_mutations.RemoteMutationInProgress:
            return Response(
                {"detail": "Confirmação teste já está em andamento.", "error_code": "mutation_in_progress"},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(result.response_body, status=result.response_code)
