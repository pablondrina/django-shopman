"""Resolved channel policy for projection builders.

This module resolves ``ChannelConfig`` plus optional surface policy hints into
an internal object used by projection builders. It does not define lifecycle,
pricing, stock, or payment rules, and it is not a public surface contract.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from shopman.shop.config import ChannelConfig, deep_merge

_DIGITAL_PAYMENT_METHODS = {"pix", "card"}
_DEFAULT_FULFILLMENT_TYPES = ("pickup", "delivery")
_VALID_FULFILLMENT_TYPES = set(_DEFAULT_FULFILLMENT_TYPES)
_DEFAULT_TRACK_ACTION = "track"


@dataclass(frozen=True)
class ChannelPolicyResolution:
    """Internal policy resolution for a single channel."""

    channel_ref: str
    payment_methods: tuple[str, ...]
    payment_timing: str
    fulfillment_timing: str
    fulfillment_types: tuple[str, ...]
    stock_scope: dict[str, Any]
    notifications: dict[str, Any]
    can_checkout: bool
    can_cancel: bool
    can_rate: bool
    requires_payment_gate: bool
    supports_access_link: bool
    action_refs: tuple[str, ...]
    handle_label: str
    handle_placeholder: str


def resolve_channel_policy(channel_or_ref: Any) -> ChannelPolicyResolution:
    """Return projection-builder policy derived from canonical channel config.

    ``ChannelConfig`` remains the source of truth. The optional
    ``surface_policy`` JSON key in Shop.defaults/Channel.config is a policy hint
    for fields that are not first-class ChannelConfig aspects yet.
    """

    channel_ref, overrides = _resolve_channel_ref_and_overrides(channel_or_ref)
    config = ChannelConfig.for_channel(channel_or_ref)

    payment_methods = tuple(str(method) for method in config.payment.available_methods)
    fulfillment_types = _fulfillment_types(overrides)
    requires_payment_gate = (
        config.payment.timing != "external"
        and any(method in _DIGITAL_PAYMENT_METHODS for method in payment_methods)
    )
    supports_access_link = _bool_override(
        overrides,
        "supports_access_link",
        _default_supports_access_link(channel_ref, config),
    )
    can_checkout = _bool_override(
        overrides,
        "can_checkout",
        config.editing.policy == "open" and config.payment.timing != "external",
    )
    can_cancel = _bool_override(
        overrides,
        "can_cancel",
        config.fulfillment.timing != "external",
    )
    can_rate = _bool_override(
        overrides,
        "can_rate",
        config.fulfillment.timing != "external" and channel_ref not in {"pdv", "pos"},
    )

    return ChannelPolicyResolution(
        channel_ref=channel_ref,
        payment_methods=payment_methods,
        payment_timing=config.payment.timing,
        fulfillment_timing=config.fulfillment.timing,
        fulfillment_types=fulfillment_types,
        stock_scope={
            "hold_ttl_minutes": config.stock.hold_ttl_minutes,
            "planned_hold_ttl_hours": config.stock.planned_hold_ttl_hours,
            "safety_margin": config.stock.safety_margin,
            "allowed_positions": config.stock.allowed_positions,
            "excluded_positions": tuple(config.stock.excluded_positions),
            "check_on_commit": config.stock.check_on_commit,
            "low_stock_threshold": config.stock.low_stock_threshold,
        },
        notifications={
            "backend": config.notifications.backend,
            "fallback_chain": tuple(config.notifications.fallback_chain),
            "routing": config.notifications.routing,
        },
        can_checkout=can_checkout,
        can_cancel=can_cancel,
        can_rate=can_rate,
        requires_payment_gate=requires_payment_gate,
        supports_access_link=supports_access_link,
        action_refs=_action_refs(
            overrides=overrides,
            can_checkout=can_checkout,
            can_cancel=can_cancel,
            can_rate=can_rate,
            requires_payment_gate=requires_payment_gate,
            supports_access_link=supports_access_link,
        ),
        handle_label=config.handle_label,
        handle_placeholder=config.handle_placeholder,
    )


def _resolve_channel_ref_and_overrides(channel_or_ref: Any) -> tuple[str, dict[str, Any]]:
    from shopman.shop.models import Channel, Shop

    if isinstance(channel_or_ref, str):
        channel_ref = channel_or_ref
        try:
            channel = Channel.objects.get(ref=channel_ref)
        except Channel.DoesNotExist:
            channel = None
    else:
        channel = channel_or_ref
        channel_ref = str(getattr(channel, "ref", "") or "")

    overrides: dict[str, Any] = {}
    shop = getattr(channel, "shop", None) if channel is not None else None
    if shop is None:
        shop = Shop.load()
    if shop and isinstance(shop.defaults, Mapping):
        overrides = deep_merge(overrides, _mapping(shop.defaults.get("surface_policy")))
    if channel is not None and isinstance(channel.config, Mapping):
        overrides = deep_merge(overrides, _mapping(channel.config.get("surface_policy")))
    return channel_ref, overrides


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _fulfillment_types(overrides: Mapping[str, Any]) -> tuple[str, ...]:
    raw = overrides.get("fulfillment_types")
    if isinstance(raw, str):
        raw_values: Iterable[Any] = (raw,)
    elif isinstance(raw, Iterable):
        raw_values = raw
    else:
        return _DEFAULT_FULFILLMENT_TYPES

    values = tuple(
        str(value)
        for value in raw_values
        if str(value) in _VALID_FULFILLMENT_TYPES
    )
    return values or _DEFAULT_FULFILLMENT_TYPES


def _bool_override(overrides: Mapping[str, Any], key: str, default: bool) -> bool:
    value = overrides.get(key)
    return value if isinstance(value, bool) else default


def _default_supports_access_link(channel_ref: str, config: ChannelConfig) -> bool:
    notification_backends = {
        config.notifications.backend,
        *config.notifications.fallback_chain,
    }
    return channel_ref in {"whatsapp", "manychat"} or "manychat" in notification_backends


def _action_refs(
    *,
    overrides: Mapping[str, Any],
    can_checkout: bool,
    can_cancel: bool,
    can_rate: bool,
    requires_payment_gate: bool,
    supports_access_link: bool,
) -> tuple[str, ...]:
    raw = overrides.get("action_refs")
    if isinstance(raw, Iterable) and not isinstance(raw, str):
        actions = tuple(str(action) for action in raw if str(action))
        if actions:
            return actions

    actions: list[str] = []
    if can_checkout:
        actions.append("checkout")
    if requires_payment_gate:
        actions.append("pay")
    actions.append(_DEFAULT_TRACK_ACTION)
    if can_cancel:
        actions.append("cancel")
    if can_rate:
        actions.append("rate")
    if supports_access_link:
        actions.append("access_link")
    return tuple(actions)
