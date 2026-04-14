"""
Tests for Craftsman v0.2.2 changes.

Covers:
- B1 fix: old_quantity stale in adjust() audit trail
- B2 fix: receive() loop returns on first iteration
- Hardening: CheckConstraints (DB-level), clean()/full_clean()
- BOM Snapshot: plan-time freeze, finish uses snapshot, backward compat
- Consumed validation: warning for unknown item_refs
- suggest(output_refs=): filter parameter
- Concurrency: simulated optimistic locking scenarios
- API: plan endpoint, query endpoints (expected, needs, suggest), pagination
"""

import logging
import pytest
from datetime import date, time
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from rest_framework.test import APIClient

from shopman.craftsman import craft, CraftError, StaleRevision
from shopman.craftsman.models import (
    Recipe,
    RecipeItem,
    WorkOrder,
    WorkOrderEvent,
    WorkOrderItem,
)


# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def recipe(db):
    """Simple recipe: 10 croissants."""
    return Recipe.objects.create(
        code="croissant-v1",
        name="Croissant Tradicional",
        output_ref="croissant",
        batch_size=Decimal("10"),
        steps=["Mistura", "Modelagem", "Forno"],
    )


@pytest.fixture
def recipe_with_items(recipe):
    """Recipe with 3 ingredients."""
    RecipeItem.objects.create(recipe=recipe, input_ref="farinha", quantity=Decimal("5"), unit="kg", sort_order=0)
    RecipeItem.objects.create(recipe=recipe, input_ref="agua", quantity=Decimal("3"), unit="L", sort_order=1)
    RecipeItem.objects.create(recipe=recipe, input_ref="fermento", quantity=Decimal("0.100"), unit="kg", sort_order=2)
    return recipe


@pytest.fixture
def recipe_b(db):
    """Second recipe for filtering tests."""
    r = Recipe.objects.create(
        code="baguette-v1",
        name="Baguette",
        output_ref="baguette",
        batch_size=Decimal("5"),
    )
    RecipeItem.objects.create(recipe=r, input_ref="farinha", quantity=Decimal("3"), unit="kg", sort_order=0)
    RecipeItem.objects.create(recipe=r, input_ref="agua", quantity=Decimal("2"), unit="L", sort_order=1)
    return r


@pytest.fixture
def tomorrow():
    return date(2026, 2, 27)


@pytest.fixture
def api_client():
    user = User.objects.create_user(username="testuser", password="testpass")
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def anon_client():
    return APIClient()


# ══════════════════════════════════════════════════════════════
# B1 FIX: old_quantity stale in adjust() audit
# ══════════════════════════════════════════════════════════════


class TestB1OldQuantityFix:
    """Verify adjust() event payload['from'] reflects DB value, not stale caller."""

    def test_adjust_event_from_reflects_db_value(self, recipe):
        """After adjust, event['from'] should match actual DB value."""
        wo = craft.plan(recipe, 100)
        craft.adjust(wo, quantity=97)

        events = list(wo.events.order_by("seq"))
        assert events[1].kind == "adjusted"
        assert Decimal(events[1].payload["from"]) == Decimal("100")
        assert Decimal(events[1].payload["to"]) == Decimal("97")

    def test_sequential_adjusts_correct_from(self, recipe):
        """Two sequential adjusts: second event 'from' = first adjust's 'to'."""
        wo = craft.plan(recipe, 100)
        craft.adjust(wo, quantity=97)
        craft.adjust(wo, quantity=90)

        events = list(wo.events.order_by("seq"))
        assert Decimal(events[1].payload["from"]) == Decimal("100")
        assert Decimal(events[1].payload["to"]) == Decimal("97")
        assert Decimal(events[2].payload["from"]) == Decimal("97")
        assert Decimal(events[2].payload["to"]) == Decimal("90")

    def test_adjust_last_write_wins_correct_from(self, recipe):
        """Without expected_rev (last-write-wins), 'from' still reflects DB."""
        wo = craft.plan(recipe, 100)

        # Simulate stale caller: adjust without rev check
        craft.adjust(wo, quantity=80)
        # wo.quantity is now 80 from the first adjust
        craft.adjust(wo, quantity=60)

        events = list(wo.events.order_by("seq"))
        assert Decimal(events[2].payload["from"]) == Decimal("80")  # not stale 100
        assert Decimal(events[2].payload["to"]) == Decimal("60")


# ══════════════════════════════════════════════════════════════
# B2 FIX: receive() loop (stocking adapter)
# ══════════════════════════════════════════════════════════════


class TestB2ReceiveLoopFix:
    """Verify StockingBackend.receive() processes all items, not just first."""

    def test_receive_processes_multiple_items(self):
        """receive() should process all MaterialProduced items."""
        from shopman.craftsman.adapters.stock import StockingBackend
        from shopman.craftsman.protocols.inventory import MaterialProduced, ReceiveResult

        backend = StockingBackend()

        items = [
            MaterialProduced(sku="croissant", quantity=Decimal("50")),
            MaterialProduced(sku="pain-au-chocolat", quantity=Decimal("30")),
        ]

        mock_stock = MagicMock()
        mock_quant1 = MagicMock(pk=1)
        mock_quant2 = MagicMock(pk=2)
        mock_stock.receive.side_effect = [mock_quant1, mock_quant2]

        mock_product1 = MagicMock()
        mock_product2 = MagicMock()
        mock_position = MagicMock()

        with patch.object(backend, "_get_stock", return_value=mock_stock), \
             patch.object(backend, "_get_product", side_effect=[mock_product1, mock_product2]), \
             patch.object(backend, "_get_position", return_value=mock_position), \
             patch("shopman.craftsman.adapters.stock._stockman_available", return_value=True):
            result = backend.receive(items, ref="WO-2026-00001")

        assert result.success is True
        assert result.quant_id == "quant:2"  # last item's quant
        assert mock_stock.receive.call_count == 2


# ══════════════════════════════════════════════════════════════
# HARDENING: CheckConstraints + clean/full_clean
# ══════════════════════════════════════════════════════════════


class TestCheckConstraints:
    """DB-level constraints prevent invalid data even bypassing Python validation."""

    def test_recipe_batch_size_positive_constraint(self, db):
        """Recipe.batch_size must be > 0 at DB level."""
        with pytest.raises((IntegrityError, ValidationError)):
            Recipe.objects.create(
                code="bad-batch", name="Bad", output_ref="x",
                batch_size=Decimal("0"),
            )

    def test_recipe_item_quantity_positive_constraint(self, recipe):
        """RecipeItem.quantity must be > 0 at DB level."""
        with pytest.raises((IntegrityError, ValidationError)):
            RecipeItem.objects.create(
                recipe=recipe, input_ref="test",
                quantity=Decimal("0"), unit="kg",
            )

    def test_work_order_quantity_positive_constraint(self, recipe):
        """WorkOrder.quantity must be > 0 at DB level."""
        with pytest.raises((IntegrityError, ValidationError)):
            WorkOrder.objects.create(
                recipe=recipe, output_ref="croissant",
                quantity=Decimal("0"),
            )

    def test_work_order_negative_quantity_rejected(self, recipe):
        """WorkOrder.quantity must be > 0 — negative also rejected."""
        with pytest.raises((IntegrityError, ValidationError)):
            WorkOrder.objects.create(
                recipe=recipe, output_ref="croissant",
                quantity=Decimal("-5"),
            )


class TestWorkOrderClean:
    """WorkOrder.clean() and save() validation."""

    def test_save_calls_full_clean_on_create(self, recipe):
        """save() without update_fields calls full_clean()."""
        with pytest.raises(ValidationError):
            WorkOrder.objects.create(
                recipe=recipe, output_ref="croissant",
                quantity=Decimal("-1"),
            )

    def test_save_with_update_fields_skips_full_clean(self, recipe):
        """save(update_fields=[...]) skips full_clean (service pattern)."""
        wo = craft.plan(recipe, 100)
        # Services use save(update_fields=...) which should not trigger full_clean
        wo.status = WorkOrder.Status.FINISHED
        wo.save(update_fields=["status", "updated_at"])
        wo.refresh_from_db()
        assert wo.status == WorkOrder.Status.FINISHED


# ══════════════════════════════════════════════════════════════
# BOM SNAPSHOT
# ══════════════════════════════════════════════════════════════


class TestBOMSnapshot:
    """BOM snapshot: freeze recipe items at plan-time, use in finish."""

    def test_plan_creates_snapshot(self, recipe_with_items):
        """plan() stores _recipe_snapshot in WorkOrder.meta."""
        wo = craft.plan(recipe_with_items, 100)

        assert "_recipe_snapshot" in wo.meta
        snapshot = wo.meta["_recipe_snapshot"]
        assert snapshot["batch_size"] == "10"
        assert len(snapshot["items"]) == 3
        assert snapshot["items"][0]["input_ref"] == "farinha"
        assert Decimal(snapshot["items"][0]["quantity"]) == Decimal("5")
        assert snapshot["items"][0]["unit"] == "kg"

    def test_plan_preserves_user_meta(self, recipe_with_items):
        """plan() with user meta keeps both user and system keys."""
        wo = craft.plan(recipe_with_items, 100, meta={"priority": "high"})

        assert wo.meta["priority"] == "high"
        assert "_recipe_snapshot" in wo.meta

    def test_finish_uses_snapshot_not_current_recipe(self, recipe_with_items):
        """After plan, modifying recipe doesn't affect finish() BOM."""
        wo = craft.plan(recipe_with_items, 100)

        # Modify recipe AFTER plan (e.g., changing farinha qty)
        farinha_item = RecipeItem.objects.get(recipe=recipe_with_items, input_ref="farinha")
        farinha_item.quantity = Decimal("10")  # was 5
        farinha_item.save()

        craft.finish(wo, finished=93, expected_rev=0)

        # Requirements should use snapshot (5kg per batch), not current (10kg per batch)
        reqs = WorkOrderItem.objects.filter(work_order=wo, kind=WorkOrderItem.Kind.REQUIREMENT)
        farinha_req = reqs.get(item_ref="farinha")
        # 100 / 10 (batch) * 5 (snapshot qty) = 50
        assert farinha_req.quantity == Decimal("50.000")

    def test_finish_backward_compat_no_snapshot(self, recipe_with_items):
        """WO without snapshot (pre-v0.2.2) falls back to current recipe."""
        wo = craft.plan(recipe_with_items, 100)

        # Simulate pre-v0.2.2 WO: remove snapshot from meta
        wo.meta = {}
        wo.save(update_fields=["meta", "updated_at"])

        craft.finish(wo, finished=93, expected_rev=0)

        # Should use current recipe items
        reqs = WorkOrderItem.objects.filter(work_order=wo, kind=WorkOrderItem.Kind.REQUIREMENT)
        assert reqs.count() == 3
        farinha_req = reqs.get(item_ref="farinha")
        assert farinha_req.quantity == Decimal("50.000")

    def test_batch_plan_creates_snapshots(self, recipe_with_items, recipe_b, tomorrow):
        """Batch plan creates snapshot for each WO."""
        orders = craft.plan([
            (recipe_with_items, 100),
            (recipe_b, 50),
        ], date=tomorrow)

        for wo in orders:
            assert "_recipe_snapshot" in wo.meta
        assert len(orders[0].meta["_recipe_snapshot"]["items"]) == 3
        assert len(orders[1].meta["_recipe_snapshot"]["items"]) == 2


# ══════════════════════════════════════════════════════════════
# CONSUMED VALIDATION
# ══════════════════════════════════════════════════════════════


class TestConsumedValidation:
    """finish() warns on consumed item_refs not in recipe."""

    def test_consumed_unknown_item_ref_logs_warning(self, recipe_with_items, caplog):
        """Consumed items not in recipe trigger warning log."""
        wo = craft.plan(recipe_with_items, 100)

        with caplog.at_level(logging.WARNING, logger="shopman.craftsman.services.execution"):
            craft.finish(wo, finished=93, consumed=[
                {"item_ref": "farinha", "quantity": 50, "unit": "kg"},
                {"item_ref": "agua", "quantity": 30, "unit": "L"},
                {"item_ref": "fermento", "quantity": 1, "unit": "kg"},
                {"item_ref": "UNKNOWN_INGREDIENT", "quantity": 5, "unit": "kg"},
            ], expected_rev=0)

        assert any("UNKNOWN_INGREDIENT" in record.message for record in caplog.records)
        assert any("not in recipe" in record.message for record in caplog.records)
        # But finish still succeeds (warning, not error)
        assert wo.status == WorkOrder.Status.FINISHED

    def test_consumed_valid_items_no_warning(self, recipe_with_items, caplog):
        """Consumed items matching recipe don't trigger warnings."""
        wo = craft.plan(recipe_with_items, 100)

        with caplog.at_level(logging.WARNING, logger="shopman.craftsman.services.execution"):
            craft.finish(wo, finished=93, consumed=[
                {"item_ref": "farinha", "quantity": 50, "unit": "kg"},
                {"item_ref": "agua", "quantity": 30, "unit": "L"},
                {"item_ref": "fermento", "quantity": 1, "unit": "kg"},
            ], expected_rev=0)

        warning_messages = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
        assert not any("not in recipe" in m for m in warning_messages)


# ══════════════════════════════════════════════════════════════
# SUGGEST WITH OUTPUT_REFS FILTER
# ══════════════════════════════════════════════════════════════


class TestSuggestFilter:
    """craft.suggest(output_refs=...) filters recipes."""

    def test_suggest_with_output_refs_filter(self, recipe, recipe_b, tomorrow, settings):
        """suggest(output_refs=["croissant"]) only returns croissant suggestion."""
        from shopman.craftsman.protocols.demand import DailyDemand

        mock_backend = MagicMock()
        mock_backend.history.return_value = [
            DailyDemand(date=date(2026, 2, 18), sold=Decimal("80"), wasted=Decimal("0")),
        ]
        mock_backend.committed.return_value = Decimal("0")
        mock_backend_class = MagicMock(return_value=mock_backend)

        settings.CRAFTSMAN = {"DEMAND_BACKEND": "test.MockDemandBackend"}

        with patch(
            "django.utils.module_loading.import_string",
            return_value=mock_backend_class,
        ):
            suggestions = craft.suggest(tomorrow, output_refs=["croissant"])

        assert len(suggestions) == 1
        assert suggestions[0].recipe.output_ref == "croissant"
        # history() should only be called for croissant, not baguette
        assert mock_backend.history.call_count == 1
        mock_backend.history.assert_called_once_with(
            "croissant", days=28, same_weekday=True,
        )

    def test_suggest_without_filter_returns_all(self, recipe, recipe_b, tomorrow, settings):
        """suggest() without filter includes all active recipes."""
        from shopman.craftsman.protocols.demand import DailyDemand

        mock_backend = MagicMock()
        mock_backend.history.return_value = [
            DailyDemand(date=date(2026, 2, 18), sold=Decimal("80"), wasted=Decimal("0")),
        ]
        mock_backend.committed.return_value = Decimal("0")
        mock_backend_class = MagicMock(return_value=mock_backend)

        settings.CRAFTSMAN = {"DEMAND_BACKEND": "test.MockDemandBackend"}

        with patch(
            "django.utils.module_loading.import_string",
            return_value=mock_backend_class,
        ):
            suggestions = craft.suggest(tomorrow)

        assert len(suggestions) == 2
        refs = {s.recipe.output_ref for s in suggestions}
        assert refs == {"croissant", "baguette"}


# ══════════════════════════════════════════════════════════════
# CONCURRENCY (SIMULATED)
# ══════════════════════════════════════════════════════════════


class TestConcurrency:
    """
    Simulated concurrency tests using optimistic locking.

    NOTE: For real concurrency tests, use PostgreSQL + threads.
    SQLite serializes transactions, so true race conditions can't be
    reproduced. These tests validate the optimistic locking protocol.
    """

    def test_sequential_adjusts_with_correct_revs(self, recipe):
        """Two sequential adjusts with correct expected_rev succeed."""
        wo = craft.plan(recipe, 100)
        craft.adjust(wo, quantity=97, expected_rev=0)
        craft.adjust(wo, quantity=90, expected_rev=1)

        wo.refresh_from_db()
        assert wo.quantity == Decimal("90")
        assert wo.rev == 2

    def test_adjust_with_stale_rev_raises(self, recipe):
        """adjust() with stale expected_rev raises StaleRevision."""
        wo = craft.plan(recipe, 100)
        craft.adjust(wo, quantity=97, expected_rev=0)

        with pytest.raises(StaleRevision) as exc:
            craft.adjust(wo, quantity=90, expected_rev=0)  # stale!
        assert exc.value.data["expected_rev"] == 0

    def test_finish_with_stale_rev_raises(self, recipe):
        """finish() with stale expected_rev raises StaleRevision."""
        wo = craft.plan(recipe, 100)
        craft.adjust(wo, quantity=97, expected_rev=0)

        with pytest.raises(StaleRevision):
            craft.finish(wo, finished=93, expected_rev=0)  # stale!

    def test_void_with_stale_rev_raises(self, recipe):
        """void() with stale expected_rev raises StaleRevision."""
        wo = craft.plan(recipe, 100)
        craft.adjust(wo, quantity=97, expected_rev=0)

        with pytest.raises(StaleRevision):
            craft.void(wo, reason="cancel", expected_rev=0)  # stale!

    def test_adjust_without_rev_is_last_write_wins(self, recipe):
        """adjust() without expected_rev always succeeds (last-write-wins)."""
        wo = craft.plan(recipe, 100)
        craft.adjust(wo, quantity=97)
        craft.adjust(wo, quantity=90)
        craft.adjust(wo, quantity=80)

        wo.refresh_from_db()
        assert wo.quantity == Decimal("80")
        assert wo.rev == 3

    def test_rev_correct_after_plan_adjust_finish(self, recipe):
        """Full lifecycle: plan(rev=0) → adjust(rev=1) → finish(rev=2)."""
        wo = craft.plan(recipe, 100)
        assert wo.rev == 0

        craft.adjust(wo, quantity=97, expected_rev=0)
        assert wo.rev == 1

        craft.finish(wo, finished=93, expected_rev=1)
        wo.refresh_from_db()
        assert wo.rev == 2

    # TODO: For real concurrency tests under PostgreSQL + threads,
    # use a dedicated test module with pytest-xdist or threading.


# ══════════════════════════════════════════════════════════════
# API: PLAN ENDPOINT
# ══════════════════════════════════════════════════════════════


class TestPlanEndpoint:
    def test_plan_creates_work_order(self, api_client, recipe_with_items, tomorrow):
        """POST /api/craftsman/work-orders/plan/ creates a WO."""
        resp = api_client.post(
            "/api/craftsman/work-orders/plan/",
            {
                "recipe_code": "croissant-v1",
                "quantity": "100",
                "date": str(tomorrow),
            },
            format="json",
        )
        assert resp.status_code == 201
        assert resp.data["output_ref"] == "croissant"
        assert resp.data["quantity"] == "100.000"
        assert resp.data["target_date"] == str(tomorrow)
        assert resp.data["status"] == "planned"

    def test_plan_with_all_fields(self, api_client, recipe_with_items, tomorrow):
        """Plan with all optional fields."""
        resp = api_client.post(
            "/api/craftsman/work-orders/plan/",
            {
                "recipe_code": "croissant-v1",
                "quantity": "50",
                "date": str(tomorrow),
                "source_ref": "order:789",
                "position_ref": "station:forno-01",
                "operator_ref": "user:joao",
                "actor": "api-user",
                "meta": {"priority": "high"},
            },
            format="json",
        )
        assert resp.status_code == 201
        assert resp.data["source_ref"] == "order:789"
        assert resp.data["position_ref"] == "station:forno-01"
        assert resp.data["operator_ref"] == "user:joao"

    def test_plan_recipe_not_found(self, api_client):
        """Plan with nonexistent recipe returns 404."""
        resp = api_client.post(
            "/api/craftsman/work-orders/plan/",
            {"recipe_code": "nonexistent", "quantity": "100"},
            format="json",
        )
        assert resp.status_code == 404
        assert resp.data["error"] == "RECIPE_NOT_FOUND"

    def test_plan_inactive_recipe_returns_404(self, api_client, recipe):
        """Plan with inactive recipe returns 404."""
        recipe.is_active = False
        recipe.save()

        resp = api_client.post(
            "/api/craftsman/work-orders/plan/",
            {"recipe_code": "croissant-v1", "quantity": "100"},
            format="json",
        )
        assert resp.status_code == 404

    def test_plan_invalid_quantity(self, api_client, recipe):
        """Plan with invalid quantity returns 400."""
        resp = api_client.post(
            "/api/craftsman/work-orders/plan/",
            {"recipe_code": "croissant-v1", "quantity": "0"},
            format="json",
        )
        assert resp.status_code == 400

    def test_plan_missing_fields(self, api_client):
        """Plan missing required fields returns 400."""
        resp = api_client.post(
            "/api/craftsman/work-orders/plan/",
            {},
            format="json",
        )
        assert resp.status_code == 400
        assert "recipe_code" in resp.data
        assert "quantity" in resp.data

    def test_plan_requires_auth(self, anon_client, recipe):
        """Plan requires authentication."""
        resp = anon_client.post(
            "/api/craftsman/work-orders/plan/",
            {"recipe_code": "croissant-v1", "quantity": "100"},
            format="json",
        )
        assert resp.status_code in (401, 403)


# ══════════════════════════════════════════════════════════════
# API: QUERY ENDPOINTS
# ══════════════════════════════════════════════════════════════


class TestExpectedEndpoint:
    def test_expected_returns_total(self, api_client, recipe, tomorrow):
        """GET /api/craftsman/queries/expected/ returns sum of planned/started WOs."""
        craft.plan(recipe, 100, date=tomorrow)
        craft.plan(recipe, 50, date=tomorrow)

        resp = api_client.get(
            f"/api/craftsman/queries/expected/?output_ref=croissant&date={tomorrow}",
        )
        assert resp.status_code == 200
        assert resp.data["output_ref"] == "croissant"
        assert resp.data["total"] == "150"

    def test_expected_zero_when_none(self, api_client, tomorrow):
        """Expected returns 0 when no matching WOs."""
        resp = api_client.get(
            f"/api/craftsman/queries/expected/?output_ref=nada&date={tomorrow}",
        )
        assert resp.status_code == 200
        assert resp.data["total"] == "0"

    def test_expected_missing_params(self, api_client):
        """Missing params returns 400."""
        resp = api_client.get("/api/craftsman/queries/expected/")
        assert resp.status_code == 400
        assert resp.data["error"] == "MISSING_PARAMS"

    def test_expected_missing_date(self, api_client):
        """Missing date returns 400."""
        resp = api_client.get("/api/craftsman/queries/expected/?output_ref=croissant")
        assert resp.status_code == 400

    def test_expected_invalid_date(self, api_client):
        """Invalid date format returns 400."""
        resp = api_client.get("/api/craftsman/queries/expected/?output_ref=croissant&date=invalid")
        assert resp.status_code == 400
        assert resp.data["error"] == "INVALID_DATE"

    def test_expected_requires_auth(self, anon_client, tomorrow):
        """Expected requires authentication."""
        resp = anon_client.get(f"/api/craftsman/queries/expected/?output_ref=x&date={tomorrow}")
        assert resp.status_code in (401, 403)


class TestNeedsEndpoint:
    def test_needs_returns_bom(self, api_client, recipe_with_items, tomorrow):
        """GET /api/craftsman/queries/needs/ returns BOM explosion."""
        craft.plan(recipe_with_items, 100, date=tomorrow)

        resp = api_client.get(f"/api/craftsman/queries/needs/?date={tomorrow}")
        assert resp.status_code == 200
        assert len(resp.data) == 3

        by_ref = {n["item_ref"]: n for n in resp.data}
        assert by_ref["farinha"]["quantity"] == "50.000"
        assert by_ref["farinha"]["unit"] == "kg"
        assert by_ref["farinha"]["has_recipe"] is False

    def test_needs_empty_when_no_orders(self, api_client, tomorrow):
        """Needs returns [] when no planned/started WOs on date."""
        resp = api_client.get(f"/api/craftsman/queries/needs/?date={tomorrow}")
        assert resp.status_code == 200
        assert resp.data == []

    def test_needs_with_expand(self, api_client, recipe_with_items, tomorrow):
        """Needs with expand=true works."""
        craft.plan(recipe_with_items, 100, date=tomorrow)
        resp = api_client.get(f"/api/craftsman/queries/needs/?date={tomorrow}&expand=true")
        assert resp.status_code == 200
        assert len(resp.data) == 3

    def test_needs_missing_date(self, api_client):
        """Missing date returns 400."""
        resp = api_client.get("/api/craftsman/queries/needs/")
        assert resp.status_code == 400
        assert resp.data["error"] == "MISSING_PARAMS"

    def test_needs_invalid_date(self, api_client):
        """Invalid date returns 400."""
        resp = api_client.get("/api/craftsman/queries/needs/?date=not-a-date")
        assert resp.status_code == 400
        assert resp.data["error"] == "INVALID_DATE"

    def test_needs_requires_auth(self, anon_client, tomorrow):
        """Needs requires authentication."""
        resp = anon_client.get(f"/api/craftsman/queries/needs/?date={tomorrow}")
        assert resp.status_code in (401, 403)


class TestSuggestEndpoint:
    def test_suggest_no_backend(self, api_client, recipe, tomorrow):
        """Without DEMAND_BACKEND, suggest returns []."""
        resp = api_client.get(f"/api/craftsman/queries/suggest/?date={tomorrow}")
        assert resp.status_code == 200
        assert resp.data == []

    def test_suggest_with_backend(self, api_client, recipe, tomorrow, settings):
        """Suggest with mocked backend returns suggestions."""
        from shopman.craftsman.protocols.demand import DailyDemand

        mock_backend = MagicMock()
        mock_backend.history.return_value = [
            DailyDemand(date=date(2026, 2, 18), sold=Decimal("100"), wasted=Decimal("0")),
        ]
        mock_backend.committed.return_value = Decimal("0")
        mock_backend_class = MagicMock(return_value=mock_backend)

        settings.CRAFTSMAN = {"DEMAND_BACKEND": "test.MockDemandBackend"}

        with patch(
            "django.utils.module_loading.import_string",
            return_value=mock_backend_class,
        ):
            resp = api_client.get(f"/api/craftsman/queries/suggest/?date={tomorrow}")

        assert resp.status_code == 200
        assert len(resp.data) == 1
        assert resp.data[0]["recipe_code"] == "croissant-v1"
        assert resp.data[0]["output_ref"] == "croissant"
        assert "quantity" in resp.data[0]
        assert "basis" in resp.data[0]

    def test_suggest_with_output_refs_filter(self, api_client, recipe, recipe_b, tomorrow, settings):
        """Suggest with output_refs filter returns only matching recipes."""
        from shopman.craftsman.protocols.demand import DailyDemand

        mock_backend = MagicMock()
        mock_backend.history.return_value = [
            DailyDemand(date=date(2026, 2, 18), sold=Decimal("100"), wasted=Decimal("0")),
        ]
        mock_backend.committed.return_value = Decimal("0")
        mock_backend_class = MagicMock(return_value=mock_backend)

        settings.CRAFTSMAN = {"DEMAND_BACKEND": "test.MockDemandBackend"}

        with patch(
            "django.utils.module_loading.import_string",
            return_value=mock_backend_class,
        ):
            resp = api_client.get(
                f"/api/craftsman/queries/suggest/?date={tomorrow}&output_refs=croissant",
            )

        assert resp.status_code == 200
        assert len(resp.data) == 1
        assert resp.data[0]["output_ref"] == "croissant"

    def test_suggest_missing_date(self, api_client):
        """Missing date returns 400."""
        resp = api_client.get("/api/craftsman/queries/suggest/")
        assert resp.status_code == 400
        assert resp.data["error"] == "MISSING_PARAMS"

    def test_suggest_invalid_date(self, api_client):
        """Invalid date returns 400."""
        resp = api_client.get("/api/craftsman/queries/suggest/?date=invalid")
        assert resp.status_code == 400
        assert resp.data["error"] == "INVALID_DATE"

    def test_suggest_requires_auth(self, anon_client, tomorrow):
        """Suggest requires authentication."""
        resp = anon_client.get(f"/api/craftsman/queries/suggest/?date={tomorrow}")
        assert resp.status_code in (401, 403)


# ══════════════════════════════════════════════════════════════
# API: PAGINATION
# ══════════════════════════════════════════════════════════════


class TestPagination:
    """Pagination on list endpoints."""

    def test_work_orders_paginated(self, api_client, recipe):
        """Work order list is paginated with limit/offset."""
        for _ in range(5):
            craft.plan(recipe, 10)

        resp = api_client.get("/api/craftsman/work-orders/?limit=2&offset=0")
        assert resp.status_code == 200
        assert resp.data["count"] == 5
        assert len(resp.data["results"]) == 2
        assert "next" in resp.data

    def test_work_orders_default_limit(self, api_client, recipe):
        """Default limit is 50."""
        for _ in range(3):
            craft.plan(recipe, 10)

        resp = api_client.get("/api/craftsman/work-orders/")
        assert resp.status_code == 200
        # With pagination, response wraps in {count, next, previous, results}
        assert resp.data["count"] == 3
        assert len(resp.data["results"]) == 3

    def test_recipes_paginated(self, api_client, recipe, recipe_b):
        """Recipe list is also paginated."""
        resp = api_client.get("/api/craftsman/recipes/?limit=1")
        assert resp.status_code == 200
        assert resp.data["count"] == 2
        assert len(resp.data["results"]) == 1

    def test_pagination_offset(self, api_client, recipe):
        """Offset skips results correctly."""
        for _ in range(5):
            craft.plan(recipe, 10)

        resp = api_client.get("/api/craftsman/work-orders/?limit=2&offset=4")
        assert resp.status_code == 200
        assert resp.data["count"] == 5
        assert len(resp.data["results"]) == 1  # only 1 left after offset=4
