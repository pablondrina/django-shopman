from __future__ import annotations

import pytest
from django.core.cache import cache

from shopman.shop.models import Channel
from shopman.shop.services.channel_policy import (
    ChannelPolicyResolution,
    resolve_channel_policy,
)

pytestmark = pytest.mark.django_db


def test_resolves_channel_policy_from_channel_config():
    cache.clear()
    Channel.objects.create(
        ref="whatsapp",
        config={
            "payment": {"method": ["pix", "cash"], "timing": "at_commit"},
            "stock": {
                "hold_ttl_minutes": 10,
                "excluded_positions": ["ontem"],
                "check_on_commit": True,
            },
            "notifications": {"backend": "manychat", "fallback_chain": ["sms"]},
        },
    )

    policy = resolve_channel_policy("whatsapp")

    assert isinstance(policy, ChannelPolicyResolution)
    assert policy.channel_ref == "whatsapp"
    assert policy.payment_methods == ("pix", "cash")
    assert policy.payment_timing == "at_commit"
    assert policy.requires_payment_gate is True
    assert policy.supports_access_link is True
    assert policy.stock_scope["excluded_positions"] == ("ontem",)
    assert policy.stock_scope["check_on_commit"] is True
    assert policy.notifications["backend"] == "manychat"
    assert "pay" in policy.action_refs


def test_surface_policy_hints_narrow_actions_without_changing_config():
    cache.clear()
    Channel.objects.create(
        ref="pickup-only",
        config={
            "payment": {"method": "cash", "timing": "post_commit"},
            "surface_policy": {
                "fulfillment_types": ["pickup"],
                "can_rate": False,
                "supports_access_link": False,
            },
        },
    )

    policy = resolve_channel_policy("pickup-only")

    assert policy.fulfillment_types == ("pickup",)
    assert policy.can_rate is False
    assert policy.supports_access_link is False
    assert "rate" not in policy.action_refs
    assert "access_link" not in policy.action_refs


def test_external_marketplace_does_not_require_shopman_payment_gate():
    cache.clear()
    Channel.objects.create(
        ref="ifood",
        config={
            "payment": {"method": "external", "timing": "external"},
            "fulfillment": {"timing": "external"},
            "pricing": {"policy": "external"},
            "editing": {"policy": "locked"},
            "notifications": {"backend": "webhook", "fallback_chain": []},
        },
    )

    policy = resolve_channel_policy("ifood")

    assert policy.can_checkout is False
    assert policy.can_cancel is False
    assert policy.can_rate is False
    assert policy.requires_payment_gate is False
    assert policy.action_refs == ("track",)
