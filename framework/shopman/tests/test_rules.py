"""
Tests for shopman.rules — engine, pricing rules, validation rules, and admin.
"""

from __future__ import annotations

from datetime import time
from unittest.mock import MagicMock, patch

import pytest
from django.core.cache import cache
from django.core.exceptions import ValidationError

from shopman.models import RuleConfig
from shopman.rules.engine import (
    CACHE_KEY,
    get_active_rules,
    invalidate_rules_cache,
    load_rule,
    register_active_rules,
)
from shopman.rules.pricing import D1Rule, EmployeeRule, HappyHourRule, PromotionRule
from shopman.rules.validation import BusinessHoursRule, MinimumOrderRule

# ── Pricing rules: class attributes ──────────────────────────────────


class TestD1Rule:
    def test_code_and_label(self):
        rule = D1Rule()
        assert rule.code == "shop.d1_discount"
        assert rule.label == "Desconto D-1 (sobras)"
        assert rule.rule_type == "modifier"

    def test_default_params(self):
        assert D1Rule.default_params == {"discount_percent": 50}

    def test_custom_params(self):
        rule = D1Rule(discount_percent=30)
        assert rule.discount_percent == 30


class TestPromotionRule:
    def test_code_and_label(self):
        rule = PromotionRule()
        assert rule.code == "shop.discount"
        assert rule.label == "Promoções e Cupons"
        assert rule.rule_type == "modifier"

    def test_default_params(self):
        assert PromotionRule.default_params == {}


class TestEmployeeRule:
    def test_code_and_label(self):
        rule = EmployeeRule()
        assert rule.code == "shop.employee_discount"
        assert rule.rule_type == "modifier"

    def test_default_params(self):
        assert EmployeeRule.default_params == {"discount_percent": 20, "group": "staff"}

    def test_custom_params(self):
        rule = EmployeeRule(discount_percent=15, group="team")
        assert rule.discount_percent == 15
        assert rule.group == "team"


class TestHappyHourRule:
    def test_code_and_label(self):
        rule = HappyHourRule()
        assert rule.code == "shop.happy_hour"
        assert rule.rule_type == "modifier"

    def test_default_params(self):
        assert HappyHourRule.default_params == {
            "discount_percent": 10,
            "start": "16:00",
            "end": "18:00",
        }

    def test_custom_params(self):
        rule = HappyHourRule(discount_percent=15, start="14:00", end="17:00")
        assert rule.discount_percent == 15
        assert rule.start == time(14, 0)
        assert rule.end == time(17, 0)


# ── Validation rules ─────────────────────────────────────────────────


class TestBusinessHoursRule:
    def test_code_and_label(self):
        rule = BusinessHoursRule()
        assert rule.code == "shop.business_hours"
        assert rule.rule_type == "validator"
        assert rule.stage == "commit"

    def test_default_params(self):
        assert BusinessHoursRule.default_params == {"start": "08:00", "end": "18:00"}

    def test_custom_params(self):
        rule = BusinessHoursRule(start="08:00", end="22:00")
        assert rule.start == time(8, 0)
        assert rule.end == time(22, 0)

    @patch("shopman.rules.validation.timezone")
    def test_flags_outside_when_shop_has_hours(self, mock_tz):
        mock_now = MagicMock()
        mock_now.time.return_value = time(23, 0)
        mock_now.strftime.return_value = "monday"
        mock_tz.localtime.return_value = mock_now

        rule = BusinessHoursRule()
        session = MagicMock()
        session.data = {}

        hours = {"monday": {"open": "06:00", "close": "20:00"}}
        with patch.object(rule, "_get_opening_hours", return_value=hours):
            rule.validate(channel=None, session=session, ctx={})
            assert session.data["outside_business_hours"] is True

    @patch("shopman.rules.validation.timezone")
    def test_no_shop_hours_never_flags_outside(self, mock_tz):
        mock_now = MagicMock()
        mock_now.time.return_value = time(23, 0)
        mock_now.strftime.return_value = "monday"
        mock_tz.localtime.return_value = mock_now

        rule = BusinessHoursRule()
        session = MagicMock()
        session.data = {}

        with patch.object(rule, "_get_opening_hours", return_value=None):
            rule.validate(channel=None, session=session, ctx={})
            assert "outside_business_hours" not in session.data

    @patch("shopman.rules.validation.timezone")
    def test_within_shop_hours_no_flag(self, mock_tz):
        mock_now = MagicMock()
        mock_now.time.return_value = time(10, 0)
        mock_now.strftime.return_value = "monday"
        mock_tz.localtime.return_value = mock_now

        rule = BusinessHoursRule()
        session = MagicMock()
        session.data = {}

        hours = {"monday": {"open": "06:00", "close": "20:00"}}
        with patch.object(rule, "_get_opening_hours", return_value=hours):
            rule.validate(channel=None, session=session, ctx={})
            assert "outside_business_hours" not in session.data

    @patch("shopman.rules.validation.timezone")
    def test_accepts_within_hours_legacy_no_shop_hours(self, mock_tz):
        mock_now = MagicMock()
        mock_now.time.return_value = time(10, 0)
        mock_now.strftime.return_value = "Monday"
        mock_tz.localtime.return_value = mock_now

        rule = BusinessHoursRule()
        session = MagicMock()

        with patch.object(rule, "_get_opening_hours", return_value=None):
            rule.validate(channel=None, session=session, ctx={})


class TestMinimumOrderRule:
    def test_code_and_label(self):
        rule = MinimumOrderRule()
        assert rule.code == "shop.minimum_order"
        assert rule.rule_type == "validator"
        assert rule.stage == "commit"

    def test_default_params(self):
        assert MinimumOrderRule.default_params == {"minimum_q": 1000}

    def test_rejects_below_minimum_delivery(self):
        rule = MinimumOrderRule(minimum_q=2000)
        session = MagicMock()
        session.data = {"fulfillment_type": "delivery"}
        session.items = [{"line_total_q": 500}]

        with pytest.raises(ValidationError, match="Pedido minimo para delivery"):
            rule.validate(channel=None, session=session, ctx={})

    def test_accepts_above_minimum_delivery(self):
        rule = MinimumOrderRule(minimum_q=1000)
        session = MagicMock()
        session.data = {"fulfillment_type": "delivery"}
        session.items = [{"line_total_q": 1500}]

        rule.validate(channel=None, session=session, ctx={})

    def test_skips_non_delivery(self):
        rule = MinimumOrderRule(minimum_q=5000)
        session = MagicMock()
        session.data = {"fulfillment_type": "pickup"}
        session.items = [{"line_total_q": 100}]

        rule.validate(channel=None, session=session, ctx={})

    def test_custom_minimum(self):
        rule = MinimumOrderRule(minimum_q=5000)
        assert rule.minimum_q == 5000


# ── Engine tests (require DB) ────────────────────────────────────────


@pytest.mark.django_db
class TestEngine:
    def setup_method(self):
        cache.delete(CACHE_KEY)

    def _create_rule(self, **overrides):
        defaults = {
            "code": "test_rule",
            "rule_path": "shopman.rules.validation.BusinessHoursRule",
            "label": "Test Rule",
            "enabled": True,
            "params": {},
            "priority": 10,
        }
        defaults.update(overrides)
        return RuleConfig.objects.create(**defaults)

    def test_get_active_rules_returns_enabled(self):
        self._create_rule(code="active_1", enabled=True)
        self._create_rule(code="inactive_1", enabled=False)

        rules = get_active_rules()
        codes = [r.code for r in rules]

        assert "active_1" in codes
        assert "inactive_1" not in codes

    def test_get_active_rules_filters_by_channel(self):
        from shopman.omniman.models import Channel

        ch = Channel.objects.create(ref="test-ch", name="Test Channel")

        self._create_rule(code="global_rule")
        rule_channel = self._create_rule(code="channel_rule")
        rule_channel.channels.add(ch)

        rules = get_active_rules(channel=ch)
        codes = [r.code for r in rules]

        assert "global_rule" in codes
        assert "channel_rule" in codes

    def test_get_active_rules_excludes_other_channel(self):
        from shopman.omniman.models import Channel

        ch1 = Channel.objects.create(ref="ch-1", name="Channel 1")
        ch2 = Channel.objects.create(ref="ch-2", name="Channel 2")

        rule = self._create_rule(code="ch1_only")
        rule.channels.add(ch1)

        rules = get_active_rules(channel=ch2)
        codes = [r.code for r in rules]

        assert "ch1_only" not in codes

    def test_load_rule_imports_and_instantiates(self):
        rc = self._create_rule(
            code="bh_test",
            rule_path="shopman.rules.validation.BusinessHoursRule",
            params={"start": "08:00", "end": "22:00"},
        )
        rule = load_rule(rc)

        assert isinstance(rule, BusinessHoursRule)
        assert rule.start == time(8, 0)
        assert rule.end == time(22, 0)

    def test_load_rule_bad_path_raises(self):
        rc = self._create_rule(
            code="bad_path",
            rule_path="shopman.rules.nonexistent.FakeRule",
        )
        with pytest.raises(ImportError):
            load_rule(rc)

    def test_cache_invalidated_on_save(self):
        self._create_rule(code="cache_test")
        get_active_rules()
        assert cache.get(CACHE_KEY) is not None

        invalidate_rules_cache(sender=RuleConfig)
        assert cache.get(CACHE_KEY) is None

    def test_register_active_rules_registers_validators(self):
        from shopman.omniman import registry

        self._create_rule(
            code="bh_register",
            rule_path="shopman.rules.validation.BusinessHoursRule",
            params={"start": "07:00", "end": "21:00"},
        )
        self._create_rule(
            code="mo_register",
            rule_path="shopman.rules.validation.MinimumOrderRule",
            params={"minimum_q": 2000},
        )

        register_active_rules()

        validator_codes = [v.code for v in registry.get_validators()]
        assert "shop.business_hours" in validator_codes
        assert "shop.minimum_order" in validator_codes

    def test_register_active_rules_skips_modifiers(self):
        from shopman.omniman import registry

        self._create_rule(
            code="pricing_skip",
            rule_path="shopman.rules.pricing.D1Rule",
            params={"discount_percent": 50},
        )

        initial_count = len(registry.get_modifiers())
        register_active_rules()
        new_count = len(registry.get_modifiers())

        assert new_count == initial_count

    def test_register_active_rules_skips_disabled(self):
        from shopman.omniman import registry

        self._create_rule(
            code="disabled_val",
            rule_path="shopman.rules.validation.BusinessHoursRule",
            enabled=False,
        )

        validator_codes_before = [v.code for v in registry.get_validators()]
        register_active_rules()
        validator_codes_after = [v.code for v in registry.get_validators()]

        new_codes = set(validator_codes_after) - set(validator_codes_before)
        assert "shop.business_hours" not in new_codes


# ── Admin registration test ──────────────────────────────────────────


@pytest.mark.django_db
class TestRuleConfigAdmin:
    def test_ruleconfig_registered_in_admin(self):
        from django.contrib import admin

        assert RuleConfig in admin.site._registry

    def test_promotion_registered_in_admin(self):
        from django.contrib import admin

        from shopman.models import Promotion

        assert Promotion in admin.site._registry

    def test_coupon_registered_in_admin(self):
        from django.contrib import admin

        from shopman.models import Coupon

        assert Coupon in admin.site._registry
