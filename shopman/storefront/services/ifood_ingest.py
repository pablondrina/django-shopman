"""
iFood order ingest — canonical entry point for marketplace orders.

A single function, :func:`ingest`, turns an iFood canonical payload into a
real ``Order`` in the iFood channel and emits the ``order_changed`` signal
so ``lifecycle.dispatch(order, "on_commit")`` runs the normal marketplace
flow (stock hold, customer.ensure with iFood strategy, etc.).

Used by:

- **Real iFood webhook** (when wired) — delegates here after authenticating
  the callback.
- **Dev simulation** — the checkout "Simular pedido iFood" button and the
  "Injetar pedido iFood simulado" admin action both build a payload with
  :func:`shopman.shop.services.ifood_simulation.session_to_ifood_payload`
  and call this service. The order runs through the exact same path a
  real callback would take.

Payload shape (canonical)
-------------------------

::

    {
        "order_code": "IFOOD-ABC123",   # required — external id
        "merchant_id": "mock-merchant", # optional — from channel config
        "created_at": "2026-04-15T...", # optional — defaults to now()
        "customer": {
            "name": "Cliente iFood",
            "phone": "",
        },
        "delivery": {
            "type": "DELIVERY",        # DELIVERY | TAKEOUT
            "address": "Rua X, 123",   # free-text
        },
        "items": [
            {
                "sku": "PAO-001",
                "name": "Pão francês",
                "qty": 2,
                "unit_price_q": 500,
            },
            ...
        ],
        "notes": "sem cebola",
    }
"""

from __future__ import annotations

import logging
from decimal import Decimal

from django.db import transaction
from shopman.orderman.ids import generate_order_ref
from shopman.orderman.models import Order, OrderItem
from shopman.orderman.signals import order_changed
from shopman.utils.monetary import monetary_mult

logger = logging.getLogger(__name__)

IFOOD_CHANNEL_REF = "ifood"


class IFoodIngestError(Exception):
    """Raised when an iFood payload cannot be ingested."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


def ingest(payload: dict, *, channel_ref: str = IFOOD_CHANNEL_REF) -> Order:
    """Ingest a canonical iFood payload and return the created ``Order``.

    The order is created in status ``NEW``; ``lifecycle.dispatch`` (triggered
    by ``order_changed``) advances it according to the channel's
    ``ChannelConfig``. Marketplace channels typically have
    ``payment.timing="external"`` and ``confirmation.mode="manual"`` — the
    order waits for the operator to accept or reject via the admin.
    """
    from shopman.shop.models import Channel

    _validate_payload(payload)

    try:
        Channel.objects.get(ref=channel_ref)
    except Channel.DoesNotExist as e:
        raise IFoodIngestError(
            "channel_missing",
            f"Canal iFood '{channel_ref}' não encontrado. Rode o seed ou crie o canal no admin.",
        ) from e

    items = _normalize_items(payload["items"])
    total_q = sum(int(item["line_total_q"]) for item in items)

    order_code = payload["order_code"]

    order_data = {
        "origin_channel": channel_ref,
        "external_order_code": order_code,
        "merchant_id": payload.get("merchant_id", ""),
        "customer": payload.get("customer") or {},
        "delivery_address": (payload.get("delivery") or {}).get("address", ""),
        "fulfillment_type": _fulfillment_type(payload),
        "order_notes": payload.get("notes", ""),
        "payment": {
            "method": "external",
            "gateway": "ifood",
            "status": "paid",  # marketplace is always pre-paid
        },
        "ifood": {
            "order_code": order_code,
            "merchant_id": payload.get("merchant_id", ""),
            "created_at": payload.get("created_at"),
        },
    }

    with transaction.atomic():
        order = Order.objects.create(
            ref=generate_order_ref(),
            channel_ref=channel_ref,
            session_key="",
            external_ref=order_code,
            handle_type="ifood_order",
            handle_ref=order_code,
            status=Order.Status.NEW,
            snapshot={
                "items": items,
                "data": dict(order_data),
                "pricing": {},
                "rev": 1,
                "commitment": {},
                "lifecycle": {},
                "source": "ifood.ingest",
            },
            data=order_data,
            total_q=total_q,
        )

        for item in items:
            OrderItem.objects.create(
                order=order,
                line_id=item["line_id"],
                sku=item["sku"],
                name=item.get("name", ""),
                qty=Decimal(str(item["qty"])),
                unit_price_q=int(item.get("unit_price_q", 0)),
                line_total_q=int(item["line_total_q"]),
                meta=item.get("meta", {}),
            )

        order.emit_event(
            event_type="created",
            actor="ifood.ingest",
            payload={"order_code": order_code},
        )

    order_changed.send(
        sender=Order,
        order=order,
        event_type="created",
        actor="ifood.ingest",
    )

    logger.info(
        "ifood_ingest: created order %s from external code %s",
        order.ref, order_code,
    )
    return order


# ── helpers ───────────────────────────────────────────────────────────


def _validate_payload(payload: dict) -> None:
    if not isinstance(payload, dict):
        raise IFoodIngestError("invalid_payload", "Payload deve ser um dict")
    if not payload.get("order_code"):
        raise IFoodIngestError("missing_order_code", "order_code é obrigatório")
    items = payload.get("items")
    if not items or not isinstance(items, list):
        raise IFoodIngestError("missing_items", "items (lista não vazia) é obrigatório")


def _normalize_items(raw_items: list[dict]) -> list[dict]:
    """Ensure every item has line_id / line_total_q computed."""
    normalized: list[dict] = []
    for idx, raw in enumerate(raw_items, start=1):
        if not raw.get("sku"):
            raise IFoodIngestError("item_missing_sku", f"item #{idx} sem sku")
        qty = Decimal(str(raw.get("qty", 0)))
        if qty <= 0:
            raise IFoodIngestError("item_invalid_qty", f"item {raw.get('sku')} com qty inválido")
        unit_price_q = int(raw.get("unit_price_q", 0))
        line_total_q = int(raw.get("line_total_q") or monetary_mult(qty, unit_price_q))
        normalized.append({
            "line_id": raw.get("line_id") or f"ifood-{idx}",
            "sku": raw["sku"],
            "name": raw.get("name", raw["sku"]),
            "qty": str(qty),
            "unit_price_q": unit_price_q,
            "line_total_q": line_total_q,
            "meta": raw.get("meta", {}),
        })
    return normalized


def _fulfillment_type(payload: dict) -> str:
    delivery = payload.get("delivery") or {}
    kind = str(delivery.get("type", "DELIVERY")).upper()
    return "delivery" if kind == "DELIVERY" else "pickup"


__all__ = ["ingest", "IFoodIngestError", "IFOOD_CHANNEL_REF"]
