"""Tests for Nelson-specific order modifiers."""
from __future__ import annotations

from datetime import time
from unittest.mock import patch

from django.test import TestCase

from nelson.modifiers import EmployeeDiscountModifier, HappyHourModifier


class FakeChannel:
    def __init__(self, code="balcao"):
        self.code = code


class FakeSession:
    def __init__(self, data=None, items=None):
        self.data = data or {}
        self.items = items or []


class EmployeeDiscountModifierTests(TestCase):
    def setUp(self) -> None:
        self.modifier = EmployeeDiscountModifier()
        self.channel = FakeChannel()

    def test_has_correct_protocol_attributes(self):
        self.assertEqual(self.modifier.code, "nelson.employee_discount")
        self.assertIsInstance(self.modifier.order, int)

    def test_applies_20_percent_discount_for_staff(self):
        session = FakeSession(
            data={"customer": {"group": "staff"}},
            items=[{"sku": "PAO-FRANCES", "unit_price_q": 1000, "qty": 2, "line_total_q": 2000}],
        )
        self.modifier.apply(channel=self.channel, session=session, ctx={})
        self.assertEqual(session.items[0]["unit_price_q"], 800)
        self.assertEqual(session.items[0]["line_total_q"], 1600)
        self.assertEqual(session.items[0]["modifiers_applied"][0]["type"], "employee_discount")

    def test_no_discount_for_regular_customer(self):
        session = FakeSession(
            data={"customer": {"group": "varejo"}},
            items=[{"sku": "PAO-FRANCES", "unit_price_q": 1000, "qty": 1, "line_total_q": 1000}],
        )
        self.modifier.apply(channel=self.channel, session=session, ctx={})
        self.assertEqual(session.items[0]["unit_price_q"], 1000)

    def test_no_discount_when_no_customer_data(self):
        session = FakeSession(
            data={},
            items=[{"sku": "PAO-FRANCES", "unit_price_q": 1000, "qty": 1, "line_total_q": 1000}],
        )
        self.modifier.apply(channel=self.channel, session=session, ctx={})
        self.assertEqual(session.items[0]["unit_price_q"], 1000)

    def test_discount_rounds_correctly(self):
        session = FakeSession(
            data={"customer": {"group": "staff"}},
            items=[{"sku": "CROISSANT", "unit_price_q": 690, "qty": 1, "line_total_q": 690}],
        )
        self.modifier.apply(channel=self.channel, session=session, ctx={})
        # 690 * 20% = 138, so 690 - 138 = 552
        self.assertEqual(session.items[0]["unit_price_q"], 552)

    def test_multiple_items(self):
        session = FakeSession(
            data={"customer": {"group": "staff"}},
            items=[
                {"sku": "PAO-FRANCES", "unit_price_q": 1000, "qty": 1, "line_total_q": 1000},
                {"sku": "CROISSANT", "unit_price_q": 500, "qty": 3, "line_total_q": 1500},
            ],
        )
        self.modifier.apply(channel=self.channel, session=session, ctx={})
        self.assertEqual(session.items[0]["unit_price_q"], 800)
        self.assertEqual(session.items[1]["unit_price_q"], 400)
        self.assertEqual(session.items[1]["line_total_q"], 1200)


class HappyHourModifierTests(TestCase):
    def setUp(self) -> None:
        self.modifier = HappyHourModifier()
        self.channel = FakeChannel()

    def test_has_correct_protocol_attributes(self):
        self.assertEqual(self.modifier.code, "nelson.happy_hour")
        self.assertIsInstance(self.modifier.order, int)

    def _make_session(self, items=None):
        return FakeSession(items=items or [
            {"sku": "PAO-FRANCES", "unit_price_q": 1000, "qty": 1, "line_total_q": 1000},
        ])

    @patch("nelson.modifiers.timezone")
    def test_applies_discount_during_happy_hour(self, mock_tz):
        mock_tz.localtime.return_value.time.return_value = time(17, 0)
        session = self._make_session()
        self.modifier.apply(channel=self.channel, session=session, ctx={})
        self.assertEqual(session.items[0]["unit_price_q"], 900)
        self.assertEqual(session.items[0]["line_total_q"], 900)
        self.assertEqual(session.items[0]["modifiers_applied"][0]["type"], "happy_hour")

    @patch("nelson.modifiers.timezone")
    def test_no_discount_outside_happy_hour(self, mock_tz):
        mock_tz.localtime.return_value.time.return_value = time(10, 0)
        session = self._make_session()
        self.modifier.apply(channel=self.channel, session=session, ctx={})
        self.assertEqual(session.items[0]["unit_price_q"], 1000)

    @patch("nelson.modifiers.timezone")
    def test_no_discount_at_boundary_end(self, mock_tz):
        mock_tz.localtime.return_value.time.return_value = time(18, 0)
        session = self._make_session()
        self.modifier.apply(channel=self.channel, session=session, ctx={})
        self.assertEqual(session.items[0]["unit_price_q"], 1000)

    @patch("nelson.modifiers.timezone")
    def test_discount_at_boundary_start(self, mock_tz):
        mock_tz.localtime.return_value.time.return_value = time(16, 0)
        session = self._make_session()
        self.modifier.apply(channel=self.channel, session=session, ctx={})
        self.assertEqual(session.items[0]["unit_price_q"], 900)

    @patch("nelson.modifiers.timezone")
    def test_does_not_stack_with_employee_discount(self, mock_tz):
        mock_tz.localtime.return_value.time.return_value = time(17, 0)
        session = self._make_session(items=[
            {
                "sku": "PAO-FRANCES",
                "unit_price_q": 800,
                "qty": 1,
                "line_total_q": 800,
                "modifiers_applied": [{"type": "employee_discount", "discount_percent": 20}],
            },
        ])
        self.modifier.apply(channel=self.channel, session=session, ctx={})
        # Should NOT apply happy hour since employee discount already applied
        self.assertEqual(session.items[0]["unit_price_q"], 800)

    @patch("nelson.modifiers.timezone")
    def test_custom_times_and_percent(self, mock_tz):
        mock_tz.localtime.return_value.time.return_value = time(14, 0)
        modifier = HappyHourModifier(
            discount_percent=15,
            start=time(13, 0),
            end=time(15, 0),
        )
        session = self._make_session()
        modifier.apply(channel=self.channel, session=session, ctx={})
        self.assertEqual(session.items[0]["unit_price_q"], 850)
