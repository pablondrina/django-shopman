"""
iFood simulation — turn a live Session into a canonical iFood payload.

Developer tool. This is how the "Simular pedido iFood" button in the
storefront checkout and the "Injetar pedido iFood simulado" admin action
produce their inputs to
:func:`shopman.shop.services.ifood_ingest.ingest`.

Philosophy
----------

The translator is *dumb*: it reads ``session.items`` and ``session.data``,
drops everything that an iFood order would not carry (scheduled delivery,
coupon codes, internal totals, business-hours annotations) and fabricates
the bits iFood would normally supply (order code, merchant id, created_at).

There is no "simulation mode" flag anywhere downstream. ``ifood_ingest``
treats the output identically to a real webhook payload — because it *is*
a valid payload, just authored locally.
"""

from __future__ import annotations

from uuid import uuid4

from django.utils import timezone

__all__ = ["session_to_ifood_payload"]


def session_to_ifood_payload(session, *, merchant_id: str = "mock-merchant") -> dict:
    """Build an iFood canonical payload from a live ``Session``.

    Parameters
    ----------
    session:
        A live ``Session`` instance (must have at least one item).
    merchant_id:
        Merchant id to embed in the payload. Defaults to ``"mock-merchant"``;
        instance code / callers may override with a channel-configured id.

    Returns
    -------
    dict
        A payload accepted by ``ifood_ingest.ingest``. Items, quantities
        and unit prices come from the session; everything else is either
        synthesized or lifted from ``session.data`` when present (customer
        name, delivery address).
    """
    if not session.items:
        raise ValueError("session_to_ifood_payload: session has no items")

    data = session.data or {}
    customer_data = data.get("customer") or {}
    delivery_address = data.get("delivery_address") or ""

    items_payload = []
    for idx, item in enumerate(session.items, start=1):
        items_payload.append({
            "line_id": f"ifood-sim-{idx}",
            "sku": item["sku"],
            "name": item.get("name") or item["sku"],
            "qty": str(item["qty"]),
            "unit_price_q": int(item.get("unit_price_q", 0)),
            # Let ifood_ingest recompute line_total_q from qty × unit_price_q.
        })

    order_code = f"IFOOD-SIM-{uuid4().hex[:8].upper()}"

    return {
        "order_code": order_code,
        "merchant_id": merchant_id,
        "created_at": timezone.now().isoformat(),
        "customer": {
            "name": customer_data.get("name") or "Cliente iFood Simulado",
            "phone": customer_data.get("phone") or "",
        },
        "delivery": {
            "type": "DELIVERY",
            "address": delivery_address or "Rua Simulada, 123 — Bairro iFood",
        },
        "items": items_payload,
        "notes": data.get("order_notes") or "[SIMULAÇÃO] Pedido iFood injetado localmente",
    }
