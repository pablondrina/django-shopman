"""Account intent extraction.

interpret_profile_update() and interpret_address_*(). absorb all POST parsing
from ProfileUpdateView, AddressCreateView, and AddressUpdateView.
"""

from __future__ import annotations

from .types import (
    AddressIntent,
    AddressIntentResult,
    ProfileUpdateIntent,
    ProfileUpdateResult,
)


# ── Public API ────────────────────────────────────────────────────────────────


def interpret_profile_update(request) -> ProfileUpdateResult:
    post = request.POST
    first_name = post.get("first_name", "").strip()
    last_name = post.get("last_name", "").strip()
    email = post.get("email", "").strip()
    birthday_raw = post.get("birthday", "").strip()

    errors: dict[str, str] = {}
    if not first_name:
        errors["first_name"] = "Nome é obrigatório."
    if errors:
        return ProfileUpdateResult(intent=None, errors=errors)

    birthday = None
    if birthday_raw:
        from datetime import date as date_type
        try:
            birthday = date_type.fromisoformat(birthday_raw)
        except ValueError:
            birthday = None

    return ProfileUpdateResult(
        intent=ProfileUpdateIntent(
            first_name=first_name,
            last_name=last_name,
            email=email,
            birthday=birthday,
        ),
        errors={},
    )


def interpret_address_create(request) -> AddressIntentResult:
    return _parse_address_intent(request.POST, addr=None)


def interpret_address_update(request, addr) -> AddressIntentResult:
    return _parse_address_intent(request.POST, addr=addr)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _parse_address_intent(post, *, addr) -> AddressIntentResult:
    def _field(name: str, default: str = "") -> str:
        fallback = (getattr(addr, name, None) or default) if addr else default
        return (post.get(name, fallback) or default).strip()

    label = post.get("label") or (getattr(addr, "label", None) or "home")
    label_custom = post.get("label_custom", "").strip()
    route = _field("route")
    street_number = _field("street_number")
    neighborhood = _field("neighborhood")
    city = _field("city")
    state_code = _field("state_code")
    postal_code = _field("postal_code")
    complement = post.get("complement", "").strip()
    delivery_instructions = post.get("delivery_instructions", "").strip()
    place_id = _field("place_id") or None
    is_default = post.get("is_default") == "on"

    formatted_address = _field("formatted_address")
    if not formatted_address:
        parts = []
        if route:
            parts.append(route)
        if street_number:
            parts.append(street_number)
        if neighborhood:
            parts.append(f"- {neighborhood}")
        if city:
            parts.append(f"- {city}")
        formatted_address = " ".join(parts)

    errors: dict[str, str] = {}
    if addr is None and (not formatted_address or not route):
        errors["formatted_address"] = "Informe um endereço válido."

    coordinates = _parse_coordinates(post)

    if errors:
        return AddressIntentResult(intent=None, errors=errors, form_data=post)

    return AddressIntentResult(
        intent=AddressIntent(
            label=label,
            label_custom=label_custom,
            formatted_address=formatted_address,
            route=route,
            street_number=street_number,
            neighborhood=neighborhood,
            city=city,
            state_code=state_code,
            postal_code=postal_code,
            complement=complement,
            delivery_instructions=delivery_instructions,
            place_id=place_id,
            is_default=is_default,
            coordinates=coordinates,
            is_verified=coordinates is not None,
        ),
        errors={},
        form_data=post,
    )


def _parse_coordinates(post) -> tuple[float, float] | None:
    try:
        lat_raw = (post.get("latitude") or "").strip()
        lng_raw = (post.get("longitude") or "").strip()
        if not lat_raw or not lng_raw:
            return None
        return float(lat_raw), float(lng_raw)
    except (ValueError, TypeError):
        return None
