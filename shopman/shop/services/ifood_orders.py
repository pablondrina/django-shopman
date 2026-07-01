"""iFood order fetch + mapping to the canonical ingest payload (WP-3).

The Order Module delivers only lightweight *events* (``id``, ``code``,
``orderId``) — never the order inline. To materialize an order we:

1. ``GET /order/v1.0/orders/{orderId}`` → the full iFood order (verified live:
   the route exists; a fake id returns ``404 OrderNotFound``).
2. Map that iFood-native shape to the **canonical payload** consumed by
   :func:`shopman.shop.services.ifood_ingest.ingest`.

⚠️ The full order schema could not be captured live (the test store is
``DISABLED`` and has no orders). :func:`map_order` follows the documented iFood
Order Module v1.0 schema and is defensive about optional fields; it must be
revalidated against one real order during homologação.

All money in the canonical payload is in centavos (``_q`` convention). iFood
order prices are decimal currency values (e.g. ``12.5`` = R$ 12,50).
"""

from __future__ import annotations

import logging

import requests
from django.conf import settings

from shopman.shop.services import ifood_auth

logger = logging.getLogger(__name__)


class IFoodOrderFetchError(Exception):
    """Raised when an iFood order cannot be fetched."""


def _cfg() -> dict:
    return getattr(settings, "SHOPMAN_IFOOD", {}) or {}


def _base_url() -> str:
    return str(_cfg().get("api_base") or "https://merchant-api.ifood.com.br").rstrip("/")


def _to_q(value) -> int:
    """Convert an iFood decimal currency value (reais) to centavos."""
    try:
        return int(round(float(value) * 100))
    except (TypeError, ValueError):
        return 0


def fetch_order(order_id: str) -> dict:
    """Fetch the full iFood order by id. Raises :class:`IFoodOrderFetchError`."""
    headers = ifood_auth.authorized_headers()
    if not headers:
        raise IFoodOrderFetchError("iFood OAuth is not configured (client_id/client_secret)")

    url = f"{_base_url()}/order/v1.0/orders/{order_id}"
    try:
        resp = requests.get(url, headers=headers, timeout=int(_cfg().get("timeout") or 30))
    except requests.RequestException as exc:
        raise IFoodOrderFetchError(f"iFood order fetch failed: {exc}") from exc

    if resp.status_code != 200:
        raise IFoodOrderFetchError(
            f"iFood order fetch HTTP {resp.status_code}: {resp.text[:200]}"
        )
    try:
        return resp.json()
    except ValueError as exc:
        raise IFoodOrderFetchError("iFood order response was not JSON") from exc


# ── Mapping: iFood order → canonical ingest payload ────────────────────────────


def map_order(order: dict) -> dict:
    """Map an iFood Order Module v1.0 order to the canonical ingest payload.

    Field coverage validated against a real Developer-Portal test order
    (2026-07-01): combos (``totalPrice`` ≠ ``unitPrice``), nested option
    customizations, the ``isTest`` flag, and the financial breakdown.
    """
    order_id = order.get("id") or order.get("orderId") or ""
    merchant = order.get("merchant") or {}

    return {
        "order_code": str(order_id),
        "merchant_id": merchant.get("id") or _cfg().get("merchant_id", ""),
        "created_at": order.get("createdAt"),
        "display_id": order.get("displayId", ""),
        "is_test": bool(order.get("isTest", False)),
        "order_timing": order.get("orderTiming", ""),
        "customer": _map_customer(order.get("customer") or {}),
        "delivery": _map_delivery(order),
        "items": _map_items(order.get("items") or []),
        "totals": _map_totals(order.get("total") or {}),
        "payments": _map_payments(order.get("payments") or {}),
        "notes": _order_notes(order),
    }


def _map_customer(customer: dict) -> dict:
    phone = customer.get("phone") or {}
    if isinstance(phone, dict):
        # iFood masks the number and gives a call localizer to reach the customer.
        number = phone.get("number", "")
        localizer = phone.get("localizer", "")
    else:
        number = str(phone)
        localizer = ""
    return {
        "name": customer.get("name", ""),
        "phone": number,
        "phone_localizer": localizer,
        "document": customer.get("documentNumber", ""),
    }


def _map_delivery(order: dict) -> dict:
    # iFood order types: DELIVERY, TAKEOUT, INDOOR. ingest treats anything other
    # than DELIVERY as pickup, so INDOOR (dine-in) is passed through unchanged.
    kind = str(order.get("orderType", "DELIVERY")).upper()
    if kind not in ("DELIVERY", "TAKEOUT", "INDOOR"):
        kind = "DELIVERY"
    delivery = order.get("delivery") or {}
    address = delivery.get("deliveryAddress") or {}
    formatted = (
        address.get("formattedAddress")
        or _compose_address(address)
    )
    return {
        "type": kind,
        "address": formatted,
        "complement": address.get("complement", ""),
        "reference": address.get("reference", ""),
        "postal_code": address.get("postalCode", ""),
        "scheduled_at": delivery.get("deliveryDateTime", ""),
        "pickup_code": delivery.get("pickupCode", ""),
        "delivered_by": delivery.get("deliveredBy", ""),
    }


def _compose_address(address: dict) -> str:
    parts = [
        address.get("streetName", ""),
        address.get("streetNumber", ""),
        address.get("neighborhood", ""),
        address.get("city", ""),
        address.get("state", ""),
    ]
    return ", ".join(p for p in parts if p)


def _map_items(items: list[dict]) -> list[dict]:
    mapped: list[dict] = []
    for idx, raw in enumerate(items, start=1):
        unit_q = _to_q(raw.get("unitPrice", raw.get("price", 0)))
        # totalPrice already includes optionsPrice + customizationPrice — critical
        # for combos, where unitPrice (base) undercounts the real line charge.
        line_total_q = _to_q(raw.get("totalPrice")) if raw.get("totalPrice") is not None else None
        mapped.append({
            "line_id": raw.get("id") or f"ifood-{idx}",
            "sku": raw.get("externalCode") or raw.get("id") or f"ifood-item-{idx}",
            "name": raw.get("name", ""),
            "qty": raw.get("quantity", 1),
            "unit_price_q": unit_q,
            # Pass the real line total so ingest doesn't recompute qty×unit and
            # drop option/customization charges. Omitted → ingest computes it.
            **({"line_total_q": line_total_q} if line_total_q is not None else {}),
            "meta": {
                "observations": raw.get("observations", ""),
                "item_type": raw.get("type", ""),
                "options": _map_options(raw.get("options") or []),
            },
        })
    return mapped


def _map_options(options: list[dict]) -> list[dict]:
    """Flatten iFood option groups (and their 3rd-level customizations) for KDS."""
    mapped: list[dict] = []
    for opt in options:
        mapped.append({
            "name": opt.get("name", ""),
            "group": opt.get("groupName", ""),
            "qty": opt.get("quantity", 1),
            "unit_price_q": _to_q(opt.get("unitPrice", opt.get("price", 0))),
            "customizations": [
                {
                    "name": cst.get("name", ""),
                    "group": cst.get("groupName", ""),
                    "qty": cst.get("quantity", 1),
                    "unit_price_q": _to_q(cst.get("unitPrice", cst.get("price", 0))),
                }
                for cst in (opt.get("customizations") or [])
            ],
        })
    return mapped


def _map_totals(total: dict) -> dict:
    """iFood order financial breakdown → centavos (for reconciliation/display)."""
    return {
        "subtotal_q": _to_q(total.get("subTotal", 0)),
        "delivery_fee_q": _to_q(total.get("deliveryFee", 0)),
        "additional_fees_q": _to_q(total.get("additionalFees", 0)),
        "benefits_q": _to_q(total.get("benefits", 0)),
        "order_amount_q": _to_q(total.get("orderAmount", 0)),
    }


def _map_payments(payments: dict) -> dict:
    """iFood payments → simplified summary (prepaid/pending + methods, centavos)."""
    methods = payments.get("methods") or []
    return {
        "prepaid_q": _to_q(payments.get("prepaid", 0)),
        "pending_q": _to_q(payments.get("pending", 0)),
        "methods": [
            {
                "method": m.get("method", ""),
                "type": m.get("type", ""),
                "prepaid": bool(m.get("prepaid", False)),
                "value_q": _to_q(m.get("value", 0)),
                "brand": (m.get("card") or {}).get("brand", ""),
            }
            for m in methods
        ],
    }


def _order_notes(order: dict) -> str:
    # Order-level free text lives under different keys across iFood payloads;
    # delivery.observations carries per-order notes on real orders.
    for value in (
        order.get("observations"),
        order.get("extraInfo"),
        order.get("note"),
        (order.get("delivery") or {}).get("observations"),
    ):
        if value:
            return str(value)
    return ""


__all__ = ["fetch_order", "map_order", "IFoodOrderFetchError"]
