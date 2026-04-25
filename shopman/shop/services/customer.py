"""
Customer resolution service.

Core: customers.services.customer (get_by_phone, create, etc.) via customer adapter

Strategy registry
-----------------
The service dispatches to a registered strategy keyed by handle_type or
channel_ref. Generic strategies (manychat, ifood) are registered at module
load. Instance-specific strategies are registered by the instance's app
configuration via register_strategy().

    from shopman.shop.services.customer import register_strategy
    register_strategy("my-channel", my_handle_fn)
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable

from shopman.shop.adapters import get_adapter

logger = logging.getLogger(__name__)

# ── Strategy registry ──

_STRATEGIES: dict[str, Callable] = {}


def register_strategy(key: str, fn: Callable) -> None:
    """Register a customer resolution strategy for the given key.

    The key is matched against order.handle_type first, then order.channel_ref.
    """
    _STRATEGIES[key] = fn


def ensure(order) -> None:
    """
    Resolve or create the customer for the order.

    Lookup order: handle_type first, then channel_ref. Falls back to
    _handle_phone when no strategy is registered for either.

    Saves customer_ref in order.data["customer_ref"].

    SYNC — needs customer_ref before proceeding.
    """
    if not _customers_available():
        return

    channel_ref = order.channel_ref or ""
    handle_type = getattr(order, "handle_type", "") or ""

    try:
        fn = _STRATEGIES.get(handle_type) or _STRATEGIES.get(channel_ref)
        if fn:
            customer = fn(order)
        else:
            customer = _handle_phone(order)
    except _SkipAnonymous:
        return
    except Exception as exc:
        logger.warning("customer.ensure: failed for order %s: %s", order.ref, exc)
        return

    if customer and order.data.get("customer_ref") != customer["ref"]:
        order.data["customer_ref"] = customer["ref"]
        order.save(update_fields=["data", "updated_at"])

    if customer:
        _save_delivery_address(customer, order)
        _create_timeline_event(customer, order)
        _update_insights(customer["ref"])


# ── Built-in strategies ──


def _handle_manychat(order):
    adapter = get_adapter("customer")
    subscriber_id = order.handle_ref
    customer_data = _get_customer_data(order)
    name = customer_data.get("name", "")

    if not subscriber_id:
        raise _SkipAnonymous()

    customer = adapter.get_customer_by_identifier("manychat", subscriber_id)
    if customer:
        _maybe_update_name(adapter, customer, name)
        return customer

    phone = _normalize_phone_safe(customer_data.get("phone", ""))

    if phone:
        customer = adapter.get_customer_by_phone(phone)
        if customer:
            adapter.create_identifier(customer["ref"], "manychat", subscriber_id, is_primary=True)
            _maybe_update_name(adapter, customer, name)
            return customer

    first_name, last_name = _split_name(name)
    ref = f"MC-{uuid.uuid4().hex[:8].upper()}"
    customer = adapter.create_customer(
        ref=ref, first_name=first_name, last_name=last_name,
        phone=phone, customer_type="individual", source_system="manychat",
    )
    adapter.create_identifier(customer["ref"], "manychat", subscriber_id, is_primary=True)
    return customer


def _handle_ifood(order):
    adapter = get_adapter("customer")
    customer_data = _get_customer_data(order)
    ifood_order_id = order.external_ref or order.handle_ref
    name = customer_data.get("name", "")

    if not ifood_order_id:
        raise _SkipAnonymous()

    customer = adapter.get_customer_by_identifier("ifood", ifood_order_id)
    if customer:
        _maybe_update_name(adapter, customer, name)
        return customer

    first_name, last_name = _split_name(name)
    ref = f"IF-{uuid.uuid4().hex[:8].upper()}"
    customer = adapter.create_customer(
        ref=ref, first_name=first_name or "iFood",
        last_name=last_name or f"#{ifood_order_id[:8]}",
        phone="", customer_type="individual", source_system="ifood",
    )
    adapter.create_identifier(customer["ref"], "ifood", ifood_order_id, is_primary=True)
    return customer


def _handle_phone(order):
    adapter = get_adapter("customer")
    customer_data = _get_customer_data(order)
    phone_raw = customer_data.get("phone") or order.handle_ref
    name = customer_data.get("name", "")

    if not phone_raw:
        raise _SkipAnonymous()

    phone = _normalize_phone_safe(phone_raw)
    if not phone:
        raise _SkipAnonymous()

    customer = adapter.get_customer_by_phone(phone)
    if customer:
        _maybe_update_name(adapter, customer, name)
        return customer

    first_name, last_name = _split_name(name)
    ref = f"CLI-{uuid.uuid4().hex[:8].upper()}"
    customer = adapter.create_customer(
        ref=ref, first_name=first_name, last_name=last_name,
        phone=phone, customer_type="individual", source_system="shopman",
    )
    return customer


# Register generic strategies at module load
register_strategy("manychat", _handle_manychat)
register_strategy("ifood", _handle_ifood)


# ── helpers ──


class _SkipAnonymous(Exception):
    pass


def _customers_available() -> bool:
    try:
        from shopman.guestman.services import customer as _svc  # noqa: F401
        return True
    except ImportError:
        return False


def _get_customer_data(order) -> dict:
    return order.snapshot.get("data", {}).get("customer", {}) or order.data.get("customer", {})


def _split_name(full_name: str) -> tuple[str, str]:
    parts = full_name.strip().split(None, 1)
    return (parts[0] if parts else "", parts[1] if len(parts) > 1 else "")


def _normalize_phone_safe(phone_raw: str) -> str:
    if not phone_raw:
        return ""
    try:
        from shopman.utils.phone import normalize_phone
        return normalize_phone(phone_raw)
    except Exception:
        return phone_raw


def _maybe_update_name(adapter, customer: dict, name: str) -> None:
    if name and not customer.get("first_name"):
        first_name, last_name = _split_name(name)
        try:
            adapter.update_customer(customer["ref"], first_name=first_name, last_name=last_name)
        except Exception:
            logger.debug("customer.update_name: failed for ref=%s", customer.get("ref"), exc_info=True)


def _save_delivery_address(customer: dict, order) -> None:
    delivery_address = (
        order.data.get("delivery_address")
        or order.snapshot.get("data", {}).get("delivery_address")
    )
    if not delivery_address:
        return

    adapter = get_adapter("customer")
    customer_ref = customer["ref"]

    try:
        if adapter.has_address(customer_ref, delivery_address):
            return
        has_any = adapter.has_any_address(customer_ref)
        adapter.create_address(
            customer_ref=customer_ref,
            label="home",
            formatted_address=delivery_address,
            is_default=not has_any,
        )
    except Exception as exc:
        logger.warning("customer.ensure: address save failed: %s", exc)


def _create_timeline_event(customer: dict, order) -> None:
    from shopman.utils.monetary import format_money

    adapter = get_adapter("customer")
    customer_ref = customer["ref"]

    try:
        if adapter.has_timeline_event(customer_ref, "order", f"order:{order.ref}"):
            return

        adapter.log_timeline_event(
            customer_ref=customer_ref,
            event_type="order",
            title=f"Pedido {order.ref}",
            description=f"Pedido realizado via {order.channel_ref} — R$ {format_money(order.total_q)}",
            channel=order.channel_ref,
            reference=f"order:{order.ref}",
            metadata={"order_ref": order.ref, "total_q": order.total_q},
            created_by="shopman.shop.services.customer.ensure",
        )
    except Exception as exc:
        logger.warning("customer.ensure: timeline event failed: %s", exc)


def _update_insights(customer_ref: str) -> None:
    adapter = get_adapter("customer")
    try:
        adapter.recalculate_insights(customer_ref)
    except Exception as exc:
        logger.warning("customer.ensure: insight recalculation failed: %s", exc)
