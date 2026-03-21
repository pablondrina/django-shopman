"""Integration tests for shopman orchestration layer.

Tests cover:
- Channel presets create valid Channels in the ordering kernel
- Channel config validation rejects invalid configs
- Preset→Channel config mapping is correct
- Registry is accessible from the orchestrator
- setup_channels provisions default channels
"""

import pytest
from django.test import TestCase

from shopman import presets
from shopman.channels import ensure_channel
from shopman.config import ChannelConfigError, validate_channel_config
from shopman.orchestration import DEFAULT_CHANNELS, PRESETS, setup_channels
from shopman.ordering.models import Channel
from shopman.ordering import registry


class PresetValidationTest(TestCase):
    """Presets return valid, complete configs."""

    def test_pos_preset_returns_valid_config(self):
        config = presets.pos()
        assert config["channel_type"] == "pos"
        assert config["auto_confirm"] is True
        assert config["payment_mode"] == "counter"
        assert config["stock_hold_ttl"] == 300

    def test_remote_preset_returns_valid_config(self):
        config = presets.remote()
        assert config["channel_type"] == "remote"
        assert config["auto_confirm"] is True
        assert config["payment_mode"] == "pix"
        assert config["stock_hold_ttl"] is None
        assert config["confirmation_timeout"] == 600

    def test_marketplace_preset_returns_valid_config(self):
        config = presets.marketplace()
        assert config["channel_type"] == "marketplace"
        assert config["auto_confirm"] is True
        assert config["payment_mode"] == "external"
        assert config["stock_hold_ttl"] is None

    def test_pos_preset_post_commit_directives(self):
        config = presets.pos()
        assert config["post_commit_directives"] == ["stock.hold", "notification.send"]
        assert config["notification_template"] == "order_confirmed_pos"

    def test_remote_preset_post_commit_directives(self):
        config = presets.remote()
        assert config["post_commit_directives"] == ["stock.hold", "notification.send"]
        assert config["notification_template"] == "order_confirmed_remote"

    def test_marketplace_preset_post_commit_directives(self):
        config = presets.marketplace()
        assert config["post_commit_directives"] == ["notification.send"]
        assert config["notification_template"] == "order_confirmed_marketplace"

    def test_pos_preset_allows_overrides(self):
        config = presets.pos(stock_hold_ttl=60)
        assert config["stock_hold_ttl"] == 60

    def test_remote_preset_allows_overrides(self):
        config = presets.remote(confirmation_timeout=120)
        assert config["confirmation_timeout"] == 120

    def test_marketplace_preset_allows_overrides(self):
        config = presets.marketplace(stock_hold_ttl=30)
        assert config["stock_hold_ttl"] == 30


class ConfigValidationTest(TestCase):
    """validate_channel_config rejects bad input."""

    def test_missing_keys_raises(self):
        with pytest.raises(ChannelConfigError, match="Missing required keys"):
            validate_channel_config({"channel_type": "pos"})

    def test_invalid_channel_type_raises(self):
        with pytest.raises(ChannelConfigError, match="Invalid channel_type"):
            validate_channel_config({
                "channel_type": "invalid",
                "auto_confirm": True,
                "payment_mode": "counter",
                "stock_hold_ttl": 300,
            })

    def test_invalid_payment_mode_raises(self):
        with pytest.raises(ChannelConfigError, match="Invalid payment_mode"):
            validate_channel_config({
                "channel_type": "pos",
                "auto_confirm": True,
                "payment_mode": "bitcoin",
                "stock_hold_ttl": 300,
            })

    def test_non_bool_auto_confirm_raises(self):
        with pytest.raises(ChannelConfigError, match="auto_confirm must be a boolean"):
            validate_channel_config({
                "channel_type": "pos",
                "auto_confirm": "yes",
                "payment_mode": "counter",
                "stock_hold_ttl": 300,
            })

    def test_negative_ttl_raises(self):
        with pytest.raises(ChannelConfigError, match="stock_hold_ttl"):
            validate_channel_config({
                "channel_type": "pos",
                "auto_confirm": True,
                "payment_mode": "counter",
                "stock_hold_ttl": -1,
            })

    def test_valid_config_passes(self):
        config = validate_channel_config({
            "channel_type": "pos",
            "auto_confirm": True,
            "payment_mode": "counter",
            "stock_hold_ttl": 300,
        })
        assert config["channel_type"] == "pos"


class EnsureChannelTest(TestCase):
    """ensure_channel creates/updates Channel in DB."""

    def test_creates_channel_from_pos_preset(self):
        preset_config = presets.pos()
        channel, created = ensure_channel(
            ref="test-pos",
            name="Test POS",
            preset_config=preset_config,
        )
        assert created is True
        assert channel.ref == "test-pos"
        assert channel.name == "Test POS"
        assert channel.config["preset"] == "pos"
        assert channel.config["payment"]["mode"] == "counter"
        assert channel.config["confirmation_flow"]["auto_confirm"] is True
        assert channel.config["stock"]["hold_ttl"] == 300
        assert channel.config["post_commit_directives"] == ["stock.hold", "notification.send"]
        assert channel.config["notification_template"] == "order_confirmed_pos"

    def test_creates_channel_from_remote_preset(self):
        preset_config = presets.remote()
        channel, created = ensure_channel(
            ref="test-remote",
            name="Test Remote",
            preset_config=preset_config,
        )
        assert created is True
        assert channel.config["preset"] == "remote"
        assert channel.config["payment"]["mode"] == "pix"
        assert channel.config["confirmation_flow"]["timeout"] == 600
        assert channel.config["post_commit_directives"] == ["stock.hold", "notification.send"]
        assert channel.config["notification_template"] == "order_confirmed_remote"

    def test_creates_channel_from_marketplace_preset(self):
        preset_config = presets.marketplace()
        channel, created = ensure_channel(
            ref="test-marketplace",
            name="Test Marketplace",
            preset_config=preset_config,
        )
        assert created is True
        assert channel.config["preset"] == "marketplace"
        assert channel.config["payment"]["mode"] == "external"
        assert channel.config["stock"]["hold_ttl"] is None
        assert channel.config["post_commit_directives"] == ["notification.send"]
        assert channel.config["notification_template"] == "order_confirmed_marketplace"

    def test_updates_existing_channel(self):
        preset_config = presets.pos()
        ensure_channel(ref="pos-update", name="V1", preset_config=preset_config)

        preset_config_v2 = presets.pos(stock_hold_ttl=60)
        channel, created = ensure_channel(
            ref="pos-update",
            name="V2",
            preset_config=preset_config_v2,
        )
        assert created is False
        assert channel.name == "V2"
        assert channel.config["stock"]["hold_ttl"] == 60

    def test_channel_defaults_applied(self):
        preset_config = presets.marketplace()
        channel, _ = ensure_channel(
            ref="test-mp-defaults",
            name="MP",
            preset_config=preset_config,
            channel_defaults={
                "pricing_policy": "external",
                "edit_policy": "locked",
                "display_order": 30,
            },
        )
        assert channel.pricing_policy == "external"
        assert channel.edit_policy == "locked"
        assert channel.display_order == 30

    def test_config_extras_merged(self):
        preset_config = presets.pos()
        channel, _ = ensure_channel(
            ref="test-pos-extras",
            name="POS Extras",
            preset_config=preset_config,
            channel_defaults={
                "config": {"icon": "point_of_sale", "terminology": {"order": "Comanda"}},
            },
        )
        assert channel.config["icon"] == "point_of_sale"
        assert channel.config["terminology"]["order"] == "Comanda"
        assert channel.config["preset"] == "pos"


class SetupChannelsTest(TestCase):
    """setup_channels provisions all default channels."""

    def test_setup_creates_three_default_channels(self):
        results = setup_channels()
        assert len(results) == 3
        assert all(created for _, created in results)

        refs = {ch.ref for ch, _ in results}
        assert refs == {"pos", "remote", "marketplace"}

    def test_setup_channels_are_in_db(self):
        setup_channels()
        assert Channel.objects.count() == 3
        assert Channel.objects.filter(ref="pos").exists()
        assert Channel.objects.filter(ref="remote").exists()
        assert Channel.objects.filter(ref="marketplace").exists()

    def test_pos_channel_config(self):
        setup_channels()
        ch = Channel.objects.get(ref="pos")
        assert ch.name == "Balcão / PDV"
        assert ch.config["preset"] == "pos"
        assert ch.config["icon"] == "point_of_sale"
        assert ch.config["payment"]["mode"] == "counter"
        assert ch.pricing_policy == "internal"
        assert ch.edit_policy == "open"

    def test_remote_channel_config(self):
        setup_channels()
        ch = Channel.objects.get(ref="remote")
        assert ch.name == "Remoto / WhatsApp"
        assert ch.config["preset"] == "remote"
        assert ch.config["payment"]["mode"] == "pix"
        assert ch.config["confirmation_flow"]["auto_confirm"] is True

    def test_marketplace_channel_config(self):
        setup_channels()
        ch = Channel.objects.get(ref="marketplace")
        assert ch.name == "Marketplace"
        assert ch.config["preset"] == "marketplace"
        assert ch.config["payment"]["mode"] == "external"
        assert ch.pricing_policy == "external"
        assert ch.edit_policy == "locked"

    def test_setup_idempotent(self):
        setup_channels()
        setup_channels()
        assert Channel.objects.count() == 3

    def test_custom_channel_defs(self):
        custom = [{
            "ref": "custom-pos",
            "name": "My POS",
            "preset": "pos",
            "config_extras": {},
            "channel_defaults": {},
        }]
        results = setup_channels(channel_defs=custom)
        assert len(results) == 1
        assert results[0][0].ref == "custom-pos"


class PresetRegistryTest(TestCase):
    """PRESETS dict maps names to callable preset functions."""

    def test_all_presets_registered(self):
        assert set(PRESETS.keys()) == {"pos", "remote", "marketplace"}

    def test_each_preset_callable(self):
        for name, fn in PRESETS.items():
            config = fn()
            assert config["channel_type"] == name


class OrderingRegistryTest(TestCase):
    """Ordering registry is accessible and functional from orchestrator."""

    def setUp(self):
        registry.clear()

    def tearDown(self):
        registry.clear()

    def test_registry_accepts_validator(self):
        class TestValidator:
            code = "test"
            stage = "draft"

            def validate(self, *, channel, session, ctx):
                pass

        registry.register_validator(TestValidator())
        assert len(registry.get_validators(stage="draft")) == 1

    def test_registry_accepts_modifier(self):
        class TestModifier:
            code = "test"
            order = 10

            def apply(self, *, channel, session, ctx):
                pass

        registry.register_modifier(TestModifier())
        assert len(registry.get_modifiers()) == 1

    def test_registry_accepts_directive_handler(self):
        class TestHandler:
            topic = "test.topic"

            def handle(self, *, message, ctx):
                pass

        registry.register_directive_handler(TestHandler())
        assert registry.get_directive_handler("test.topic") is not None

    def test_registry_accepts_issue_resolver(self):
        class TestResolver:
            source = "test"

            def resolve(self, *, session, issue, action_id, ctx):
                pass

        registry.register_issue_resolver(TestResolver())
        assert registry.get_issue_resolver("test") is not None
