"""Server-side Google Geocoding wrapper.

Reverse geocoding is done on the server so the Maps API key never leaks to
the client — only the canonical, structured address is sent back to the
browser. The forward (Places Autocomplete) path stays client-side because
that key is domain-restricted in Google Cloud Console.
"""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
REQUEST_TIMEOUT_SECONDS = 5
CACHE_TTL_SECONDS = 60 * 60 * 24  # 24h — reverse geocode is stable for a coordinate.


class GeocodingError(Exception):
    """Raised when reverse geocoding cannot produce a canonical result."""


@dataclass(frozen=True)
class ReverseGeocodeResult:
    """Canonical address payload returned to the client.

    Mirrors the keys the storefront writes into `delivery_address_structured`
    (see docs/reference/data-schemas.md) so the same component can persist the
    result without reshaping.
    """

    formatted_address: str
    route: str
    street_number: str
    neighborhood: str
    city: str
    state: str
    state_code: str
    postal_code: str
    country: str
    country_code: str
    latitude: float
    longitude: float
    place_id: str

    def to_dict(self) -> dict:
        return asdict(self)


def _component(components: list[dict], *types: str) -> str:
    """Return the long_name of the first component matching any of `types`."""
    wanted = set(types)
    for comp in components:
        if wanted.intersection(comp.get("types", [])):
            return comp.get("long_name") or ""
    return ""


def _component_short(components: list[dict], *types: str) -> str:
    wanted = set(types)
    for comp in components:
        if wanted.intersection(comp.get("types", [])):
            return comp.get("short_name") or ""
    return ""


def _parse_result(result: dict, lat: float, lng: float) -> ReverseGeocodeResult:
    comps = result.get("address_components") or []
    loc = (result.get("geometry") or {}).get("location") or {}
    return ReverseGeocodeResult(
        formatted_address=result.get("formatted_address", ""),
        route=_component(comps, "route"),
        street_number=_component(comps, "street_number"),
        neighborhood=_component(
            comps, "sublocality_level_1", "sublocality", "neighborhood"
        ),
        city=_component(
            comps, "administrative_area_level_2", "locality"
        ),
        state=_component(comps, "administrative_area_level_1"),
        state_code=_component_short(comps, "administrative_area_level_1"),
        postal_code=_component(comps, "postal_code"),
        country=_component(comps, "country"),
        country_code=_component_short(comps, "country"),
        latitude=float(loc.get("lat", lat)),
        longitude=float(loc.get("lng", lng)),
        place_id=result.get("place_id", ""),
    )


def reverse_geocode(lat: float, lng: float) -> ReverseGeocodeResult:
    """Reverse-geocode (lat, lng) via Google. Raises GeocodingError on failure.

    Cached for 24h per (lat, lng) rounded to ~11m precision (6 decimals).
    """
    api_key = getattr(settings, "GOOGLE_MAPS_API_KEY", "")
    if not api_key:
        raise GeocodingError("GOOGLE_MAPS_API_KEY not configured.")

    key = f"geocode:rev:{lat:.6f}:{lng:.6f}"
    cached = cache.get(key)
    if cached is not None:
        return ReverseGeocodeResult(**cached)

    params = {
        "latlng": f"{lat},{lng}",
        "key": api_key,
        "language": "pt-BR",
        "region": "br",
    }
    url = f"{GEOCODE_URL}?{urllib.parse.urlencode(params)}"

    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 — network error surfaces as domain error
        logger.warning("reverse_geocode_http_failed lat=%s lng=%s err=%s", lat, lng, exc)
        raise GeocodingError("Reverse geocoding request failed.") from exc

    status = payload.get("status", "")
    if status != "OK":
        logger.info("reverse_geocode_empty lat=%s lng=%s status=%s", lat, lng, status)
        raise GeocodingError(f"No result (status={status}).")

    results = payload.get("results") or []
    if not results:
        raise GeocodingError("No result returned.")

    parsed = _parse_result(results[0], lat, lng)
    cache.set(key, parsed.to_dict(), CACHE_TTL_SECONDS)
    return parsed
