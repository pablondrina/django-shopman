"""Cart intent extraction.

interpret_add_to_cart() and interpret_set_qty() absorb the product-lookup
and cart-line-resolution logic from AddToCartView, QuickAddView, and
CartSetQtyBySkuView, leaving each view with only HTTP parsing and rendering.

Helper functions accept scalars (not request objects) so they are testable
without a Django request.
"""

from __future__ import annotations

from shopman.shop.services import cart_context

from .types import AddToCartIntent, CartIntentResult, SetQtyIntent

# ── Public API ────────────────────────────────────────────────────────────────


def interpret_add_to_cart(
    sku: str,
    qty: int,
    *,
    picker_origin: str = "menu",
) -> CartIntentResult:
    """Resolve product context for an add-to-cart POST.

    Steps:
     1. Look up published product by SKU
     2. Check is_sellable
     3. Resolve listing price and D-1 flag
    """
    product_ctx = cart_context.product_context(sku)
    if not product_ctx:
        return CartIntentResult(intent=None, error_type="not_found", error_context={})

    product = product_ctx.product
    if not product.is_sellable:
        return CartIntentResult(
            intent=None,
            error_type="not_sellable",
            error_context={"product": product, "qty": qty, "picker_origin": picker_origin},
        )

    return CartIntentResult(
        intent=AddToCartIntent(
            sku=sku,
            qty=qty,
            unit_price_q=product_ctx.unit_price_q,
            is_d1=product_ctx.is_d1,
            picker_origin=picker_origin,
            product=product,
        ),
        error_type=None,
        error_context={},
    )


def interpret_set_qty(sku: str, qty: int, cart: dict) -> CartIntentResult:
    """Resolve action for a set-qty-by-SKU POST.

    Steps:
     1. Look up published product by SKU
     2. Find existing cart line for the SKU
     3. Determine action: "remove" (qty==0) | "update" (line exists) | "add"
     4. Resolve listing price and D-1 flag for "add"
    """
    product_ctx = cart_context.product_context(sku)
    if not product_ctx:
        return CartIntentResult(intent=None, error_type="not_found", error_context={})

    product = product_ctx.product
    line = next(
        (item for item in cart.get("items") or [] if item.get("sku") == sku),
        None,
    )

    if qty == 0:
        action = "remove"
        line_id = line["line_id"] if line else None
    elif line is not None:
        action = "update"
        line_id = line["line_id"]
    else:
        action = "add"
        line_id = None

    return CartIntentResult(
        intent=SetQtyIntent(
            sku=sku,
            qty=qty,
            action=action,
            line_id=line_id,
            unit_price_q=product_ctx.unit_price_q if action == "add" else 0,
            is_d1=product_ctx.is_d1,
            product=product,
        ),
        error_type=None,
        error_context={},
    )
