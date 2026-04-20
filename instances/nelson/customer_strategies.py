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


def nelson_handle_balcao(order):
    """
    Resolve customer for in-person counter (balcão) orders.

    Resolution order:
    1. Phone present → delegate to generic phone strategy.
    2. CPF present → resolve/create customer by document number.
    3. Neither → skip (anonymous walk-in).
    """
    from shopman.shop.adapters import get_adapter
    from shopman.shop.services.customer import (
        _SkipAnonymous,
        _get_customer_data,
        _handle_phone,
        _maybe_update_name,
        _split_name,
    )

    customer_data = _get_customer_data(order)
    phone_raw = customer_data.get("phone", "")
    cpf = customer_data.get("cpf", "")
    name = customer_data.get("name", "")

    if phone_raw:
        return _handle_phone(order)

    if cpf:
        adapter = get_adapter("customer")
        cpf_normalized = "".join(filter(str.isdigit, cpf))
        if not cpf_normalized:
            raise _SkipAnonymous()

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
            customer_type="individual",
            source_system="balcao",
        )
        adapter.create_identifier(customer["ref"], "cpf", cpf_normalized, is_primary=True)
        return customer

    raise _SkipAnonymous()


# Register on import
from shopman.shop.services.customer import register_strategy
register_strategy("balcao", nelson_handle_balcao)
