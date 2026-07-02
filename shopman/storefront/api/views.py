from __future__ import annotations

import logging

from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from shopman.utils.phone import normalize_phone

from shopman.shop.services import checkout as checkout_service
from shopman.shop.services import sessions as session_service
from shopman.storefront.cart import CHANNEL_REF
from shopman.storefront.services import orders as order_service

from .serializers import (
    CheckoutResponseSerializer,
    CheckoutSerializer,
    DetailSerializer,
)

logger = logging.getLogger(__name__)


CHECKOUT_RATE_LIMIT_RETRY_SECONDS = 60


def _cart_data(request):
    """Resolve the cart DATA projection for the current visitor (checkout commit).

    Reads the orchestrator read-side (``shop.projections.cart.CartProjection``).
    """
    from shopman.shop.projections.cart import build_cart

    return build_cart(request.session.get("cart_session_key"), CHANNEL_REF)


# Rate-limit MANUAL (is_ratelimited): só a tentativa que chega ao commit
# incrementa o contador — cliente corrigindo erro de formulário não pode
# tomar 429 no momento mais crítico do pedido.
class CheckoutView(APIView):
    """
    POST /api/v1/checkout/

    Commit the cart as an order.
    """

    permission_classes = [AllowAny]
    authentication_classes = [SessionAuthentication]
    serializer_class = CheckoutSerializer

    @extend_schema(
        tags=["checkout"],
        summary="Commit cart as order",
        request=CheckoutSerializer,
        responses={
            201: CheckoutResponseSerializer,
            400: DetailSerializer,
            429: DetailSerializer,
        },
    )
    def post(self, request):
        if self._rate_limited(request, increment=False):
            return self._rate_limited_response()

        serializer = CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Check cart has items
        cart = _cart_data(request)
        if cart.is_empty:
            return Response(
                {"detail": "Cart is empty."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        session_key = cart.session_key
        name = serializer.validated_data["name"]
        phone_raw = serializer.validated_data["phone"]
        notes = serializer.validated_data.get("notes", "")
        fulfillment_type = serializer.validated_data.get("fulfillment_type", "pickup")
        delivery_address = serializer.validated_data.get("delivery_address", "")
        saved_address_id = serializer.validated_data.get("saved_address_id")
        delivery_address_structured = serializer.validated_data.get("delivery_address_structured") or {}
        delivery_complement = serializer.validated_data.get("delivery_complement", "")
        delivery_instructions = serializer.validated_data.get("delivery_instructions", "")
        delivery_date = serializer.validated_data.get("delivery_date", "")
        delivery_time_slot = serializer.validated_data.get("delivery_time_slot", "")
        payment_method = serializer.validated_data.get("payment_method", "")
        use_loyalty = serializer.validated_data.get("use_loyalty", False)
        idempotency_key = serializer.validated_data.get("idempotency_key") or session_service.new_idempotency_key()

        if fulfillment_type != "delivery":
            saved_address_id = None
            delivery_address = ""
            delivery_address_structured = {}
            delivery_complement = ""
            delivery_instructions = ""

        if not delivery_date and (fulfillment_type == "delivery" or delivery_time_slot):
            return Response(
                {"detail": "Escolha a data.", "field": "delivery_date"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Guard autoritativo: nunca confirmar pedido para um dia fechado
        # (fim de semana fora do expediente, feriado, férias coletivas). A UI
        # já evita oferecer, mas o commit não bloqueia data futura — então o
        # servidor é a última linha. Prometer dia fechado seria gravíssimo.
        if delivery_date:
            from datetime import date as _date

            from shopman.shop.services import business_calendar

            try:
                _parsed_date = _date.fromisoformat(delivery_date)
            except ValueError:
                _parsed_date = None
            if _parsed_date is not None:
                if not business_calendar.is_open_on(_parsed_date):
                    message = "Estamos fechados nesse dia. Escolha outra data."
                    return Response(
                        {"detail": message, "field": "delivery_date", "errors": {"delivery_date": message}},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                # Eixo de HORA: dia operante mas já encerrado hoje (entrega e
                # retirada). is_open_on é cego à hora — esta é a última linha.
                _state = business_calendar.current_business_state()
                _today = _state.resolved_at.date() if _state.resolved_at else None
                if _parsed_date == _today and _state.closure_source == "after_close":
                    message = "Já encerramos o atendimento de hoje. Escolha outra data."
                    return Response(
                        {"detail": message, "field": "delivery_date", "errors": {"delivery_date": message}},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

        if fulfillment_type == "delivery" and delivery_time_slot and delivery_date:
            # Aba antiga do checkout: slot de entrega de HOJE que já passou
            # não vira pedido impossível para a operação.
            slot_error = _delivery_slot_in_past_error(delivery_time_slot, delivery_date)
            if slot_error:
                return Response(
                    {
                        "detail": slot_error,
                        "field": "delivery_time_slot",
                        "errors": {"delivery_time_slot": slot_error},
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        if fulfillment_type == "pickup":
            from shopman.storefront.services.pickup_slots import validate_pickup_slot_selection

            try:
                now_local = timezone.localtime().time().replace(second=0, microsecond=0)
            except (ValueError, KeyError):
                now_local = None
            slot_error = validate_pickup_slot_selection(
                delivery_time_slot,
                delivery_date=delivery_date,
                cart_skus=[str(line.sku) for line in cart.lines if line.sku],
                now=now_local,
            )
            if slot_error:
                return Response(
                    {
                        "detail": slot_error,
                        "field": "delivery_time_slot",
                        "errors": {"delivery_time_slot": slot_error},
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        if fulfillment_type == "delivery" and saved_address_id:
            saved_payload, saved_error = _saved_address_payload(request, saved_address_id)
            if saved_error:
                return Response(saved_error, status=status.HTTP_400_BAD_REQUEST)
            if saved_payload:
                delivery_address = delivery_address or saved_payload["formatted_address"]
                delivery_address_structured = {
                    **saved_payload["structured"],
                    **_clean_structured_address(delivery_address_structured),
                }

        if fulfillment_type == "delivery":
            structured = _clean_structured_address(delivery_address_structured)
            delivery_address = delivery_address or str(structured.get("formatted_address") or "")
            if not delivery_address.strip():
                return Response(
                    {
                        "detail": "Informe o endereço de entrega.",
                        "field": "delivery_address",
                        "errors": {"delivery_address": "Informe o endereço de entrega."},
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            delivery_address_structured = structured

        phone = normalize_phone(phone_raw) or phone_raw

        checkout_data = {
            "customer": {"name": name, "phone": phone},
            "fulfillment_type": fulfillment_type,
            # Omotenashi: lembrar escolhas é o default; toggle desmarcado → False.
            # (Endereço novo é salvo sempre, independente disto.)
            "save_as_default": serializer.validated_data.get("save_as_default", True),
        }
        if notes:
            checkout_data["order_notes"] = notes
        if delivery_address:
            checkout_data["delivery_address"] = delivery_address
        if saved_address_id:
            checkout_data["saved_address_id"] = saved_address_id
        if fulfillment_type == "delivery":
            structured = _clean_structured_address(delivery_address_structured)
            if delivery_complement:
                structured["complement"] = delivery_complement
            if delivery_instructions:
                structured["delivery_instructions"] = delivery_instructions
            if structured:
                checkout_data["delivery_address_structured"] = structured
        if delivery_date:
            checkout_data["delivery_date"] = delivery_date
        if delivery_time_slot:
            checkout_data["delivery_time_slot"] = delivery_time_slot
        if payment_method in {"pix", "card"}:
            checkout_data["payment"] = {"method": payment_method}
        elif payment_method == "cash":
            # Dinheiro também é método de pagamento: sem isso o operador não
            # sabe como cobrar — e o troco pedido pelo cliente se perdia.
            from shopman.storefront.intents.checkout import parse_change_for

            payment_data = {"method": "cash"}
            change_for_q = parse_change_for(serializer.validated_data.get("change_for", ""))
            if fulfillment_type == "delivery" and change_for_q:
                payment_data["change_for_q"] = change_for_q
            checkout_data["payment"] = payment_data

        # Presente (entrega para terceiro) — integridade antes do commit.
        from shopman.storefront.intents.gift import build_gift_data

        gift_data, gift_errors = build_gift_data(
            is_gift=serializer.validated_data.get("is_gift", False),
            fulfillment_type=fulfillment_type,
            recipient_name=serializer.validated_data.get("recipient_name", ""),
            recipient_phone=serializer.validated_data.get("recipient_phone", ""),
            gift_message=serializer.validated_data.get("gift_message", ""),
            hide_values=serializer.validated_data.get("gift_hide_values", False),
        )
        if gift_errors:
            field, message = next(iter(gift_errors.items()))
            return Response(
                {"detail": message, "field": field, "errors": gift_errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if gift_data:
            checkout_data.update(gift_data)

        # Sempre gravar a chave: desmarcar o toggle precisa LIMPAR um resgate
        # aplicado numa tentativa anterior da mesma sessão (senão o desconto
        # stale sobrevive ao commit).
        checkout_data["loyalty"] = {}
        if use_loyalty:
            try:
                from shopman.shop.projections import checkout_context

                customer_info = getattr(request, "customer", None)
                loyalty_balance_q = checkout_context.loyalty_balance(
                    customer_info.uuid if customer_info else None
                )
                if loyalty_balance_q > 0:
                    checkout_data["loyalty"] = {"redeem_points_q": loyalty_balance_q}
            except Exception:
                logger.debug("views.post degraded; using fallback", exc_info=True)
                pass

        # Passou por todas as validações: agora sim a tentativa CONTA.
        if self._rate_limited(request, increment=True):
            return self._rate_limited_response()

        try:
            result = checkout_service.process(
                session_key=session_key,
                channel_ref=CHANNEL_REF,
                data=checkout_data,
                idempotency_key=idempotency_key,
                expected_total_q=serializer.validated_data.get("expected_total_q"),
            )
        except Exception as exc:
            logger.debug("views.post degraded; using fallback", exc_info=True)
            mapped = checkout_service.map_checkout_error(exc)
            if mapped:
                field, message = next(iter(mapped.items()))
                return Response(
                    {"detail": message, "field": field, "errors": mapped},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            order_error = checkout_service.map_order_error(exc)
            if order_error is not None:
                return Response(
                    {
                        "detail": order_error.detail,
                        "error_code": order_error.error_code,
                        "context": order_error.context,
                    },
                    status=order_error.http_status,
                )
            raise

        # Clear cart
        order_service.grant_order_access(request, result.order_ref)
        request.session.pop("cart_session_key", None)
        next_url = f"/tracking/{result.order_ref}"
        if payment_method in {"pix", "card"}:
            next_url = f"/pedido/{result.order_ref}/pagamento"
            if payment_method == "pix" and checkout_service.starts_payment_after_store_confirmation(CHANNEL_REF):
                next_url = f"/tracking/{result.order_ref}"

        data = CheckoutResponseSerializer(
            {
                "order_ref": result.order_ref,
                "status": result.status,
                "next_url": next_url,
            }
        ).data
        return Response(data, status=status.HTTP_201_CREATED)

    @staticmethod
    def _rate_limited(request, *, increment: bool) -> bool:
        from django_ratelimit.core import is_ratelimited

        return is_ratelimited(
            request,
            group="storefront.checkout",
            key="user_or_ip",
            rate="3/m",
            method="POST",
            increment=increment,
        )

    @staticmethod
    def _rate_limited_response() -> Response:
        return Response(
            {
                "detail": "Muitas tentativas. Aguarde alguns minutos.",
                "error_code": "rate_limited",
                "retry_after_seconds": CHECKOUT_RATE_LIMIT_RETRY_SECONDS,
            },
            status=status.HTTP_429_TOO_MANY_REQUESTS,
            headers={"Retry-After": str(CHECKOUT_RATE_LIMIT_RETRY_SECONDS)},
        )


def _delivery_slot_in_past_error(slot: str, delivery_date: str) -> str | None:
    """Slot "HH:MM-HH:MM" de HOJE cujo fim já passou → erro acionável."""
    import re
    from datetime import date as _date

    match = re.match(r"^\s*(\d{1,2}):(\d{2})\s*[-–]\s*(\d{1,2}):(\d{2})\s*$", slot or "")
    if not match:
        return None  # formato livre (ex.: "manhã") — sem eixo de hora para validar
    try:
        if _date.fromisoformat(delivery_date) != timezone.localdate():
            return None
    except ValueError:
        return None
    start = (int(match.group(1)), int(match.group(2)))
    end = (int(match.group(3)), int(match.group(4)))
    if end <= start:
        # Slot cruza a meia-noite (ex.: 22:00-02:00): o fim é amanhã, então
        # nunca "já passou" hoje. Sem eixo confiável — não bloquear.
        return None
    now_local = timezone.localtime()
    if (now_local.hour, now_local.minute) >= end:
        return "Esse horário já passou. Escolha outro horário de entrega."
    return None


_STRUCTURED_ADDRESS_FIELDS = (
    "formatted_address",
    "route",
    "street_number",
    "neighborhood",
    "city",
    "state_code",
    "postal_code",
    "country",
    "country_code",
    "latitude",
    "longitude",
    "place_id",
    "complement",
    "delivery_instructions",
)


def _clean_structured_address(value: dict | None) -> dict:
    if not isinstance(value, dict):
        return {}
    cleaned: dict = {}
    for field in _STRUCTURED_ADDRESS_FIELDS:
        raw = value.get(field)
        if raw is None or raw == "":
            continue
        cleaned[field] = raw
    return cleaned


def _saved_address_payload(request, address_id: int | None) -> tuple[dict | None, dict | None]:
    if not address_id:
        return None, None
    from shopman.shop.services import account as account_service
    from shopman.storefront.identity import get_authenticated_customer

    customer = get_authenticated_customer(request)
    if not customer:
        return None, {"detail": "Entre novamente para usar este endereço.", "field": "saved_address_id"}
    if account_service.address_belongs_to_other_customer(customer.ref, address_id):
        return None, {"detail": "Endereço não encontrado.", "field": "saved_address_id"}
    address = account_service.get_address(customer.ref, address_id)
    if not address:
        return None, {"detail": "Endereço não encontrado.", "field": "saved_address_id"}
    structured = _clean_structured_address({
        "formatted_address": address.formatted_address,
        "route": getattr(address, "route", "") or "",
        "street_number": getattr(address, "street_number", "") or "",
        "neighborhood": getattr(address, "neighborhood", "") or "",
        "city": getattr(address, "city", "") or "",
        "state_code": getattr(address, "state_code", "") or "",
        "postal_code": getattr(address, "postal_code", "") or "",
        "latitude": getattr(address, "latitude", None),
        "longitude": getattr(address, "longitude", None),
        "place_id": getattr(address, "place_id", "") or "",
        "complement": getattr(address, "complement", "") or "",
        "delivery_instructions": getattr(address, "delivery_instructions", "") or "",
    })
    return {
        "formatted_address": address.formatted_address,
        "structured": structured,
    }, None
