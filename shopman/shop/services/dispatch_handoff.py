"""Teleporte — operator hand-off of a delivery order to an external courier.

The courier service used today (TaOn / Taxi Machine) has **no API**, so dispatch is
manual: the operator retypes the customer address into the courier's web form. This
service removes the retyping error by extracting the order's structured delivery data
into a clean, paste-ready block (and onto the clipboard).

It is the "clipboard fallback" slice of the teleporte (STOREFRONT-GAPS-ACTION-PLAN.md,
WP-11 slice 3). The structured payload returned by :func:`build_dispatch_payload` is the
seam for the future DOM auto-fill: once the courier's URL + field names are known, a
filler maps this dict onto the form. See DELIVERY-EXTERNAL-LOGISTICS-PLAN.md.

Pure (no DB writes, no side effects beyond an optional best-effort clipboard copy), so
the formatting is unit-testable without a live order.
"""

from __future__ import annotations

import shutil
import subprocess

from shopman.utils.monetary import format_money

# Clipboard tools by platform, in priority order. Each entry is the argv we pipe text to.
_CLIPBOARD_TOOLS = (
    ["pbcopy"],  # macOS
    ["wl-copy"],  # Wayland
    ["xclip", "-selection", "clipboard"],  # X11
    ["xsel", "--clipboard", "--input"],  # X11 alt
    ["clip"],  # Windows (WSL)
)


class NotDeliverableError(ValueError):
    """Raised when an order has no delivery address to hand off (e.g. pickup)."""


def build_dispatch_payload(order) -> dict:
    """Extract the structured delivery hand-off for one order.

    Returns a flat dict the courier form (or a future auto-filler) consumes directly.
    Raises :class:`NotDeliverableError` for non-delivery orders.
    """
    data = order.data if isinstance(order.data, dict) else {}
    if str(data.get("fulfillment_type") or "").lower() != "delivery":
        raise NotDeliverableError(
            f"Pedido {order.ref} não é entrega (fulfillment_type="
            f"{data.get('fulfillment_type')!r}); nada para despachar."
        )

    customer = data.get("customer") if isinstance(data.get("customer"), dict) else {}
    structured = (
        data.get("delivery_address_structured")
        if isinstance(data.get("delivery_address_structured"), dict)
        else {}
    )

    return {
        "order_ref": order.ref,
        "customer_name": str(customer.get("name") or "").strip(),
        "customer_phone": str(customer.get("phone") or data.get("customer_phone") or "").strip(),
        "route": str(structured.get("route") or "").strip(),
        "street_number": str(structured.get("street_number") or "").strip(),
        "complement": str(structured.get("complement") or "").strip(),
        "neighborhood": str(structured.get("neighborhood") or "").strip(),
        "city": str(structured.get("city") or "").strip(),
        "state_code": str(structured.get("state_code") or "").strip(),
        "postal_code": str(structured.get("postal_code") or "").strip(),
        "formatted_address": str(
            structured.get("formatted_address") or data.get("delivery_address") or ""
        ).strip(),
        "delivery_instructions": str(structured.get("delivery_instructions") or "").strip(),
        "latitude": structured.get("latitude"),
        "longitude": structured.get("longitude"),
        "distance_km": data.get("delivery_distance_km"),
        "delivery_fee_q": data.get("delivery_fee_q"),
    }


def format_dispatch_text(payload: dict) -> str:
    """Render the hand-off payload as a paste-ready pt-BR block."""
    street = " ".join(p for p in (payload["route"], payload["street_number"]) if p).strip()
    locality = ", ".join(
        p for p in (payload["neighborhood"], payload["city"], payload["state_code"]) if p
    )

    lines = [f"Pedido {payload['order_ref']}"]
    if payload["customer_name"]:
        lines.append(f"Cliente: {payload['customer_name']}")
    if payload["customer_phone"]:
        lines.append(f"Telefone: {payload['customer_phone']}")
    lines.append(f"Endereço: {street or payload['formatted_address']}")
    if payload["complement"]:
        lines.append(f"Complemento: {payload['complement']}")
    if locality:
        lines.append(f"Bairro/Cidade: {locality}")
    if payload["postal_code"]:
        lines.append(f"CEP: {payload['postal_code']}")
    if payload["delivery_instructions"]:
        lines.append(f"Referência: {payload['delivery_instructions']}")
    if payload["distance_km"] is not None:
        lines.append(f"Distância: {payload['distance_km']} km")
    if payload["delivery_fee_q"] is not None:
        lines.append(f"Taxa de entrega: R$ {format_money(int(payload['delivery_fee_q']))}")
    if payload["latitude"] is not None and payload["longitude"] is not None:
        lines.append(f"Coordenadas: {payload['latitude']},{payload['longitude']}")
    return "\n".join(lines)


def copy_to_clipboard(text: str) -> bool:
    """Best-effort copy to the operator's clipboard. Returns False if unavailable.

    Only meaningful on the operator's own machine — the teleporte is a local utility,
    decoupled from the server deploy (Pablo, 2026-06-17).
    """
    for argv in _CLIPBOARD_TOOLS:
        if shutil.which(argv[0]) is None:
            continue
        try:
            subprocess.run(argv, input=text.encode("utf-8"), check=True)
            return True
        except (subprocess.SubprocessError, OSError):
            continue
    return False
