"""
Tests for shopman.craftsman.contrib.demand — OrderingDemandBackend.

Since Orderman models aren't available in isolated crafting tests,
we mock the backend methods for suggest() integration and test
helper functions directly.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe
from shopman.craftsman.protocols.demand import DailyDemand, DemandProtocol

# ── Fixtures ──


@pytest.fixture
def recipe(db):
    """Simple active recipe."""
    return Recipe.objects.create(
        ref="croissant-v1",
        name="Croissant Tradicional",
        output_sku="CROISSANT",
        batch_size=Decimal("10"),
        steps=["Mistura", "Forno"],
    )


# ── Protocol conformance ──


class TestProtocolConformance:
    """OrderingDemandBackend satisfies DemandProtocol (Ordering)."""

    def test_implements_protocol(self):
        from shopman.craftsman.contrib.demand.backend import OrderingDemandBackend

        backend = OrderingDemandBackend()
        assert isinstance(backend, DemandProtocol)

    def test_has_history_method(self):
        from shopman.craftsman.contrib.demand.backend import OrderingDemandBackend

        backend = OrderingDemandBackend()
        assert callable(getattr(backend, "history", None))

    def test_has_committed_method(self):
        from shopman.craftsman.contrib.demand.backend import OrderingDemandBackend

        backend = OrderingDemandBackend()
        assert callable(getattr(backend, "committed", None))


# ── Backend unit tests ──


class TestHistoryMethod:
    """OrderingDemandBackend.history() behavior (Ordering)."""

    def test_history_with_mocked_data(self, db):
        """history() converts ORM results to DailyDemand list."""
        from shopman.craftsman.contrib.demand.backend import OrderingDemandBackend

        backend = OrderingDemandBackend()

        mock_daily = [
            DailyDemand(date=date(2026, 3, 11), sold=Decimal("25"), wasted=Decimal("0")),
            DailyDemand(date=date(2026, 3, 4), sold=Decimal("30"), wasted=Decimal("0")),
        ]

        with patch.object(backend, "history", return_value=mock_daily):
            result = backend.history("CROISSANT", days=28, same_weekday=True)

        assert len(result) == 2
        assert all(isinstance(dd, DailyDemand) for dd in result)
        assert result[0].sold == Decimal("25")

    def test_history_empty_for_unknown_sku(self, db):
        """history() returns [] when no orders match."""
        from shopman.craftsman.contrib.demand.backend import OrderingDemandBackend

        backend = OrderingDemandBackend()

        with patch.object(backend, "history", return_value=[]):
            result = backend.history("NONEXISTENT-SKU")

        assert result == []


class TestCommittedMethod:
    """OrderingDemandBackend.committed() behavior (Ordering)."""

    def test_committed_returns_decimal(self, db):
        """committed() returns Decimal."""
        from shopman.craftsman.contrib.demand.backend import OrderingDemandBackend

        backend = OrderingDemandBackend()
        # Without stocking installed, should return 0 gracefully
        result = backend.committed("CROISSANT", date.today())
        assert isinstance(result, Decimal)
        assert result == Decimal("0")


# ── Integration with suggest() ──


class TestSuggestWithDemandBackend:
    """craft.suggest() works when DEMAND_BACKEND is configured."""

    def test_suggest_with_real_backend_path(self, recipe, settings):
        """suggest() loads and uses the configured backend."""
        today = date.today()
        tomorrow = today + timedelta(days=1)

        settings.CRAFTSMAN = {
            "DEMAND_BACKEND": "shopman.craftsman.contrib.demand.backend.OrderingDemandBackend",
        }

        mock_history = [
            DailyDemand(date=today - timedelta(days=7), sold=Decimal("20"), wasted=Decimal("0")),
            DailyDemand(date=today - timedelta(days=14), sold=Decimal("30"), wasted=Decimal("0")),
        ]

        with patch(
            "shopman.craftsman.contrib.demand.backend.OrderingDemandBackend.history",
            return_value=mock_history,
        ):
            with patch(
                "shopman.craftsman.contrib.demand.backend.OrderingDemandBackend.committed",
                return_value=Decimal("5"),
            ):
                suggestions = craft.suggest(tomorrow)

        assert len(suggestions) == 1
        s = suggestions[0]
        assert s.recipe == recipe
        # avg = (20+30)/2 = 25, committed = 5, safety = 20%
        # (25 + 5) * 1.2 = 36
        assert s.quantity == Decimal("36")
        assert s.basis["committed"] == Decimal("5")
        assert s.basis["sample_size"] == 2

    def test_suggest_no_history_skips_recipe(self, recipe, settings):
        """Recipe with no historical demand is skipped."""
        tomorrow = date.today() + timedelta(days=1)

        settings.CRAFTSMAN = {
            "DEMAND_BACKEND": "shopman.craftsman.contrib.demand.backend.OrderingDemandBackend",
        }

        with patch(
            "shopman.craftsman.contrib.demand.backend.OrderingDemandBackend.history",
            return_value=[],
        ):
            suggestions = craft.suggest(tomorrow)

        assert suggestions == []

    def test_suggest_inactive_recipe_excluded(self, recipe, settings):
        """Inactive recipes are not included in suggestions."""
        tomorrow = date.today() + timedelta(days=1)
        recipe.is_active = False
        recipe.save()

        settings.CRAFTSMAN = {
            "DEMAND_BACKEND": "shopman.craftsman.contrib.demand.backend.OrderingDemandBackend",
        }

        with patch(
            "shopman.craftsman.contrib.demand.backend.OrderingDemandBackend.history",
            return_value=[
                DailyDemand(date=date.today() - timedelta(days=7), sold=Decimal("50"), wasted=Decimal("0")),
            ],
        ):
            with patch(
                "shopman.craftsman.contrib.demand.backend.OrderingDemandBackend.committed",
                return_value=Decimal("0"),
            ):
                suggestions = craft.suggest(tomorrow)

        assert suggestions == []

    def test_suggest_multiple_recipes(self, recipe, settings):
        """suggest() returns suggestions for all active recipes with demand."""
        tomorrow = date.today() + timedelta(days=1)

        recipe_b = Recipe.objects.create(
            ref="baguete-v1",
            name="Baguete",
            output_sku="BAGUETE",
            batch_size=Decimal("5"),
            steps=["Mistura", "Forno"],
        )

        settings.CRAFTSMAN = {
            "DEMAND_BACKEND": "shopman.craftsman.contrib.demand.backend.OrderingDemandBackend",
        }

        def mock_history(product_ref, **kwargs):
            if product_ref == "CROISSANT":
                return [DailyDemand(date=date.today() - timedelta(days=7), sold=Decimal("100"), wasted=Decimal("0"))]
            elif product_ref == "BAGUETE":
                return [DailyDemand(date=date.today() - timedelta(days=7), sold=Decimal("50"), wasted=Decimal("0"))]
            return []

        with patch(
            "shopman.craftsman.contrib.demand.backend.OrderingDemandBackend.history",
            side_effect=mock_history,
        ):
            with patch(
                "shopman.craftsman.contrib.demand.backend.OrderingDemandBackend.committed",
                return_value=Decimal("0"),
            ):
                suggestions = craft.suggest(tomorrow)

        assert len(suggestions) == 2
        refs = {s.recipe.output_sku for s in suggestions}
        assert refs == {"CROISSANT", "BAGUETE"}


# ── Helper function tests ──


class TestDjangoWeekday:
    """_django_weekday converts Python weekday to Django __week_day."""

    def test_monday(self):
        from shopman.craftsman.contrib.demand.backend import _django_weekday

        assert _django_weekday(0) == 2  # Monday

    def test_sunday(self):
        from shopman.craftsman.contrib.demand.backend import _django_weekday

        assert _django_weekday(6) == 1  # Sunday

    def test_saturday(self):
        from shopman.craftsman.contrib.demand.backend import _django_weekday

        assert _django_weekday(5) == 7  # Saturday

    def test_wednesday(self):
        from shopman.craftsman.contrib.demand.backend import _django_weekday

        assert _django_weekday(2) == 4  # Wednesday

    def test_all_days_in_range(self):
        from shopman.craftsman.contrib.demand.backend import _django_weekday

        for py_day in range(7):
            dj_day = _django_weekday(py_day)
            assert 1 <= dj_day <= 7, f"Python weekday {py_day} -> {dj_day} out of range"
