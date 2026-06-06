"""Checkout context — read-side facades for the checkout flow.

Clean read facades (policy/data, no presentation): customer name lookup,
saved-address resolution, channel payment methods, preorder config, session
held qty, loyalty balance, and the availability read. Lives in the
orchestrator read-side (``shop/projections/``).

The repricing and stock-shortfall read-models (which embedded ``format_money``
and copy) drained to ``shop/projections/checkout.py`` (data) +
``storefront/presentation/checkout.py`` (display).
"""

from __future__ import annotations

import logging
from datetime import date

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
        logger.debug("checkout_context.preorder_config degraded; using fallback", exc_info=True)
        return 30, []


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
