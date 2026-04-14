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
    from shopman.shop.services.customer import (
        _SkipAnonymous,
        _add_identifier,
        _find_by_identifier,
        _get_customer_data,
        _get_customer_service,
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
        svc = _get_customer_service()
        cpf_normalized = "".join(filter(str.isdigit, cpf))
        if not cpf_normalized:
            raise _SkipAnonymous()

        customer = svc.get_by_document(cpf_normalized)
        if customer:
            _maybe_update_name(customer, name)
            return customer

        customer = _find_by_identifier("cpf", cpf_normalized)
        if customer:
            _maybe_update_name(customer, name)
            return customer

        first_name, last_name = _split_name(name)
        ref = f"CLI-{uuid.uuid4().hex[:8].upper()}"
        customer = svc.create(
            ref=ref,
            first_name=first_name or "Cliente",
            last_name=last_name or f"CPF {cpf_normalized[-4:]}",
            document=cpf_normalized,
            customer_type="individual",
            source_system="balcao",
        )
        _add_identifier(customer, "cpf", cpf_normalized, is_primary=True)
        return customer

    raise _SkipAnonymous()


# Register on import
from shopman.shop.services.customer import register_strategy
register_strategy("balcao", nelson_handle_balcao)
