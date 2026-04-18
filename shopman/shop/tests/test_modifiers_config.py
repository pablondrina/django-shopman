"""Tests: modifier RuleConfig integration (WP-GAP-10 Fase 2).

Verifies that D1, HappyHour, and Employee modifiers read params from
RuleConfig when available, with correct fallback to channel.config and
constructor defaults. RuleConfig DB is mocked via get_rule_params.
"""
from __future__ import annotations

from datetime import time
from unittest.mock import MagicMock, patch

import pytest


# ─── helpers ────────────────────────────────────────────────────────────────


def _make_session(items=None, data=None, pricing=None):
    session = MagicMock()
    session.items = items if items is not None else [
        {"sku": "P001", "unit_price_q": 1000, "qty": 1}
    ]
    session.data = data if data is not None else {}
    session.pricing = pricing if pricing is not None else {}
    session.update_items = lambda x: None
    session.save = MagicMock()
    return session


def _make_channel(rules=None):
    ch = MagicMock()
    ch.config = {"rules": rules or {}}
    return ch


# ─── D1DiscountModifier ─────────────────────────────────────────────────────


class TestD1ModifierRuleConfig:
    @pytest.fixture
    def modifier(self):
        from instances.nelson.modifiers import D1DiscountModifier
        return D1DiscountModifier()

    def _d1_item(self, price_q=1000):
        return {"sku": "P001", "unit_price_q": price_q, "qty": 1, "is_d1": True}

    def test_reads_percent_from_ruleconfig(self, modifier):
        session = _make_session(items=[self._d1_item()])
        channel = _make_channel()
        with patch("shopman.shop.rules.engine.get_rule_params", return_value={"discount_percent": 30}):
            modifier.apply(channel=channel, session=session, ctx={})
        assert session.items[0]["unit_price_q"] == 700  # 1000 - 30%

    def test_channel_config_overrides_ruleconfig(self, modifier):
        session = _make_session(items=[self._d1_item()])
        channel = _make_channel(rules={"d1_discount_percent": 40})
        with patch("shopman.shop.rules.engine.get_rule_params", return_value={"discount_percent": 30}):
            modifier.apply(channel=channel, session=session, ctx={})
        assert session.items[0]["unit_price_q"] == 600  # 1000 - 40%

    def test_falls_back_to_default_when_no_ruleconfig(self, modifier):
        session = _make_session(items=[self._d1_item()])
        channel = _make_channel()
        with patch("shopman.shop.rules.engine.get_rule_params", return_value={}):
            modifier.apply(channel=channel, session=session, ctx={})
        assert session.items[0]["unit_price_q"] == 500  # 1000 - 50% (module default)

    def test_non_d1_item_unaffected(self, modifier):
        session = _make_session(items=[{"sku": "P001", "unit_price_q": 1000, "qty": 1}])
        channel = _make_channel()
        with patch("shopman.shop.rules.engine.get_rule_params", return_value={"discount_percent": 30}):
            modifier.apply(channel=channel, session=session, ctx={})
        assert session.items[0]["unit_price_q"] == 1000  # not d1, not touched

    def test_modifier_records_type_in_applied(self, modifier):
        session = _make_session(items=[self._d1_item()])
        channel = _make_channel()
        with patch("shopman.shop.rules.engine.get_rule_params", return_value={"discount_percent": 50}):
            modifier.apply(channel=channel, session=session, ctx={})
        types = [m["type"] for m in session.items[0].get("modifiers_applied", [])]
        assert "d1_discount" in types


# ─── HappyHourModifier ──────────────────────────────────────────────────────


class TestHappyHourModifierRuleConfig:
    @pytest.fixture
    def modifier(self):
        from instances.nelson.modifiers import HappyHourModifier
        # Constructor: 10% discount, open all day (for override testing)
        return HappyHourModifier(
            discount_percent=10,
            start=time(0, 0),
            end=time(23, 59),
        )

    def _at(self, h, m=0):
        mock = MagicMock()
        mock.return_value.time.return_value = time(h, m)
        return mock

    def test_reads_percent_from_ruleconfig(self, modifier):
        session = _make_session()
        channel = _make_channel()
        rc = {"discount_percent": 20, "start": "00:00", "end": "23:59"}
        with patch("shopman.shop.rules.engine.get_rule_params", return_value=rc):
            with patch("django.utils.timezone.localtime", self._at(12)):
                modifier.apply(channel=channel, session=session, ctx={})
        assert session.items[0]["unit_price_q"] == 800  # 1000 - 20%

    def test_reads_time_window_from_ruleconfig(self, modifier):
        session = _make_session()
        channel = _make_channel()
        # RuleConfig says 14:00-15:00; check at 13:00 → outside window → no discount
        rc = {"discount_percent": 15, "start": "14:00", "end": "15:00"}
        with patch("shopman.shop.rules.engine.get_rule_params", return_value=rc):
            with patch("django.utils.timezone.localtime", self._at(13)):
                modifier.apply(channel=channel, session=session, ctx={})
        assert session.items[0]["unit_price_q"] == 1000  # outside window, no discount

    def test_ruleconfig_window_inside_applies(self, modifier):
        session = _make_session()
        channel = _make_channel()
        rc = {"discount_percent": 15, "start": "14:00", "end": "15:00"}
        with patch("shopman.shop.rules.engine.get_rule_params", return_value=rc):
            with patch("django.utils.timezone.localtime", self._at(14, 30)):
                modifier.apply(channel=channel, session=session, ctx={})
        assert session.items[0]["unit_price_q"] == 850  # 1000 - 15%

    def test_falls_back_to_constructor_when_no_ruleconfig(self, modifier):
        session = _make_session()
        channel = _make_channel()
        with patch("shopman.shop.rules.engine.get_rule_params", return_value={}):
            with patch("django.utils.timezone.localtime", self._at(12)):
                modifier.apply(channel=channel, session=session, ctx={})
        assert session.items[0]["unit_price_q"] == 900  # 1000 - 10% (constructor)

    def test_skips_employee_discount_items(self, modifier):
        session = _make_session(items=[{
            "sku": "P001", "unit_price_q": 1000, "qty": 1,
            "modifiers_applied": [{"type": "employee_discount"}],
        }])
        channel = _make_channel()
        rc = {"discount_percent": 20, "start": "00:00", "end": "23:59"}
        with patch("shopman.shop.rules.engine.get_rule_params", return_value=rc):
            with patch("django.utils.timezone.localtime", self._at(12)):
                modifier.apply(channel=channel, session=session, ctx={})
        assert session.items[0]["unit_price_q"] == 1000  # not touched

    def test_web_channel_skipped(self, modifier):
        session = _make_session(data={"origin_channel": "web"})
        channel = _make_channel()
        rc = {"discount_percent": 20, "start": "00:00", "end": "23:59"}
        with patch("shopman.shop.rules.engine.get_rule_params", return_value=rc):
            with patch("django.utils.timezone.localtime", self._at(12)):
                modifier.apply(channel=channel, session=session, ctx={})
        assert session.items[0]["unit_price_q"] == 1000  # web origin skipped


# ─── EmployeeDiscountModifier ───────────────────────────────────────────────


class TestEmployeeModifierRuleConfig:
    @pytest.fixture
    def modifier(self):
        from shopman.shop.modifiers import EmployeeDiscountModifier
        return EmployeeDiscountModifier()

    def _staff_session(self):
        return _make_session(data={"customer": {"group": "staff"}})

    def test_reads_percent_from_ruleconfig(self, modifier):
        session = self._staff_session()
        channel = _make_channel()
        with patch("shopman.shop.rules.engine.get_rule_params", return_value={"discount_percent": 30}):
            modifier.apply(channel=channel, session=session, ctx={})
        assert session.items[0]["unit_price_q"] == 700  # 1000 - 30%

    def test_channel_config_overrides_ruleconfig(self, modifier):
        session = self._staff_session()
        channel = _make_channel(rules={"employee_discount_percent": 40})
        with patch("shopman.shop.rules.engine.get_rule_params", return_value={"discount_percent": 30}):
            modifier.apply(channel=channel, session=session, ctx={})
        assert session.items[0]["unit_price_q"] == 600  # 1000 - 40%

    def test_falls_back_to_default_when_no_ruleconfig(self, modifier):
        session = self._staff_session()
        channel = _make_channel()
        with patch("shopman.shop.rules.engine.get_rule_params", return_value={}):
            modifier.apply(channel=channel, session=session, ctx={})
        assert session.items[0]["unit_price_q"] == 800  # 1000 - 20% (default)

    def test_non_staff_not_affected(self, modifier):
        session = _make_session(data={"customer": {"group": "regular"}})
        channel = _make_channel()
        with patch("shopman.shop.rules.engine.get_rule_params", return_value={"discount_percent": 30}):
            modifier.apply(channel=channel, session=session, ctx={})
        assert session.items[0]["unit_price_q"] == 1000  # not staff, not touched

    def test_modifier_records_type_in_applied(self, modifier):
        session = self._staff_session()
        channel = _make_channel()
        with patch("shopman.shop.rules.engine.get_rule_params", return_value={"discount_percent": 20}):
            modifier.apply(channel=channel, session=session, ctx={})
        types = [m["type"] for m in session.items[0].get("modifiers_applied", [])]
        assert "employee_discount" in types
