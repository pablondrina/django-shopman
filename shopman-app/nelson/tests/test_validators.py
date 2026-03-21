"""Tests for Nelson-specific order validators."""
from __future__ import annotations

from datetime import time
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase

from nelson.validators import BusinessHoursValidator, MinimumOrderValidator


class FakeChannel:
    def __init__(self, ref=""):
        self.ref = ref


class FakeSession:
    def __init__(self, items=None):
        self.items = items or []


class BusinessHoursValidatorTests(TestCase):
    def setUp(self) -> None:
        self.validator = BusinessHoursValidator()
        self.channel = FakeChannel(ref="balcao")
        self.session = FakeSession()

    def test_has_correct_protocol_attributes(self):
        self.assertEqual(self.validator.code, "nelson.business_hours")
        self.assertEqual(self.validator.stage, "commit")

    @patch("nelson.validators.timezone")
    def test_accepts_order_during_business_hours(self, mock_tz):
        mock_tz.localtime.return_value.time.return_value = time(10, 0)
        # Should not raise
        self.validator.validate(channel=self.channel, session=self.session, ctx={})

    @patch("nelson.validators.timezone")
    def test_rejects_order_before_opening(self, mock_tz):
        mock_tz.localtime.return_value.time.return_value = time(5, 0)
        with self.assertRaises(ValidationError):
            self.validator.validate(channel=self.channel, session=self.session, ctx={})

    @patch("nelson.validators.timezone")
    def test_rejects_order_after_closing(self, mock_tz):
        mock_tz.localtime.return_value.time.return_value = time(21, 0)
        with self.assertRaises(ValidationError):
            self.validator.validate(channel=self.channel, session=self.session, ctx={})

    @patch("nelson.validators.timezone")
    def test_accepts_at_opening_time(self, mock_tz):
        mock_tz.localtime.return_value.time.return_value = time(6, 0)
        self.validator.validate(channel=self.channel, session=self.session, ctx={})

    @patch("nelson.validators.timezone")
    def test_rejects_at_closing_time(self, mock_tz):
        mock_tz.localtime.return_value.time.return_value = time(20, 0)
        with self.assertRaises(ValidationError):
            self.validator.validate(channel=self.channel, session=self.session, ctx={})

    @patch("nelson.validators.timezone")
    def test_custom_hours(self, mock_tz):
        mock_tz.localtime.return_value.time.return_value = time(22, 0)
        validator = BusinessHoursValidator(start=time(20, 0), end=time(23, 0))
        # Should not raise (22h is within 20h-23h)
        validator.validate(channel=self.channel, session=FakeSession(), ctx={})


class MinimumOrderValidatorTests(TestCase):
    def setUp(self) -> None:
        self.validator = MinimumOrderValidator()

    def test_has_correct_protocol_attributes(self):
        self.assertEqual(self.validator.code, "nelson.minimum_order")
        self.assertEqual(self.validator.stage, "commit")

    def test_accepts_delivery_order_above_minimum(self):
        channel = FakeChannel(ref="delivery")
        session = FakeSession(items=[{"line_total_q": 1500}])
        # Should not raise (R$ 15,00 > R$ 10,00)
        self.validator.validate(channel=channel, session=session, ctx={})

    def test_rejects_delivery_order_below_minimum(self):
        channel = FakeChannel(ref="delivery")
        session = FakeSession(items=[{"line_total_q": 500}])
        with self.assertRaises(ValidationError):
            self.validator.validate(channel=channel, session=session, ctx={})

    def test_accepts_delivery_order_at_exactly_minimum(self):
        channel = FakeChannel(ref="delivery")
        session = FakeSession(items=[{"line_total_q": 1000}])
        # Should not raise (R$ 10,00 == R$ 10,00)
        self.validator.validate(channel=channel, session=session, ctx={})

    def test_no_minimum_for_balcao_channel(self):
        channel = FakeChannel(ref="balcao")
        session = FakeSession(items=[{"line_total_q": 100}])
        # Should not raise — minimum only applies to delivery
        self.validator.validate(channel=channel, session=session, ctx={})

    def test_no_minimum_when_no_channel(self):
        session = FakeSession(items=[{"line_total_q": 100}])
        # Should not raise
        self.validator.validate(channel=None, session=session, ctx={})

    def test_multiple_items_sum(self):
        channel = FakeChannel(ref="delivery")
        session = FakeSession(items=[
            {"line_total_q": 300},
            {"line_total_q": 400},
            {"line_total_q": 200},
        ])
        # Total = 900, below 1000
        with self.assertRaises(ValidationError):
            self.validator.validate(channel=channel, session=session, ctx={})

    def test_custom_minimum(self):
        validator = MinimumOrderValidator(minimum_q=2000)
        channel = FakeChannel(ref="delivery")
        session = FakeSession(items=[{"line_total_q": 1500}])
        with self.assertRaises(ValidationError):
            validator.validate(channel=channel, session=session, ctx={})

    def test_delivery_substring_match(self):
        """Validates for channels like 'delivery-proprio', 'delivery-web'."""
        channel = FakeChannel(ref="delivery-proprio")
        session = FakeSession(items=[{"line_total_q": 500}])
        with self.assertRaises(ValidationError):
            self.validator.validate(channel=channel, session=session, ctx={})
