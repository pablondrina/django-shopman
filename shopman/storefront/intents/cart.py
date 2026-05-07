"""Cart intent extraction.

interpret_set_qty() absorbs the product-lookup and cart-line-resolution logic
from CartSetQtyBySkuView, leaving the view with only HTTP parsing and
rendering.

Helper functions accept scalars (not request objects) so they are testable
without a Django request.
"""

from __future__ import annotations

from types import SimpleNamespace

from shopman.shop.services import cart_context

from .types import CartIntentResult, SetQtyIntent

# ── Public API ────────────────────────────────────────────────────────────────


def interpret_set_qty(sku: str, qty: int, cart: dict) -> CartIntentResult:
    """Resolve action for a set-qty-by-SKU POST.

    Steps:
     1. Look up published product by SKU
     2. Find existing cart line for the SKU
     3. Determine action: "remove" (qty==0) | "update" (line exists) | "add"
     4. Resolve listing price and D-1 flag for "add"
    """
    line = next(
        (item for item in cart.get("items") or [] if item.get("sku") == sku),
        None,
    )
    product_ctx = cart_context.product_context(sku)

    if qty == 0 and line is not None:
        product = (
            product_ctx.product
            if product_ctx
            else SimpleNamespace(sku=sku, name=line.get("name") or sku)
        )
        return CartIntentResult(
            intent=SetQtyIntent(
                sku=sku,
                qty=qty,
                action="remove",
                line_id=line["line_id"],
                unit_price_q=0,
                is_d1=False,
                product=product,
            ),
            error_type=None,
            error_context={},
        )

    if not product_ctx:
        return CartIntentResult(intent=None, error_type="not_found", error_context={})

    product = product_ctx.product

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
