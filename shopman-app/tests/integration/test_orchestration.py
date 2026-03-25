"""Integration tests for channels configuration.

Tests cover:
- Channel presets produce valid ChannelConfig dicts
- ChannelConfig from_dict / to_dict roundtrip
- ChannelConfig validation
- ChannelConfig deep_merge cascata
"""

import pytest
from django.test import TestCase
from shopman.ordering.models import Channel

from channels import presets
from channels.config import ChannelConfig, deep_merge
from channels.topics import CUSTOMER_ENSURE, PIX_GENERATE, STOCK_COMMIT, STOCK_HOLD


class PresetValidationTest(TestCase):
    """Presets return valid, complete ChannelConfig dicts."""

    def test_pos_preset_returns_valid_config(self):
        config = presets.pos()
        assert config["confirmation"]["mode"] == "immediate"
        assert config["payment"]["method"] == "counter"
        assert config["stock"]["hold_ttl_minutes"] == 5

    def test_remote_preset_returns_valid_config(self):
        config = presets.remote()
        assert config["confirmation"]["mode"] == "optimistic"
        assert config["confirmation"]["timeout_minutes"] == 10
        assert config["payment"]["method"] == "pix"
        assert config["stock"]["hold_ttl_minutes"] == 30

    def test_marketplace_preset_returns_valid_config(self):
        config = presets.marketplace()
        assert config["confirmation"]["mode"] == "immediate"
        assert config["payment"]["method"] == "external"
        assert config["notifications"]["backend"] == "none"

    def test_pos_preset_pipeline(self):
        config = presets.pos()
        assert CUSTOMER_ENSURE in config["pipeline"]["on_commit"]
        assert STOCK_COMMIT in config["pipeline"]["on_confirmed"]

    def test_remote_preset_pipeline(self):
        config = presets.remote()
        assert STOCK_HOLD in config["pipeline"]["on_commit"]
        assert PIX_GENERATE in config["pipeline"]["on_confirmed"]
        assert STOCK_COMMIT in config["pipeline"]["on_payment_confirmed"]

    def test_marketplace_preset_pipeline(self):
        config = presets.marketplace()
        assert CUSTOMER_ENSURE in config["pipeline"]["on_commit"]
        assert STOCK_COMMIT in config["pipeline"]["on_confirmed"]

    def test_pos_preset_rules(self):
        config = presets.pos()
        assert "business_hours" in config["rules"]["validators"]
        assert "shop.employee_discount" in config["rules"]["modifiers"]

    def test_remote_preset_rules(self):
        config = presets.remote()
        assert "business_hours" in config["rules"]["validators"]
        assert "min_order" in config["rules"]["validators"]
        assert "shop.happy_hour" in config["rules"]["modifiers"]
        assert "stock" in config["rules"]["checks"]


class ChannelConfigTest(TestCase):
    """ChannelConfig roundtrip, validation, and cascata."""

    def test_from_dict_roundtrip(self):
        original = ChannelConfig()
        d = original.to_dict()
        restored = ChannelConfig.from_dict(d)
        assert restored.to_dict() == d

    def test_from_dict_ignores_unknown_keys(self):
        d = ChannelConfig.defaults()
        d["payment"]["unknown_key"] = "ignored"
        config = ChannelConfig.from_dict(d)
        assert config.payment.method == "counter"

    def test_validate_valid_config(self):
        config = ChannelConfig()
        config.validate()  # should not raise

    def test_validate_invalid_confirmation_mode(self):
        config = ChannelConfig(confirmation=ChannelConfig.Confirmation(mode="invalid"))
        with pytest.raises(ValueError, match="confirmation.mode"):
            config.validate()

    def test_validate_optimistic_requires_positive_timeout(self):
        config = ChannelConfig(confirmation=ChannelConfig.Confirmation(mode="optimistic", timeout_minutes=0))
        with pytest.raises(ValueError, match="timeout_minutes"):
            config.validate()

    def test_validate_invalid_payment_method(self):
        config = ChannelConfig(payment=ChannelConfig.Payment(method="bitcoin"))
        with pytest.raises(ValueError, match="payment.method"):
            config.validate()

    def test_deep_merge_overrides(self):
        base = {"a": 1, "b": {"c": 2, "d": 3}}
        override = {"b": {"c": 99}}
        result = deep_merge(base, override)
        assert result == {"a": 1, "b": {"c": 99, "d": 3}}

    def test_deep_merge_list_replaces(self):
        base = {"validators": ["a", "b"]}
        override = {"validators": ["c"]}
        result = deep_merge(base, override)
        assert result == {"validators": ["c"]}

    def test_deep_merge_empty_list_clears(self):
        base = {"validators": ["a", "b"]}
        override = {"validators": []}
        result = deep_merge(base, override)
        assert result == {"validators": []}


class ChannelCreationTest(TestCase):
    """Channels can be created with preset configs."""

    def test_create_channel_with_pos_preset(self):
        config = presets.pos()
        channel = Channel.objects.create(ref="test-pos", name="Test POS", config=config)
        assert channel.ref == "test-pos"
        assert channel.config["confirmation"]["mode"] == "immediate"

    def test_create_channel_with_remote_preset(self):
        config = presets.remote()
        channel = Channel.objects.create(ref="test-remote", name="Test Remote", config=config)
        assert channel.config["payment"]["method"] == "pix"

    def test_create_channel_with_listing_ref(self):
        config = presets.pos()
        channel = Channel.objects.create(
            ref="test-pos-listing", name="POS + Listing",
            config=config, listing_ref="preco-balcao",
        )
        assert channel.listing_ref == "preco-balcao"
