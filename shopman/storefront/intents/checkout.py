"""Checkout intent extraction.

interpret_checkout() absorbs all domain logic from CheckoutView.post():
phone normalization, name resolution, address/payment/stock validation,
preorder/slot validation, and checkout_data assembly.

Helper functions accept raw data so they are testable without a request object.
"""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from shopman.shop.services import checkout_context
from shopman.shop.services import sessions as session_service

from ._phone import normalize_phone_input as _try_normalize_phone
from .types import CheckoutIntent, IntentResult

# ── Public API ────────────────────────────────────────────────────────────────


def interpret_checkout(request, channel_ref: str) -> IntentResult:
    """Extract all domain logic from a checkout POST into a typed intent.

    Steps:
     1. Parse raw form data
     2. Validate and normalize phone
     3. Resolve customer name
     4. Resolve saved address
     5. Resolve and validate payment method
     6. Check minimum order (delivery only)
     7. Validate address/form
     8. Check repricing (non-blocking)
     9. Check stock
    10. Validate preorder
    11. Validate slot
    12. Build checkout_data
    13. Resolve loyalty
    14. Generate idempotency key
    """
    from ..cart import CartService

    session_key = request.session.get("cart_session_key", "")
    post = request.POST

    # ── Step 1: Parse raw form data ───────────────────────────────────────
    name_raw = post.get("name", "").strip()
    phone_raw = post.get("phone", "").strip()
    notes = post.get("notes", "").strip()
    fulfillment_type = post.get("fulfillment_type", "pickup")
    delivery_address = post.get("delivery_address", "").strip()
    delivery_date = post.get("delivery_date", "").strip()
    delivery_time_slot = post.get("delivery_time_slot", "").strip()
    saved_address_id_raw = post.get("saved_address_id", "").strip()
    addr_data = _parse_address_data(post)
    if not delivery_address and addr_data.get("formatted_address"):
        delivery_address = addr_data["formatted_address"]

    form_data = _build_form_data(
        name_raw, phone_raw, notes, fulfillment_type, delivery_address,
        delivery_date, delivery_time_slot, saved_address_id_raw, addr_data,
        payment_method=post.get("payment_method", ""),
    )

    errors: dict[str, str] = {}

    # ── Step 2: Validate and normalize phone ──────────────────────────────
    phone = _try_normalize_phone(phone_raw)
    if not phone_raw:
        errors["phone"] = "Telefone é obrigatório."
    elif not phone:
        errors["phone"] = "Telefone inválido. Informe com DDD, ex: (43) 99999-9999"

    # ── Step 3: Resolve customer name ─────────────────────────────────────
    name = name_raw
    if phone and not errors.get("phone"):
        if not name:
            existing_name = checkout_context.customer_name_by_phone(phone)
            if existing_name:
                name = existing_name
            else:
                errors["name"] = "Nome é obrigatório."
    elif not name:
        errors["name"] = "Nome é obrigatório."

    # ── Step 4: Resolve saved address ─────────────────────────────────────
    saved_address_id: int | None = None
    if saved_address_id_raw and fulfillment_type == "delivery" and not delivery_address:
        resolved = _resolve_saved_address(request, saved_address_id_raw)
        if resolved:
            delivery_address = resolved
            try:
                saved_address_id = int(saved_address_id_raw)
            except ValueError:
                pass
    elif saved_address_id_raw:
        try:
            saved_address_id = int(saved_address_id_raw)
        except ValueError:
            pass

    # ── Step 5: Resolve and validate payment method ───────────────────────
    payment_methods = checkout_context.payment_methods(channel_ref)
    chosen_method = _resolve_payment_method(post, payment_methods)
    form_data["payment_method"] = chosen_method

    if chosen_method not in payment_methods:
        errors["payment_method"] = "Método de pagamento indisponível. Selecione outro."

    # ── Step 6: Check minimum order (delivery only) ───────────────────────
    cart = CartService.get_cart(request)
    if fulfillment_type == "delivery":
        from shopman.shop.services.storefront_context import minimum_order_progress
        warning = minimum_order_progress(cart["subtotal_q"])
        if warning:
            errors["minimum_order"] = (
                f"Faltam {warning['remaining_display']} para atingir o pedido mínimo de "
                f"{warning['minimum_display']}."
            )

    # ── Step 7: Validate address/form ─────────────────────────────────────
    address_errors = _validate_checkout_form(
        fulfillment_type=fulfillment_type,
        delivery_address=delivery_address,
        addr_data=addr_data,
        payment_method=chosen_method,
    )
    errors.update(address_errors)

    # ── Step 8: Check repricing (non-blocking) ────────────────────────────
    repricing_warnings = checkout_context.repricing_warnings(cart)

    # ── Step 9: Check stock ───────────────────────────────────────────────
    from shopman.shop.services.order_helpers import parse_commitment_date
    commitment_date = parse_commitment_date(delivery_date)
    stock_errors, stock_check_unavailable = checkout_context.cart_stock_errors(
        session_key=session_key,
        cart=cart,
        channel_ref=channel_ref,
        target_date=commitment_date,
    )
    if stock_errors:
        errors["stock"] = stock_errors[0]["message"]

    if errors:
        return IntentResult(
            intent=None,
            errors=errors,
            form_data=form_data,
            repricing_warnings=repricing_warnings,
        )

    # ── Step 10: Validate preorder ────────────────────────────────────────
    if delivery_date:
        preorder_errors = _validate_preorder(delivery_date)
        errors.update(preorder_errors)

    # ── Step 11: Validate slot ────────────────────────────────────────────
    slot_errors = _validate_slot(delivery_time_slot, fulfillment_type, delivery_date)
    errors.update(slot_errors)

    if errors:
        return IntentResult(
            intent=None,
            errors=errors,
            form_data=form_data,
            repricing_warnings=repricing_warnings,
        )

    # ── Step 12: Build checkout_data ──────────────────────────────────────
    checkout_data: dict = {
        "customer": {"name": name, "phone": phone},
        "fulfillment_type": fulfillment_type,
    }
    if stock_check_unavailable:
        checkout_data["stock_check_unavailable"] = True
    if notes:
        checkout_data["order_notes"] = notes
    if fulfillment_type == "delivery" and delivery_address:
        checkout_data["delivery_address"] = delivery_address
        if addr_data.get("formatted_address"):
            checkout_data["delivery_address_structured"] = {
                k: v for k, v in addr_data.items() if v
            }
    if delivery_date:
        checkout_data["delivery_date"] = delivery_date
    if delivery_time_slot:
        checkout_data["delivery_time_slot"] = delivery_time_slot
    if chosen_method in ("pix", "card"):
        checkout_data["payment"] = {"method": chosen_method}

    # ── Step 13: Resolve loyalty ──────────────────────────────────────────
    loyalty_redeem = post.get("use_loyalty") == "true"
    loyalty_balance_q = 0
    if loyalty_redeem:
        customer_info = getattr(request, "customer", None)
        loyalty_balance_q = checkout_context.loyalty_balance(
            customer_info.uuid if customer_info else None
        )
        if loyalty_balance_q > 0:
            checkout_data["loyalty"] = {"redeem_points_q": loyalty_balance_q}
        else:
            loyalty_redeem = False

    # ── Step 14: Generate idempotency key ─────────────────────────────────
    idempotency_key = session_service.new_idempotency_key()

    intent = CheckoutIntent(
        session_key=session_key,
        channel_ref=channel_ref,
        customer_name=name,
        customer_phone=phone,
        fulfillment_type=fulfillment_type,
        payment_method=chosen_method,
        delivery_address=delivery_address or None,
        delivery_address_structured=(
            {k: v for k, v in addr_data.items() if v}
            if addr_data.get("formatted_address") else None
        ),
        saved_address_id=saved_address_id,
        delivery_date=delivery_date or None,
        delivery_time_slot=delivery_time_slot or None,
        notes=notes or None,
        loyalty_redeem=loyalty_redeem,
        loyalty_balance_q=loyalty_balance_q,
        stock_check_unavailable=stock_check_unavailable,
        idempotency_key=idempotency_key,
        checkout_data=checkout_data,
    )

    return IntentResult(
        intent=intent,
        errors={},
        form_data=form_data,
        repricing_warnings=repricing_warnings,
    )


# ── Payment helpers ───────────────────────────────────────────────────────────


def _resolve_payment_method(post, payment_methods: list[str]) -> str:
    if len(payment_methods) > 1:
        chosen = post.get("payment_method", payment_methods[0])
        return chosen if chosen in payment_methods else payment_methods[0]
    return payment_methods[0] if payment_methods else "cash"


# ── Form parsing helpers ──────────────────────────────────────────────────────


def _parse_address_data(post) -> dict:
    addr_data = {
        "route": post.get("route", "").strip(),
        "street_number": post.get("street_number", "").strip(),
        "complement": post.get("complement", "").strip(),
        "neighborhood": post.get("neighborhood", "").strip(),
        "city": post.get("city", "").strip(),
        "state_code": post.get("state_code", "").strip(),
        "postal_code": post.get("postal_code", "").strip(),
        "place_id": post.get("place_id", "").strip(),
        "formatted_address": post.get("formatted_address", "").strip(),
        "delivery_instructions": post.get("delivery_instructions", "").strip(),
        "is_verified": post.get("is_verified", "") == "true",
    }
    try:
        addr_data["latitude"] = float(post.get("latitude", ""))
    except (ValueError, TypeError):
        addr_data["latitude"] = None
    try:
        addr_data["longitude"] = float(post.get("longitude", ""))
    except (ValueError, TypeError):
        addr_data["longitude"] = None
    return addr_data


def _build_form_data(
    name: str,
    phone_raw: str,
    notes: str,
    fulfillment_type: str,
    delivery_address: str,
    delivery_date: str,
    delivery_time_slot: str,
    saved_address_id_raw: str,
    addr_data: dict,
    *,
    payment_method: str = "",
) -> dict:
    return {
        "name": name,
        "phone": phone_raw,
        "notes": notes,
        "fulfillment_type": fulfillment_type,
        "delivery_address": delivery_address,
        "delivery_date": delivery_date,
        "delivery_time_slot": delivery_time_slot,
        "saved_address_id": saved_address_id_raw,
        "payment_method": payment_method,
        "route": addr_data.get("route", ""),
        "street_number": addr_data.get("street_number", ""),
        "complement": addr_data.get("complement", ""),
        "neighborhood": addr_data.get("neighborhood", ""),
        "city": addr_data.get("city", ""),
        "state_code": addr_data.get("state_code", ""),
        "postal_code": addr_data.get("postal_code", ""),
        "delivery_instructions": addr_data.get("delivery_instructions", ""),
        "formatted_address": addr_data.get("formatted_address", ""),
        "place_id": addr_data.get("place_id", ""),
    }


# ── Address helpers ───────────────────────────────────────────────────────────


def _resolve_saved_address(request, saved_address_id_raw: str) -> str:
    """Look up a saved address by id and return its flat string, or empty string."""
    customer_info = getattr(request, "customer", None)
    if customer_info is None:
        return ""
    return checkout_context.saved_address_text(
        customer_uuid=customer_info.uuid,
        address_id_raw=saved_address_id_raw,
    )


# ── Validation helpers ────────────────────────────────────────────────────────


def _validate_checkout_form(
    *,
    fulfillment_type: str,
    delivery_address: str,
    addr_data: dict,
    payment_method: str,
) -> dict[str, str]:
    errors: dict[str, str] = {}
    if fulfillment_type == "delivery":
        has_route = bool((addr_data.get("route") or "").strip())
        has_number = bool((addr_data.get("street_number") or "").strip())
        has_saved_flat = bool(delivery_address)
        if not has_saved_flat and not has_route:
            errors["delivery_address"] = (
                "Escolha um endereço salvo ou adicione um novo para entregarmos."
            )
        if has_route and not has_number:
            errors["street_number"] = "Falta só o número do endereço."
    if not payment_method:
        errors["payment_method"] = "Selecione uma forma de pagamento."
    return errors


def _validate_preorder(delivery_date: str) -> dict[str, str]:
    from datetime import date as date_type
    errors: dict[str, str] = {}
    today = timezone.now().date()
    try:
        chosen_date = date_type.fromisoformat(delivery_date)
    except ValueError:
        return errors

    if chosen_date < today:
        errors["delivery_date"] = "Não é possível encomendar para uma data passada."
        return errors

    max_preorder_days, closed_dates = checkout_context.preorder_config()

    max_date = today + timedelta(days=max_preorder_days)
    if chosen_date > max_date:
        errors["delivery_date"] = f"Data máxima permitida: {max_date.strftime('%d/%m/%Y')}"
        return errors

    is_closed, closed_label = _is_closed_date(chosen_date, closed_dates)
    if is_closed:
        suffix = f": {closed_label}" if closed_label else ""
        errors["delivery_date"] = f"Fechado{suffix} — escolha outra data."
    return errors


def _validate_slot(
    delivery_time_slot: str,
    fulfillment_type: str,
    delivery_date: str,
) -> dict[str, str]:
    from datetime import date as date_type
    from datetime import time as time_type

    from shopman.storefront.services.pickup_slots import _find_slot_by_ref, get_slots

    errors: dict[str, str] = {}
    if fulfillment_type != "pickup":
        return errors

    if not delivery_time_slot:
        errors["delivery_time_slot"] = "Selecione um horário de retirada."
        return errors

    slots = get_slots()
    slot = _find_slot_by_ref(slots, delivery_time_slot)
    if slot is None:
        errors["delivery_time_slot"] = "Horário de retirada inválido."
        return errors

    today = timezone.localtime().date()
    is_today = True
    if delivery_date:
        try:
            is_today = date_type.fromisoformat(delivery_date) == today
        except ValueError:
            is_today = True

    if is_today:
        now_local = timezone.localtime()
        try:
            parts = slot["starts_at"].split(":")
            slot_time = time_type(int(parts[0]), int(parts[1]))
            current_time = now_local.time().replace(second=0, microsecond=0)
            if slot_time <= current_time:
                errors["delivery_time_slot"] = "Este horário já passou. Selecione um horário futuro."
        except (ValueError, KeyError):
            pass
    return errors


def _is_closed_date(date_obj, closed_dates: list) -> tuple[bool, str | None]:
    from datetime import date as date_type
    for entry in closed_dates:
        label = entry.get("label", "")
        if "date" in entry:
            try:
                if date_obj == date_type.fromisoformat(entry["date"]):
                    return True, label
            except ValueError:
                pass
        elif "from" in entry and "to" in entry:
            try:
                if date_type.fromisoformat(entry["from"]) <= date_obj <= date_type.fromisoformat(entry["to"]):
                    return True, label
            except ValueError:
                pass
    return False, None
