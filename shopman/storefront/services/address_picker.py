"""Address picker context builder — shared by checkout and account views.

JSON is returned as plain strings. Django's auto-escape turns ``"`` into
``&quot;`` inside ``x-data="..."`` which the browser unescapes to valid JS.
Never mark_safe the output.
"""

from __future__ import annotations

import json as _json
import logging

logger = logging.getLogger(__name__)


def address_picker_context(
    saved_addresses=(),
    *,
    form_data: dict | None = None,
    preselected_id: int | None = None,
) -> dict:
    """Build the Alpine addressPicker x-data payload.

    ``saved_addresses`` is any iterable of SavedAddressProjection objects or
    address dicts. Pass an empty iterable for surfaces that list addresses
    separately (e.g. account page).

    ``form_data`` is the POST payload on error re-renders; hydrates the
    picker's ``draft`` so the user doesn't lose what they typed.
    """
    from django.conf import settings
    from shopman.shop.models import Shop

    addresses = []
    for addr in (saved_addresses or ()):
        if isinstance(addr, dict):
            addresses.append(addr)
        else:
            addresses.append({
                "id": addr.id,
                "label": getattr(addr, "label", "") or getattr(addr, "display_label", ""),
                "formatted_address": addr.formatted_address,
                "complement": addr.complement,
                "is_default": addr.is_default,
                "route": getattr(addr, "route", ""),
                "street_number": getattr(addr, "street_number", ""),
                "neighborhood": getattr(addr, "neighborhood", ""),
                "city": getattr(addr, "city", ""),
                "state_code": getattr(addr, "state_code", ""),
                "postal_code": getattr(addr, "postal_code", ""),
                "latitude": getattr(addr, "latitude", None),
                "longitude": getattr(addr, "longitude", None),
                "place_id": getattr(addr, "place_id", ""),
                "delivery_instructions": getattr(addr, "delivery_instructions", ""),
            })

    shop_location = None
    try:
        shop = Shop.load()
        if shop and shop.latitude and shop.longitude:
            shop_location = {"lat": float(shop.latitude), "lng": float(shop.longitude)}
    except Exception:
        shop_location = None

    initial_draft = None
    if form_data:
        draft = {
            "route": form_data.get("addr_route", ""),
            "street_number": form_data.get("addr_street_number", ""),
            "complement": form_data.get("addr_complement", ""),
            "neighborhood": form_data.get("addr_neighborhood", ""),
            "city": form_data.get("addr_city", ""),
            "state_code": form_data.get("addr_state_code", ""),
            "postal_code": form_data.get("addr_postal_code", ""),
            "place_id": form_data.get("addr_place_id", ""),
            "formatted_address": form_data.get("addr_formatted_address", ""),
            "delivery_instructions": form_data.get("addr_delivery_instructions", ""),
            "latitude": form_data.get("addr_latitude") or None,
            "longitude": form_data.get("addr_longitude") or None,
        }
        if any(v for v in draft.values() if v not in (None, "")):
            initial_draft = draft

    return {
        "picker_addresses_json": _json.dumps(addresses),
        "picker_shop_location_json": _json.dumps(shop_location),
        "picker_initial_draft_json": _json.dumps(initial_draft),
        "picker_preselected_id": preselected_id,
        "google_maps_api_key": getattr(settings, "GOOGLE_MAPS_API_KEY", ""),
    }
