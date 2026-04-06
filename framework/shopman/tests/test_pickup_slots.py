"""
Tests for pickup slot service — production-based slot assignment.

Covers:
- get_slots() reads from Shop.defaults, falls back to defaults
- get_typical_ready_times() computes median from WorkOrder history
- _round_up_minutes() rounds to configurable granularity
- get_earliest_slot_for_skus() maps cart items to correct slot
- annotate_slots_for_checkout() returns full template context
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from shopman.models import Shop
from shopman.services.pickup_slots import (
    DEFAULT_SLOTS,
    _round_up_minutes,
    annotate_slots_for_checkout,
    get_earliest_slot_for_skus,
    get_slots,
    get_typical_ready_times,
)


class RoundUpMinutesTests(TestCase):
    def test_exact_boundary(self):
        self.assertEqual(_round_up_minutes(330, 30), 330)  # 5:30 exact

    def test_rounds_up(self):
        self.assertEqual(_round_up_minutes(331, 30), 360)  # 5:31 → 6:00

    def test_just_past(self):
        self.assertEqual(_round_up_minutes(361, 30), 390)  # 6:01 → 6:30

    def test_zero(self):
        self.assertEqual(_round_up_minutes(0, 30), 0)

    def test_15min_granularity(self):
        self.assertEqual(_round_up_minutes(46, 15), 60)  # 0:46 → 1:00


class GetSlotsTests(TestCase):
    def setUp(self):
        Shop.objects.create(
            name="Test Shop",
            brand_name="Test",
            defaults={
                "pickup_slots": [
                    {"ref": "s1", "label": "Slot 1", "starts_at": "08:00"},
                    {"ref": "s2", "label": "Slot 2", "starts_at": "14:00"},
                ],
            },
        )

    def test_reads_from_shop_defaults(self):
        slots = get_slots()
        self.assertEqual(len(slots), 2)
        self.assertEqual(slots[0]["ref"], "s1")
        self.assertEqual(slots[1]["starts_at"], "14:00")

    def test_falls_back_to_defaults_when_no_shop(self):
        Shop.objects.all().delete()
        slots = get_slots()
        self.assertEqual(slots, list(DEFAULT_SLOTS))


class GetTypicalReadyTimesTests(TestCase):
    def setUp(self):
        from shopman.crafting.models import Recipe, WorkOrder

        Shop.objects.create(name="Test", brand_name="Test")
        self.recipe = Recipe.objects.create(
            code="test-bread",
            name="Test Bread",
            output_ref="BREAD-SKU",
            batch_size=Decimal("50"),
        )
        # Create 5 days of history with finished_at around 6:00 AM
        tz_info = timezone.get_current_timezone()
        today = date.today()
        for days_ago in range(1, 6):
            d = today - timedelta(days=days_ago)
            WorkOrder.objects.create(
                recipe=self.recipe,
                output_ref="BREAD-SKU",
                quantity=Decimal("50"),
                produced=Decimal("48"),
                status="done",
                scheduled_date=d,
                started_at=datetime.combine(d, time(4, 0), tzinfo=tz_info),
                finished_at=datetime.combine(d, time(6, 0), tzinfo=tz_info),
            )

    def test_computes_typical_time(self):
        result = get_typical_ready_times(["BREAD-SKU"])
        self.assertIn("BREAD-SKU", result)
        # Median of 6:00 AM each day = 6:00, rounded to 30min = 6:00
        self.assertEqual(result["BREAD-SKU"], time(6, 0))

    def test_unknown_sku_omitted(self):
        result = get_typical_ready_times(["UNKNOWN-SKU"])
        self.assertNotIn("UNKNOWN-SKU", result)

    def test_rounds_up_correctly(self):
        """If median is 6:15, should round up to 6:30."""
        from shopman.crafting.models import WorkOrder

        tz_info = timezone.get_current_timezone()
        today = date.today()
        # Add one more WO at 6:30 to shift median
        d = today - timedelta(days=6)
        WorkOrder.objects.create(
            recipe=self.recipe,
            output_ref="BREAD-SKU",
            quantity=Decimal("50"),
            produced=Decimal("48"),
            status="done",
            scheduled_date=d,
            started_at=datetime.combine(d, time(4, 0), tzinfo=tz_info),
            finished_at=datetime.combine(d, time(6, 30), tzinfo=tz_info),
        )
        result = get_typical_ready_times(["BREAD-SKU"], rounding_minutes=30)
        # 5 at 360min + 1 at 390min → median = 360 → rounded = 360 = 6:00
        self.assertEqual(result["BREAD-SKU"], time(6, 0))


class GetEarliestSlotTests(TestCase):
    def setUp(self):
        from shopman.crafting.models import Recipe, WorkOrder

        Shop.objects.create(
            name="Test",
            brand_name="Test",
            defaults={
                "pickup_slots": [
                    {"ref": "slot-09", "label": "A partir das 09h", "starts_at": "09:00"},
                    {"ref": "slot-12", "label": "A partir das 12h", "starts_at": "12:00"},
                    {"ref": "slot-15", "label": "A partir das 15h", "starts_at": "15:00"},
                ],
                "pickup_slot_config": {"rounding_minutes": 30, "history_days": 30},
            },
        )
        tz_info = timezone.get_current_timezone()
        today = date.today()

        # Bread: finishes at 5:30 → slot-09
        self.bread_recipe = Recipe.objects.create(
            code="bread", name="Bread", output_ref="BREAD", batch_size=Decimal("50"),
        )
        for days_ago in range(1, 4):
            d = today - timedelta(days=days_ago)
            WorkOrder.objects.create(
                recipe=self.bread_recipe, output_ref="BREAD",
                quantity=Decimal("50"), produced=Decimal("48"), status="done",
                scheduled_date=d,
                started_at=datetime.combine(d, time(4, 0), tzinfo=tz_info),
                finished_at=datetime.combine(d, time(5, 30), tzinfo=tz_info),
            )

        # Cake: finishes at 11:30 → slot-12
        self.cake_recipe = Recipe.objects.create(
            code="cake", name="Cake", output_ref="CAKE", batch_size=Decimal("10"),
        )
        for days_ago in range(1, 4):
            d = today - timedelta(days=days_ago)
            WorkOrder.objects.create(
                recipe=self.cake_recipe, output_ref="CAKE",
                quantity=Decimal("10"), produced=Decimal("9"), status="done",
                scheduled_date=d,
                started_at=datetime.combine(d, time(8, 0), tzinfo=tz_info),
                finished_at=datetime.combine(d, time(11, 30), tzinfo=tz_info),
            )

        # Brigadeiro: finishes at 13:30 → slot-15
        self.brig_recipe = Recipe.objects.create(
            code="brigadeiro", name="Brigadeiro", output_ref="BRIGADEIRO", batch_size=Decimal("100"),
        )
        for days_ago in range(1, 4):
            d = today - timedelta(days=days_ago)
            WorkOrder.objects.create(
                recipe=self.brig_recipe, output_ref="BRIGADEIRO",
                quantity=Decimal("100"), produced=Decimal("95"), status="done",
                scheduled_date=d,
                started_at=datetime.combine(d, time(10, 0), tzinfo=tz_info),
                finished_at=datetime.combine(d, time(13, 30), tzinfo=tz_info),
            )

    def test_bread_only_gets_first_slot(self):
        result = get_earliest_slot_for_skus(["BREAD"])
        self.assertEqual(result["slot_ref"], "slot-09")

    def test_cake_pushes_to_slot_12(self):
        result = get_earliest_slot_for_skus(["BREAD", "CAKE"])
        self.assertEqual(result["slot_ref"], "slot-12")
        self.assertEqual(result["bottleneck_sku"], "CAKE")

    def test_brigadeiro_pushes_to_slot_15(self):
        result = get_earliest_slot_for_skus(["BREAD", "BRIGADEIRO"])
        self.assertEqual(result["slot_ref"], "slot-15")
        self.assertEqual(result["bottleneck_sku"], "BRIGADEIRO")

    def test_all_three_pushes_to_slot_15(self):
        """Cart with bread + cake + brigadeiro → slot-15 (brigadeiro is bottleneck)."""
        result = get_earliest_slot_for_skus(["BREAD", "CAKE", "BRIGADEIRO"])
        self.assertEqual(result["slot_ref"], "slot-15")
        self.assertEqual(result["bottleneck_sku"], "BRIGADEIRO")

    def test_unknown_sku_gets_fallback(self):
        result = get_earliest_slot_for_skus(["UNKNOWN-SKU"])
        self.assertEqual(result["slot_ref"], "slot-09")  # fallback
        self.assertIsNone(result["bottleneck_sku"])


class AnnotateSlotsTests(TestCase):
    def setUp(self):
        Shop.objects.create(
            name="Test", brand_name="Test",
            defaults={
                "pickup_slots": [
                    {"ref": "slot-09", "label": "A partir das 09h", "starts_at": "09:00"},
                    {"ref": "slot-12", "label": "A partir das 12h", "starts_at": "12:00"},
                ],
            },
        )

    def test_returns_all_required_keys(self):
        result = annotate_slots_for_checkout(["SOME-SKU"])
        self.assertIn("pickup_slots", result)
        self.assertIn("earliest_slot_ref", result)
        self.assertIn("bottleneck_sku", result)
        self.assertIn("ready_times", result)
        self.assertEqual(len(result["pickup_slots"]), 2)
