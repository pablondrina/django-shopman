"""Cart mutation commands shared by Django and API storefront surfaces."""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from typing import Any

from django.http import HttpRequest
from shopman.utils.monetary import format_money

from shopman.shop.services.cart import CartUnavailableError
from shopman.shop.services.storefront_context import minimum_order_progress
from shopman.storefront.cart import CartService
from shopman.storefront.constants import STOREFRONT_CHANNEL_REF
from shopman.storefront.intents.cart import interpret_set_qty
from shopman.storefront.intents.types import SetQtyIntent

MAX_CART_LINE_QTY = 99


class CartCommandNotFound(Exception):
    """Raised when a SKU cannot be resolved for a cart command."""


class CartCommandUnavailable(Exception):
    """Raised when the server refuses a cart command for stock reasons."""

    def __init__(self, *, product, stock_error: CartUnavailableError):
        super().__init__(str(stock_error))
        self.product = product
        self.stock_error = stock_error


@dataclass(frozen=True)
class CartCommandOutcome:
    """Result of one set-qty command."""

    intent: SetQtyIntent
    cart: dict[str, Any]
    payload: dict[str, Any]


def parse_cart_qty(raw, *, minimum: int) -> int | None:
    """Parse a storefront cart quantity and clamp it to the public max."""
    try:
        qty = int(raw)
    except (TypeError, ValueError):
        return None
    if qty < minimum:
        qty = minimum
    return min(qty, MAX_CART_LINE_QTY)


def set_qty_by_sku(
    request: HttpRequest,
    *,
    sku: str,
    qty: int,
    perf=None,
) -> CartCommandOutcome:
    """Set absolute cart quantity for one SKU.

    This is the canonical mutation command for product-card, PDP and cart
    steppers. It keeps the server authoritative for price, holds and stock while
    letting different surfaces share the same action semantics.
    """
    with _perf_step(perf, "cart_read"):
        cart = CartService.get_cart_summary(request, include_items=True)
    with _perf_step(perf, "intent"):
        result = interpret_set_qty(sku, qty, cart)
    if result.error_type == "not_found" or result.intent is None:
        raise CartCommandNotFound(sku)

    intent = result.intent
    mutated_session = None
    try:
        with _perf_step(perf, f"mutate_{intent.action}"):
            if intent.action == "remove":
                if intent.line_id is not None:
                    mutated_session = CartService.remove_item(
                        request,
                        line_id=intent.line_id,
                        sku=intent.sku,
                    )
            elif intent.action == "update":
                mutated_session = CartService.update_qty(
                    request,
                    line_id=intent.line_id,
                    qty=intent.qty,
                    sku=intent.sku,
                )
            else:
                mutated_session = CartService.add_item(
                    request,
                    sku=intent.sku,
                    qty=intent.qty,
                    unit_price_q=intent.unit_price_q,
                    is_d1=intent.is_d1,
                )
    except CartUnavailableError as exc:
        raise CartCommandUnavailable(product=intent.product, stock_error=exc) from exc

    with _perf_step(perf, "payload"):
        if mutated_session is not None:
            cart = CartService.summary_from_session(
                mutated_session,
                include_items=True,
            )
        else:
            cart = CartService.get_cart_summary(request, include_items=True)
        payload = cart_command_payload(intent, cart)
    return CartCommandOutcome(intent=intent, cart=cart, payload=payload)


def cart_command_payload(intent: SetQtyIntent, cart: dict[str, Any]) -> dict[str, Any]:
    """Compact command response for immediate UI reconciliation."""
    subtotal_q = int(cart.get("subtotal_q", 0) or 0)
    min_order = minimum_order_progress(
        subtotal_q,
        channel_ref=STOREFRONT_CHANNEL_REF,
    )
    line = cart_line_payload(intent, cart)
    return {
        "ok": True,
        "action": intent.action,
        "sku": intent.sku,
        "line": line,
        "cart": {
            "count": int(cart.get("count", 0) or 0),
            "subtotal_q": subtotal_q,
            "subtotal_display": str(cart.get("subtotal_display") or _money(subtotal_q)),
            "grand_total_q": subtotal_q,
            "grand_total_display": str(cart.get("subtotal_display") or _money(subtotal_q)),
            "minimum_order_progress": min_order,
            "checkout_enabled": bool(cart.get("count", 0) and min_order is None),
        },
    }


def cart_line_payload(intent: SetQtyIntent, cart: dict[str, Any]) -> dict[str, Any]:
    """Return the changed line as a compact JSON object."""
    line = next(
        (
            item
            for item in cart.get("items") or []
            if item.get("sku") == intent.sku
        ),
        None,
    )
    if line is None:
        return {
            "sku": intent.sku,
            "line_id": intent.line_id,
            "qty": 0,
            "unit_price_q": 0,
            "line_total_q": 0,
            "line_total_display": _money(0),
            "name": getattr(intent.product, "name", intent.sku),
        }

    qty = int(line.get("qty", 0) or 0)
    unit_price_q = int(line.get("unit_price_q", 0) or 0)
    line_total_q = int(line.get("line_total_q", 0) or 0)
    return {
        "sku": str(line.get("sku") or intent.sku),
        "line_id": line.get("line_id") or intent.line_id,
        "qty": qty,
        "unit_price_q": unit_price_q,
        "line_total_q": line_total_q,
        "line_total_display": _money(line_total_q),
        "name": line.get("name") or getattr(intent.product, "name", intent.sku),
    }


def _money(value_q: int | None) -> str:
    return f"R$ {format_money(int(value_q or 0))}"


def _perf_step(perf, name: str):
    if perf is None:
        return nullcontext()
    return perf.step(name)
