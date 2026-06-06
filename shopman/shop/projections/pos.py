"""POS read-side — the open-comanda projection (DADO).

This is the read-model the POS surface renders for an open ``Session`` (the
comanda): its lines, customer, fulfillment, payment intent and the per-line
manual-discount state needed to re-hydrate the cart. It carries semantic data
only (``_q`` cents, refs, booleans) — no copy, no money formatting, no HTML.

It lives on the read-side so the write-side commands in
``shopman.shop.services.pos`` stay command/saga/policy only: they mutate the
session and delegate the UI payload here (``shop`` → ``shop`` is boundary-safe).
The POS *terminal page* chrome (product grid, tab cards, checkout-field
contract, cash runtime) is POS-surface-specific and lives in
``shopman.backstage.projections.pos``.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _int_q(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _is_delivery_fee_item(item: dict) -> bool:
    return bool((item.get("meta") or {}).get("type") == "delivery_fee")


def _display_tab_ref(tab_ref: str) -> str:
    value = str(tab_ref or "").strip()
    if value.isdigit():
        return value.lstrip("0") or "0"
    return value


def _tab_payload_line_discount(item: dict) -> dict | None:
    """Surface the operator's per-line manual discount (percent) for restore."""
    manual = (item.get("meta") or {}).get("manual_discount") or {}
    value = manual.get("value")
    if not value:
        return None
    return {"value": value, "reason": manual.get("reason", "cortesia")}


def _tab_line_display_price_q(item: dict) -> int:
    """Pre-discount unit price for display: when a manual discount won, the
    DiscountModifier stored the original price; otherwise the stored unit price."""
    manual = (item.get("meta") or {}).get("manual_discount") or {}
    if manual.get("value"):
        for mod in (item.get("modifiers_applied") or []):
            if mod.get("type") == "manual" and mod.get("original_price_q"):
                return int(mod["original_price_q"])
    return int(item.get("unit_price_q", 0))


def _tab_payload_payment_tenders(payment: dict) -> list[dict]:
    tenders = payment.get("tenders")
    if not isinstance(tenders, list) or not tenders:
        return []
    method = str(payment.get("method") or "").strip().lower()
    if method == "mixed" or len(tenders) > 1:
        return tenders
    return []


def build_open_tab(session) -> dict:
    """Read-model of an open POS comanda, rendered by the POS surface.

    The stored ``tab_ref``/``tab_display`` are already normalized at open time,
    so they are read back verbatim (no re-normalization).
    """
    data = session.data or {}
    customer = data.get("customer") or {}
    payment = data.get("payment") or {}
    fiscal = data.get("fiscal") or {}
    receipt = data.get("receipt") or {}
    discount = data.get("manual_discount") or {}
    tab_ref = str(data.get("tab_ref") or session.handle_ref or "")
    tab_display = str(data.get("tab_display") or "") or _display_tab_ref(tab_ref)
    fired_lines = set(data.get("fired_lines") or [])
    items = [
        {
            "line_id": item.get("line_id", ""),
            "sku": item["sku"],
            "name": item.get("name", item["sku"]),
            "price_q": _tab_line_display_price_q(item),
            "qty": int(item.get("qty", 1)),
            "notes": (item.get("meta") or {}).get("notes", ""),
            "is_d1": bool(item.get("is_d1")),
            "fired": item.get("line_id", "") in fired_lines,
            "discount": _tab_payload_line_discount(item),
        }
        for item in (session.items or [])
        if not _is_delivery_fee_item(item)
    ]

    return {
        "session_key": session.session_key,
        "tab_session_key": session.session_key,
        "tab_ref": tab_ref,
        "tab_display": tab_display,
        "items": items,
        "customer_phone": customer.get("phone", ""),
        "customer_name": customer.get("name", ""),
        "customer_ref": customer.get("ref", data.get("customer_ref", "")),
        "customer_group": customer.get("group", ""),
        "customer_tax_id": customer.get("tax_id", ""),
        "customer_email": customer.get("email", ""),
        "fulfillment_type": data.get("fulfillment_type", "pickup") or "pickup",
        "delivery_address": data.get("delivery_address", ""),
        "delivery_address_structured": data.get("delivery_address_structured", {}),
        "delivery_date": data.get("delivery_date", ""),
        "delivery_time_slot": data.get("delivery_time_slot", ""),
        "delivery_fee_q": data.get("delivery_fee_q", 0),
        "order_notes": data.get("order_notes", ""),
        "payment_method": payment.get("method", "cash"),
        "payment_collection": payment.get("collection", "terminal"),
        "payment_tenders": _tab_payload_payment_tenders(payment),
        "tendered_amount_q": "",
        "client_request_id": data.get("client_request_id", (data.get("pos") or {}).get("client_request_id", "")),
        "issue_fiscal_document": bool(fiscal.get("issue_document")),
        "receipt_mode": receipt.get("mode", "none"),
        "receipt_email": receipt.get("email", ""),
        "discount_type": discount.get("type", "percent"),
        "discount_value": str(discount.get("value", "")) if discount.get("value") else "",
        "discount_reason": discount.get("reason", "cortesia"),
    }


def customer_history_summary(customer_ref: str, *, limit: int = 5) -> dict:
    """Return compact consumption memory for POS lookup surfaces."""
    if not customer_ref:
        return {}
    try:
        from shopman.orderman.services import CustomerOrderHistoryService

        stats = CustomerOrderHistoryService.get_customer_stats(customer_ref)
        recent = CustomerOrderHistoryService.list_customer_orders(customer_ref, limit=limit)
    except Exception:
        logger.exception("pos_customer_history_failed customer_ref=%s", customer_ref)
        return {}

    favorite = ""
    favorite_item: dict = {}
    last_order_items: list[dict] = []
    counts: dict[str, tuple[str, float, int]] = {}
    if recent:
        for item in recent[0].items or []:
            sku = str(item.get("sku") or "")
            if not sku or sku == "__DELIVERY_FEE__":
                continue
            try:
                qty = int(item.get("qty") or 1)
            except (TypeError, ValueError):
                qty = 1
            last_order_items.append({
                "sku": sku,
                "name": str(item.get("name") or sku),
                "qty": max(1, qty),
                "unit_price_q": _int_q(item.get("unit_price_q") or item.get("price_q") or item.get("unit_price") or 0),
            })
    for order in recent:
        for item in order.items or []:
            sku = str(item.get("sku") or "")
            if not sku or sku == "__DELIVERY_FEE__":
                continue
            name = str(item.get("name") or sku)
            try:
                qty = float(item.get("qty") or 1)
            except (TypeError, ValueError):
                qty = 1
            unit_price_q = _int_q(item.get("unit_price_q") or item.get("price_q") or item.get("unit_price") or 0)
            prev_name, prev_qty, prev_price_q = counts.get(sku, (name, 0, unit_price_q))
            counts[sku] = (prev_name or name, prev_qty + qty, prev_price_q or unit_price_q)
    if counts:
        fav_sku, fav_row = max(counts.items(), key=lambda row: row[1][1])
        favorite = fav_row[0]
        favorite_item = {
            "sku": fav_sku,
            "name": fav_row[0],
            "qty": 1,
            "unit_price_q": fav_row[2],
        }

    return {
        "total_orders": stats.total_orders,
        "total_spent_q": stats.total_spent_q,
        "average_order_q": stats.average_order_q,
        "last_order_at": stats.last_order_at,
        "favorite_product": favorite,
        "favorite_item": favorite_item,
        "last_order_items": last_order_items[:8],
    }
