"""Checkout context and validation helpers backed by kernel services."""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal

from shopman.utils.monetary import format_money

logger = logging.getLogger(__name__)


def customer_name_by_phone(phone: str) -> str:
    from shopman.guestman.services import customer as customer_service

    customer = customer_service.get_by_phone(phone)
    if customer and customer.first_name:
        return customer.name
    return ""


def saved_address_text(*, customer_uuid, address_id_raw: str) -> str:
    """Resolve a customer saved address to the flat checkout address string."""
    try:
        from shopman.guestman.services import address as address_service
        from shopman.guestman.services import customer as customer_service

        customer_obj = customer_service.get_by_uuid(customer_uuid)
        if not customer_obj:
            return ""
        addr = address_service.get_address(customer_obj.ref, int(address_id_raw))
        if not addr:
            return ""
        parts = [addr.formatted_address]
        if addr.complement:
            parts.append(f"- {addr.complement}")
        return " ".join(parts)
    except (ValueError, Exception):
        return ""


def payment_methods(channel_ref: str) -> list[str]:
    from shopman.shop.config import ChannelConfig
    from shopman.shop.models import Channel

    try:
        channel = Channel.objects.get(ref=channel_ref)
    except Channel.DoesNotExist:
        return ["cash"]
    return ChannelConfig.for_channel(channel).payment.available_methods


def preorder_config() -> tuple[int, list]:
    """Return (max_preorder_days, closed_dates) from shop defaults."""
    try:
        from shopman.shop.models import Shop

        shop = Shop.load()
        max_preorder_days = int((shop.defaults or {}).get("max_preorder_days", 30)) if shop else 30
        closed_dates = ((shop.defaults or {}).get("closed_dates", [])) if shop else []
        return max_preorder_days, closed_dates
    except Exception:
        return 30, []


def repricing_warnings(cart: dict) -> list[dict]:
    items = cart.get("items", [])
    if not items:
        return []

    from shopman.offerman.models import Product

    skus = [item.get("sku", "") for item in items if item.get("sku")]
    if not skus:
        return []

    products_by_sku = {
        p.sku: p
        for p in Product.objects.filter(sku__in=skus).only("sku", "name", "base_price_q")
    }
    warnings = []
    for item in items:
        sku = item.get("sku", "")
        product = products_by_sku.get(sku)
        if not product:
            continue
        cart_price = int(item.get("unit_price_q", 0))
        current_price = int(product.base_price_q)
        if cart_price <= 0 or current_price <= 0:
            continue
        if abs(current_price - cart_price) / current_price > 0.05:
            warnings.append({
                "sku": sku,
                "name": product.name or sku,
                "cart_price_display": f"R$ {format_money(cart_price)}",
                "current_price_display": f"R$ {format_money(current_price)}",
                "message": (
                    f"O preço de {product.name or sku} mudou para "
                    f"R$ {format_money(current_price)}. Deseja continuar?"
                ),
            })
    return warnings


def cart_stock_errors(
    *,
    session_key: str,
    cart: dict,
    channel_ref: str,
    target_date: date | None = None,
) -> tuple[list[dict], bool]:
    items = cart.get("items", [])
    if not items:
        return [], False

    session_held = session_held_qty(session_key, target_date=target_date)
    warnings = []
    checked = 0
    skipped = 0
    for item in items:
        sku = item.get("sku", "")
        qty = int(Decimal(str(item.get("qty", 0))))
        avail = _availability_for_sku(sku, channel_ref=channel_ref, target_date=target_date)
        if avail is None:
            skipped += 1
            continue
        checked += 1
        if avail.get("availability_policy") == "demand_ok" and not avail.get("is_paused", False):
            continue
        available_qty = int(avail.get("total_promisable", Decimal("0"))) + session_held.get(sku, 0)
        if qty > available_qty:
            name = item.get("name") or sku
            message = (
                f"{name}: disponível {available_qty} unidade(s) no momento."
                if available_qty > 0
                else f"{name} está esgotado no momento."
            )
            warnings.append({
                "line_id": item.get("line_id", ""),
                "sku": sku,
                "requested_qty": qty,
                "available_qty": available_qty,
                "message": message,
            })

    service_unavailable = skipped > 0 and checked == 0
    if service_unavailable:
        logger.warning(
            "checkout.stock_check_unavailable: %d item(s) skipped",
            skipped,
        )
    return warnings, service_unavailable


def session_held_qty(session_key: str, *, target_date: date | None = None) -> dict[str, int]:
    if not session_key:
        return {}
    from shopman.stockman import StockHolds

    holds = StockHolds.find_active_by_reference(session_key)
    held: dict[str, int] = {}
    for hold in holds:
        if target_date is not None and hold.target_date != target_date:
            continue
        held[hold.sku] = held.get(hold.sku, 0) + int(hold.quantity)
    return held


def loyalty_balance(customer_uuid) -> int:
    if not customer_uuid:
        return 0
    try:
        from shopman.guestman.contrib.loyalty import LoyaltyService

        balance = (
            LoyaltyService.get_balance_by_uuid(customer_uuid)
            if hasattr(LoyaltyService, "get_balance_by_uuid")
            else 0
        )
        if balance <= 0:
            from shopman.guestman.services import customer as customer_service

            customer_obj = customer_service.get_by_uuid(customer_uuid)
            if customer_obj:
                balance = LoyaltyService.get_balance(customer_obj.ref)
        return max(0, balance)
    except Exception:
        logger.exception("loyalty_balance_failed")
        return 0


def _availability_for_sku(
    sku: str,
    *,
    channel_ref: str,
    target_date: date | None = None,
) -> dict | None:
    try:
        from shopman.stockman.services.availability import availability_for_sku

        from shopman.shop.adapters import stock as stock_adapter

        scope = stock_adapter.get_channel_scope(channel_ref)
        return availability_for_sku(
            sku,
            target_date=target_date,
            safety_margin=scope["safety_margin"],
            allowed_positions=scope["allowed_positions"],
            excluded_positions=scope.get("excluded_positions"),
        )
    except Exception as e:
        logger.warning("checkout_availability_lookup_failed sku=%s: %s", sku, e, exc_info=True)
        return None
