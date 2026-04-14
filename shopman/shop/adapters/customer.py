"""Internal customer adapter — delegates to Guestman services."""

from __future__ import annotations

import logging
from decimal import Decimal

logger = logging.getLogger(__name__)


# ── Customer CRUD ────────────────────────────────────────────────────


def get_customer_by_phone(phone: str) -> dict | None:
    """Retorna {"ref", "first_name", "last_name", "phone"} ou None."""
    from shopman.guestman.services import customer as svc

    customer = svc.get_by_phone(phone)
    if not customer:
        return None
    return _customer_to_dict(customer)


def create_customer(
    ref: str,
    first_name: str,
    last_name: str,
    phone: str,
    customer_type: str,
    source_system: str,
) -> dict:
    """Cria cliente. Retorna {"ref", "first_name", "last_name", "phone"}."""
    from shopman.guestman.services import customer as svc

    customer = svc.create(
        ref=ref,
        first_name=first_name,
        last_name=last_name,
        phone=phone,
        customer_type=customer_type,
        source_system=source_system,
    )
    return _customer_to_dict(customer)


def update_customer(ref: str, first_name: str | None = None, last_name: str | None = None) -> None:
    """Atualiza dados do cliente."""
    from shopman.guestman.services import customer as svc

    kwargs = {}
    if first_name is not None:
        kwargs["first_name"] = first_name
    if last_name is not None:
        kwargs["last_name"] = last_name
    if kwargs:
        svc.update(ref, **kwargs)


# ── Identifiers ──────────────────────────────────────────────────────


def get_customer_by_identifier(identifier_type: str, identifier_value: str) -> dict | None:
    """Busca cliente por identificador externo. Retorna {"ref", "first_name", "last_name", "phone"} ou None."""
    from shopman.guestman.contrib.identifiers import IdentifierService

    customer = IdentifierService.find_by_identifier(identifier_type, identifier_value)
    if not customer:
        return None
    return _customer_to_dict(customer)


def create_identifier(
    customer_ref: str,
    identifier_type: str,
    identifier_value: str,
    is_primary: bool = True,
    source_system: str | None = None,
) -> None:
    """Cria identificador externo para cliente."""
    from shopman.guestman.contrib.identifiers import IdentifierService

    IdentifierService.ensure_identifier(
        customer_ref=customer_ref,
        identifier_type=identifier_type,
        identifier_value=str(identifier_value),
        is_primary=is_primary,
        source_system=source_system or "shopman",
    )


# ── Timeline ─────────────────────────────────────────────────────────


def log_timeline_event(
    customer_ref: str,
    event_type: str,
    title: str,
    description: str = "",
    channel: str = "",
    reference: str = "",
    metadata: dict | None = None,
    created_by: str = "system",
) -> None:
    """Registra evento na timeline do cliente."""
    from shopman.guestman.contrib.timeline import TimelineService

    TimelineService.log_event(
        customer_ref=customer_ref,
        event_type=event_type,
        title=title,
        description=description,
        channel=channel,
        reference=reference,
        metadata=metadata or {},
        created_by=created_by,
    )


def has_timeline_event(customer_ref: str, event_type: str, reference: str) -> bool:
    """Verifica se evento já existe (idempotência)."""
    from shopman.guestman.contrib.timeline import TimelineService

    return TimelineService.has_event(customer_ref, event_type, reference)


# ── Insights ─────────────────────────────────────────────────────────


def recalculate_insights(customer_ref: str) -> None:
    """Recalcula insights do cliente (RFM, etc.)."""
    from shopman.guestman.contrib.insights import InsightService

    InsightService.recalculate(customer_ref)


# ── Addresses ────────────────────────────────────────────────────────


def has_address(customer_ref: str, formatted_address: str) -> bool:
    """Verifica se endereço já existe."""
    from shopman.guestman.services import address as address_service

    return address_service.has_address(customer_ref, formatted_address)


def has_any_address(customer_ref: str) -> bool:
    """Verifica se o cliente já tem algum endereço cadastrado."""
    from shopman.guestman.services import address as address_service

    return address_service.has_any_address(customer_ref)


def create_address(
    customer_ref: str,
    label: str,
    formatted_address: str,
    is_default: bool = False,
) -> None:
    """Salva endereço do cliente."""
    from shopman.guestman.services import address as address_service

    address_service.add_address(
        customer_ref=customer_ref,
        label=label,
        formatted_address=formatted_address,
        is_default=is_default,
    )


# ── Preferences ──────────────────────────────────────────────────────


def get_preferences(customer_ref: str, category: str) -> list[dict]:
    """Retorna [{"key": str, "value": str, "preference_type": str}]."""
    from shopman.guestman.contrib.preferences import PreferenceService

    prefs = PreferenceService.get_preferences(customer_ref, category=category)
    return [
        {
            "key": p.key,
            "value": p.value,
            "preference_type": p.preference_type.value if hasattr(p.preference_type, "value") else str(p.preference_type),
        }
        for p in prefs
    ]


def set_preference(
    customer_ref: str,
    category: str,
    key: str,
    value: str,
    preference_type: str = "explicit",
    confidence: float = 1.0,
    source: str = "checkout",
) -> None:
    """Salva preferência."""
    from shopman.guestman.contrib.preferences import PreferenceService

    PreferenceService.set_preference(
        customer_ref=customer_ref,
        category=category,
        key=key,
        value=value,
        preference_type=preference_type,
        confidence=Decimal(str(confidence)),
        source=source,
    )


# ── Loyalty ──────────────────────────────────────────────────────────


def enroll_loyalty(customer_ref: str) -> None:
    """Inscreve cliente no programa de fidelidade."""
    from shopman.guestman.contrib.loyalty import LoyaltyService

    LoyaltyService.enroll(customer_ref)


def earn_points(
    customer_ref: str,
    points: int,
    description: str,
    reference: str,
    created_by: str = "system",
) -> None:
    """Credita pontos."""
    from shopman.guestman.contrib.loyalty import LoyaltyService

    LoyaltyService.earn_points(
        customer_ref=customer_ref,
        points=points,
        description=description,
        reference=reference,
        created_by=created_by,
    )


def redeem_points(
    customer_ref: str,
    points: int,
    description: str,
    reference: str,
    created_by: str = "system",
) -> None:
    """Debita pontos."""
    from shopman.guestman.contrib.loyalty import LoyaltyService

    LoyaltyService.redeem_points(
        customer_ref=customer_ref,
        points=points,
        description=description,
        reference=reference,
        created_by=created_by,
    )


# ── helpers ──────────────────────────────────────────────────────────


def _customer_to_dict(customer) -> dict:
    return {
        "ref": customer.ref,
        "first_name": customer.first_name,
        "last_name": customer.last_name,
        "phone": customer.phone,
    }
