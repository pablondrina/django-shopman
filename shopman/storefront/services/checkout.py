"""Storefront checkout service facade."""

from shopman.shop.services.checkout import CheckoutResult, process, process_ops


def map_checkout_error(exc: Exception) -> dict[str, str] | None:
    from django.core.exceptions import ValidationError as DjangoValidationError
    from shopman.orderman.exceptions import ValidationError as OrderingValidationError

    if isinstance(exc, OrderingValidationError):
        field = "delivery_address" if exc.code == "delivery_zone_not_covered" else "checkout"
        return {field: exc.message}
    if isinstance(exc, DjangoValidationError):
        msgs = exc.messages if hasattr(exc, "messages") else [str(exc)]
        return {"checkout": msgs[0] if msgs else str(exc)}
    return None


def ensure_customer(intent) -> None:
    import uuid as uuid_lib

    from django.db import IntegrityError
    from shopman.guestman.services import customer as customer_service

    customer_obj = customer_service.get_by_phone(intent.customer_phone)
    if customer_obj:
        if intent.customer_name and not customer_obj.first_name:
            customer_obj.first_name = intent.customer_name
            customer_obj.save(update_fields=["first_name"])
        return

    try:
        customer_service.create(
            ref=f"WEB-{str(uuid_lib.uuid4())[:8].upper()}",
            first_name=intent.customer_name,
            phone=intent.customer_phone,
        )
    except IntegrityError:
        pass


def persist_new_address(intent) -> None:
    if intent.fulfillment_type != "delivery":
        return
    if intent.saved_address_id:
        return
    if not intent.delivery_address:
        return

    from shopman.guestman.services import address as address_service
    from shopman.guestman.services import customer as customer_service

    customer_obj = customer_service.get_by_phone(intent.customer_phone)
    if not customer_obj:
        return

    if address_service.has_address(customer_obj.ref, intent.delivery_address):
        return

    structured = intent.delivery_address_structured or {}

    lat = structured.get("latitude")
    lng = structured.get("longitude")
    coordinates = (float(lat), float(lng)) if lat and lng else None

    components = {
        "street_number": structured.get("street_number", ""),
        "route": structured.get("route", ""),
        "neighborhood": structured.get("neighborhood", ""),
        "city": structured.get("city", ""),
        "state_code": structured.get("state_code", ""),
        "postal_code": structured.get("postal_code", ""),
    }

    is_first = not address_service.has_any_address(customer_obj.ref)

    address_service.add_address(
        customer_ref=customer_obj.ref,
        label="other",
        label_custom="Entrega",
        formatted_address=intent.delivery_address,
        place_id=structured.get("place_id") or None,
        components=components,
        coordinates=coordinates,
        complement=structured.get("complement", ""),
        delivery_instructions=structured.get("delivery_instructions", ""),
        is_default=is_first,
    )


def save_defaults(intent, *, order_ref: str, enabled: bool) -> None:
    if not enabled:
        return

    from shopman.guestman.services import customer as customer_service

    from shopman.storefront.services.checkout_defaults import CheckoutDefaultsService

    customer_obj = customer_service.get_by_phone(intent.customer_phone)
    if not customer_obj:
        return

    defaults_data: dict = {
        "fulfillment_type": intent.fulfillment_type,
        "payment_method": intent.payment_method,
    }
    if intent.fulfillment_type == "delivery":
        if intent.saved_address_id:
            defaults_data["delivery_address_id"] = intent.saved_address_id
        if intent.delivery_time_slot:
            defaults_data["delivery_time_slot"] = intent.delivery_time_slot
    if intent.notes:
        defaults_data["order_notes"] = intent.notes

    CheckoutDefaultsService.save_defaults(
        customer_ref=customer_obj.ref,
        channel_ref=intent.channel_ref,
        data=defaults_data,
        source=f"order:{order_ref}",
    )


def order_has_payment_error(order_ref: str) -> bool:
    from shopman.orderman.models import Order

    order = Order.objects.get(ref=order_ref)
    return bool((order.data or {}).get("payment", {}).get("error"))


def get_open_cart_session(*, session_key: str, channel_ref: str):
    from shopman.orderman.models import Session

    return Session.objects.get(
        session_key=session_key,
        channel_ref=channel_ref,
        state="open",
    )


def simulate_ifood_order(cart_session):
    from shopman.shop.services import ifood_ingest
    from shopman.storefront.services.ifood_simulation import session_to_ifood_payload

    payload = session_to_ifood_payload(cart_session)
    return ifood_ingest.ingest(payload)


def close_cart_session(cart_session) -> None:
    cart_session.state = "closed"
    cart_session.save(update_fields=["state", "updated_at"])


__all__ = [
    "CheckoutResult",
    "close_cart_session",
    "ensure_customer",
    "get_open_cart_session",
    "map_checkout_error",
    "order_has_payment_error",
    "persist_new_address",
    "process",
    "process_ops",
    "save_defaults",
    "simulate_ifood_order",
]
