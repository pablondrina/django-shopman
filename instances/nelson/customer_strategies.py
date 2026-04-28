"""
Nelson Boulangerie — customer resolution strategies.

Registers Nelson-specific strategies with the shopman customer service.
Import this module during app startup to activate them.

    # In AppConfig.ready() or settings-level registration:
    from shopman.shop.services.customer import register_strategy
    import nelson.customer_strategies  # registers on import
"""

from __future__ import annotations

import uuid

from shopman.shop.adapters import get_adapter
from shopman.shop.services.customer import SkipAnonymous, register_strategy


def _get_customer_data(order) -> dict:
    return order.snapshot.get("data", {}).get("customer", {}) or order.data.get("customer", {})


def _normalize_phone(phone_raw: str) -> str:
    if not phone_raw:
        return ""
    try:
        from shopman.utils.phone import normalize_phone

        return normalize_phone(phone_raw)
    except Exception:
        return phone_raw


def _split_name(full_name: str) -> tuple[str, str]:
    parts = full_name.strip().split(None, 1)
    return (parts[0] if parts else "", parts[1] if len(parts) > 1 else "")


def _maybe_update_name(adapter, customer: dict, name: str) -> None:
    if name and not customer.get("first_name"):
        first_name, last_name = _split_name(name)
        try:
            adapter.update_customer(customer["ref"], first_name=first_name, last_name=last_name)
        except Exception:
            pass


def nelson_handle_pdv(order):
    """
    Resolve customer for in-person counter (balcão) orders.

    Resolution order:
    1. Phone present → delegate to generic phone strategy.
    2. CPF present → resolve/create customer by document number.
    3. Neither → skip (anonymous walk-in).
    """
    customer_data = _get_customer_data(order)
    phone_raw = customer_data.get("phone", "")
    cpf = customer_data.get("cpf", "")
    name = customer_data.get("name", "")
    adapter = get_adapter("customer")

    if phone_raw:
        phone = _normalize_phone(phone_raw)
        if not phone:
            raise SkipAnonymous()

        customer = adapter.get_customer_by_phone(phone)
        if customer:
            _maybe_update_name(adapter, customer, name)
            return customer

        first_name, last_name = _split_name(name)
        ref = f"CLI-{uuid.uuid4().hex[:8].upper()}"
        return adapter.create_customer(
            ref=ref,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            customer_type="individual",
            source_system="pdv",
        )

    if cpf:
        cpf_normalized = "".join(filter(str.isdigit, cpf))
        if not cpf_normalized:
            raise SkipAnonymous()

        customer = adapter.get_customer_by_identifier("cpf", cpf_normalized)
        if customer:
            _maybe_update_name(adapter, customer, name)
            return customer

        first_name, last_name = _split_name(name)
        ref = f"CLI-{uuid.uuid4().hex[:8].upper()}"
        customer = adapter.create_customer(
            ref=ref,
            first_name=first_name or "Cliente",
            last_name=last_name or f"CPF {cpf_normalized[-4:]}",
            phone="",
            customer_type="individual",
            source_system="pdv",
        )
        adapter.create_identifier(customer["ref"], "cpf", cpf_normalized, is_primary=True)
        return customer

    raise SkipAnonymous()


# Register on import
register_strategy("pdv", nelson_handle_pdv)
