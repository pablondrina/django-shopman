"""
API integration tests — HTTP-level tests using DRF's APIClient.

Covers:
- Authentication enforcement (401 without auth)
- HTTP status codes: 200, 400, 409
- Serializer validation (consumed sub-serializer, required fields)
- URL routing via router
"""

from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe, RecipeItem

# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def api_client():
    user = User.objects.create_user(username="testuser", password="testpass")
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def anon_client():
    return APIClient()


@pytest.fixture
def recipe(db):
    return Recipe.objects.create(
        code="croissant-v1",
        name="Croissant Tradicional",
        output_ref="croissant",
        batch_size=Decimal("10"),
    )


@pytest.fixture
def recipe_with_items(recipe):
    RecipeItem.objects.create(
        recipe=recipe, input_ref="farinha", quantity=Decimal("5"), unit="kg", sort_order=0,
    )
    RecipeItem.objects.create(
        recipe=recipe, input_ref="agua", quantity=Decimal("3"), unit="L", sort_order=1,
    )
    return recipe


# ══════════════════════════════════════════════════════════════
# AUTHENTICATION
# ══════════════════════════════════════════════════════════════


class TestAuthentication:
    def test_list_requires_auth(self, anon_client):
        resp = anon_client.get("/api/craftsman/work-orders/")
        assert resp.status_code in (401, 403)

    def test_finish_requires_auth(self, anon_client, recipe):
        wo = craft.plan(recipe, 100)
        resp = anon_client.post(f"/api/craftsman/work-orders/{wo.ref}/finish/", {})
        assert resp.status_code in (401, 403)

    def test_authenticated_can_list(self, api_client, recipe):
        craft.plan(recipe, 100)
        resp = api_client.get("/api/craftsman/work-orders/")
        assert resp.status_code == 200

    def test_queue_requires_auth(self, anon_client):
        resp = anon_client.get("/api/craftsman/queries/queue/")
        assert resp.status_code in (401, 403)


# ══════════════════════════════════════════════════════════════
# FINISH ENDPOINT
# ══════════════════════════════════════════════════════════════


class TestFinishEndpoint:
    def test_finish_returns_200(self, api_client, recipe_with_items):
        wo = craft.plan(recipe_with_items, 100)
        resp = api_client.post(
            f"/api/craftsman/work-orders/{wo.ref}/finish/",
            {"finished": "93", "expected_rev": 0},
            format="json",
        )
        assert resp.status_code == 200
        assert resp.data["status"] == "finished"
        assert resp.data["finished"] == "93.000"
        assert resp.data["finished_qty"] == "93.000"

    def test_finish_terminal_returns_400(self, api_client, recipe):
        wo = craft.plan(recipe, 100)
        craft.finish(wo, finished=93, expected_rev=0)

        resp = api_client.post(
            f"/api/craftsman/work-orders/{wo.ref}/finish/",
            {"finished": "50", "expected_rev": 1},
            format="json",
        )
        assert resp.status_code == 400
        assert resp.data["error"] == "TERMINAL_STATUS"

    def test_finish_stale_rev_returns_409(self, api_client, recipe_with_items):
        wo = craft.plan(recipe_with_items, 100)
        craft.adjust(wo, quantity=97)  # rev now 1

        resp = api_client.post(
            f"/api/craftsman/work-orders/{wo.ref}/finish/",
            {"finished": "93", "expected_rev": 0},
            format="json",
        )
        assert resp.status_code == 409
        assert resp.data["error"] == "STALE_REVISION"

    def test_finish_missing_finished_returns_400(self, api_client, recipe):
        wo = craft.plan(recipe, 100)
        resp = api_client.post(
            f"/api/craftsman/work-orders/{wo.ref}/finish/",
            {},
            format="json",
        )
        assert resp.status_code == 400
        assert "finished" in resp.data

    def test_finish_with_valid_consumed(self, api_client, recipe_with_items):
        wo = craft.plan(recipe_with_items, 100)
        resp = api_client.post(
            f"/api/craftsman/work-orders/{wo.ref}/finish/",
            {
                "finished": "93",
                "expected_rev": 0,
                "consumed": [
                    {"item_ref": "farinha", "quantity": "48.5", "unit": "kg"},
                    {"item_ref": "agua", "quantity": "29", "unit": "L"},
                ],
            },
            format="json",
        )
        assert resp.status_code == 200

    def test_finish_consumed_missing_item_ref_returns_400(self, api_client, recipe_with_items):
        wo = craft.plan(recipe_with_items, 100)
        resp = api_client.post(
            f"/api/craftsman/work-orders/{wo.ref}/finish/",
            {
                "finished": "93",
                "consumed": [
                    {"quantity": "48.5"},  # missing item_ref
                ],
            },
            format="json",
        )
        assert resp.status_code == 400

    def test_finish_consumed_missing_quantity_returns_400(self, api_client, recipe_with_items):
        wo = craft.plan(recipe_with_items, 100)
        resp = api_client.post(
            f"/api/craftsman/work-orders/{wo.ref}/finish/",
            {
                "finished": "93",
                "consumed": [
                    {"item_ref": "farinha"},  # missing quantity
                ],
            },
            format="json",
        )
        assert resp.status_code == 400

    def test_finish_with_idempotency(self, api_client, recipe_with_items):
        wo = craft.plan(recipe_with_items, 100)
        payload = {
            "finished": "93",
            "expected_rev": 0,
            "idempotency_key": "finish-http-001",
        }
        resp1 = api_client.post(
            f"/api/craftsman/work-orders/{wo.ref}/finish/", payload, format="json",
        )
        assert resp1.status_code == 200

        resp2 = api_client.post(
            f"/api/craftsman/work-orders/{wo.ref}/finish/",
            {"finished": "50", "idempotency_key": "finish-http-001"},
            format="json",
        )
        assert resp2.status_code == 200
        assert resp2.data["finished"] == "93.000"  # original preserved


# ══════════════════════════════════════════════════════════════
# ADJUST ENDPOINT
# ══════════════════════════════════════════════════════════════


class TestAdjustEndpoint:
    def test_adjust_returns_200(self, api_client, recipe):
        wo = craft.plan(recipe, 100)
        resp = api_client.post(
            f"/api/craftsman/work-orders/{wo.ref}/adjust/",
            {"quantity": "97", "reason": "farinha insuficiente", "expected_rev": 0},
            format="json",
        )
        assert resp.status_code == 200
        assert resp.data["quantity"] == "97.000"

    def test_adjust_stale_rev_returns_409(self, api_client, recipe):
        wo = craft.plan(recipe, 100)
        craft.adjust(wo, quantity=97)  # rev now 1

        resp = api_client.post(
            f"/api/craftsman/work-orders/{wo.ref}/adjust/",
            {"quantity": "95", "expected_rev": 0},
            format="json",
        )
        assert resp.status_code == 409

    def test_adjust_terminal_returns_400(self, api_client, recipe):
        wo = craft.plan(recipe, 100)
        craft.finish(wo, finished=93, expected_rev=0)

        resp = api_client.post(
            f"/api/craftsman/work-orders/{wo.ref}/adjust/",
            {"quantity": "50"},
            format="json",
        )
        assert resp.status_code == 400
        assert resp.data["error"] == "INVALID_STATUS"

    def test_adjust_missing_quantity_returns_400(self, api_client, recipe):
        wo = craft.plan(recipe, 100)
        resp = api_client.post(
            f"/api/craftsman/work-orders/{wo.ref}/adjust/",
            {},
            format="json",
        )
        assert resp.status_code == 400


class TestOperationalQueries:
    def test_queue_returns_active_work(self, api_client, recipe):
        planned = craft.plan(recipe, 100, date="2026-02-27", position_ref="forno")
        started = craft.plan(recipe, 80, date="2026-02-27", position_ref="forno", operator_ref="user:joao")
        craft.start(started, quantity=Decimal("75"), expected_rev=0, position_ref="forno", operator_ref="user:joao")
        finished = craft.plan(recipe, 50, date="2026-02-27", position_ref="forno")
        craft.finish(finished, finished=Decimal("47"), expected_rev=0)

        resp = api_client.get("/api/craftsman/queries/queue/?date=2026-02-27&position_ref=forno")

        assert resp.status_code == 200
        refs = [item["ref"] for item in resp.data]
        assert planned.ref in refs
        assert started.ref in refs
        assert finished.ref not in refs

    def test_summary_returns_operational_totals(self, api_client, recipe):
        planned = craft.plan(recipe, 100, date="2026-02-27", position_ref="forno")
        started = craft.plan(recipe, 80, date="2026-02-27", position_ref="forno")
        craft.start(started, quantity=Decimal("75"), expected_rev=0, position_ref="forno")
        finished = craft.plan(recipe, 50, date="2026-02-27", position_ref="forno")
        craft.start(finished, quantity=Decimal("48"), expected_rev=0, position_ref="forno")
        craft.finish(finished, finished=Decimal("46"), expected_rev=1)
        voided = craft.plan(recipe, 20, date="2026-02-27", position_ref="forno")
        craft.void(voided, reason="sem demanda")

        resp = api_client.get("/api/craftsman/queries/summary/?date=2026-02-27&position_ref=forno")

        assert resp.status_code == 200
        assert resp.data["total_orders"] == 4
        assert resp.data["planned_orders"] == 1
        assert resp.data["started_orders"] == 1
        assert resp.data["finished_orders"] == 1
        assert resp.data["void_orders"] == 1
        assert resp.data["planned_qty"] == "250.000"
        assert resp.data["started_qty"] == "123.000"
        assert resp.data["finished_qty"] == "46.000"
        assert resp.data["loss_qty"] == "2.000"


class TestFloorExecutionEndpoints:
    def test_start_returns_200(self, api_client, recipe):
        wo = craft.plan(recipe, 100)
        resp = api_client.post(
            f"/api/craftsman/work-orders/{wo.ref}/start/",
            {
                "quantity": "92",
                "expected_rev": 0,
                "operator_ref": "user:joao",
                "position_ref": "station:forno-01",
                "note": "massa na bancada",
            },
            format="json",
        )
        assert resp.status_code == 200
        assert resp.data["status"] == "started"
        assert resp.data["operator_ref"] == "user:joao"
        assert resp.data["position_ref"] == "station:forno-01"
        assert resp.data["started_qty"] == "92.000"

    def test_retrieve_exposes_floor_projection(self, api_client, recipe):
        wo = craft.plan(recipe, 100)
        craft.start(wo, quantity=Decimal("92"), expected_rev=0)

        resp = api_client.get(f"/api/craftsman/work-orders/{wo.ref}/")
        assert resp.status_code == 200
        assert resp.data["planned_qty"] == "100.000"
        assert resp.data["started_qty"] == "92.000"
        assert resp.data["finished_qty"] is None


# ══════════════════════════════════════════════════════════════
# VOID ENDPOINT
# ══════════════════════════════════════════════════════════════


class TestVoidEndpoint:
    def test_void_returns_200(self, api_client, recipe):
        wo = craft.plan(recipe, 100)
        resp = api_client.post(
            f"/api/craftsman/work-orders/{wo.ref}/void/",
            {"reason": "cliente cancelou", "expected_rev": 0},
            format="json",
        )
        assert resp.status_code == 200
        assert resp.data["status"] == "void"

    def test_void_from_finished_returns_400(self, api_client, recipe):
        wo = craft.plan(recipe, 100)
        craft.finish(wo, finished=93, expected_rev=0)

        resp = api_client.post(
            f"/api/craftsman/work-orders/{wo.ref}/void/",
            {"reason": "teste", "expected_rev": 1},
            format="json",
        )
        assert resp.status_code == 400
        assert resp.data["error"] == "VOID_FROM_DONE"

    def test_void_stale_rev_returns_409(self, api_client, recipe):
        wo = craft.plan(recipe, 100)
        craft.adjust(wo, quantity=97)

        resp = api_client.post(
            f"/api/craftsman/work-orders/{wo.ref}/void/",
            {"reason": "cancelado", "expected_rev": 0},
            format="json",
        )
        assert resp.status_code == 409

    def test_void_missing_reason_returns_400(self, api_client, recipe):
        wo = craft.plan(recipe, 100)
        resp = api_client.post(
            f"/api/craftsman/work-orders/{wo.ref}/void/",
            {},
            format="json",
        )
        assert resp.status_code == 400
        assert "reason" in resp.data


# ══════════════════════════════════════════════════════════════
# READ ENDPOINTS
# ══════════════════════════════════════════════════════════════


class TestReadEndpoints:
    def test_list_work_orders(self, api_client, recipe):
        craft.plan(recipe, 100)
        craft.plan(recipe, 50)

        resp = api_client.get("/api/craftsman/work-orders/")
        assert resp.status_code == 200
        # Paginated response: {count, next, previous, results}
        assert resp.data["count"] == 2
        assert len(resp.data["results"]) == 2

    def test_retrieve_work_order(self, api_client, recipe):
        wo = craft.plan(recipe, 100)
        resp = api_client.get(f"/api/craftsman/work-orders/{wo.ref}/")
        assert resp.status_code == 200
        assert resp.data["ref"] == wo.ref
        assert resp.data["output_ref"] == "croissant"

    def test_list_recipes(self, api_client, recipe):
        resp = api_client.get("/api/craftsman/recipes/")
        assert resp.status_code == 200
        # Paginated response: {count, next, previous, results}
        assert resp.data["count"] == 1
        assert resp.data["results"][0]["code"] == "croissant-v1"

    def test_retrieve_recipe(self, api_client, recipe):
        resp = api_client.get(f"/api/craftsman/recipes/{recipe.code}/")
        assert resp.status_code == 200
        assert resp.data["name"] == "Croissant Tradicional"

    def test_list_work_orders_filters_by_operational_fields(self, api_client, recipe):
        from datetime import date

        wo1 = craft.plan(recipe, 100, date=date(2026, 2, 27), position_ref="forno", operator_ref="user:joao")
        craft.plan(recipe, 50, date=date(2026, 2, 28), position_ref="bancada", operator_ref="user:maria")

        resp = api_client.get(
            "/api/craftsman/work-orders/?target_date=2026-02-27&position_ref=forno&operator_ref=user:joao&status=planned"
        )
        assert resp.status_code == 200
        assert resp.data["count"] == 1
        assert resp.data["results"][0]["ref"] == wo1.ref

    def test_nonexistent_work_order_returns_404(self, api_client):
        resp = api_client.get("/api/craftsman/work-orders/WO-9999-99999/")
        assert resp.status_code == 404


class TestQueryEndpoints:
    def test_suggest_accepts_season_and_multiplier(self, api_client, recipe, settings, monkeypatch):
        from datetime import date
        from unittest.mock import MagicMock

        from shopman.craftsman.protocols.demand import DailyDemand

        settings.CRAFTSMAN = {"DEMAND_BACKEND": "shopman.craftsman.adapters.noop.NoopDemandBackend"}

        backend = MagicMock()
        backend.history.return_value = [
            DailyDemand(date=date(2026, 1, 10), sold=Decimal("10"), wasted=Decimal("0"), soldout_at=None),
            DailyDemand(date=date(2026, 2, 14), sold=Decimal("12"), wasted=Decimal("0"), soldout_at=None),
        ]
        backend.committed.return_value = Decimal("3")

        monkeypatch.setattr("django.utils.module_loading.import_string", lambda _: lambda: backend)

        resp = api_client.get(
            "/api/craftsman/queries/suggest/?date=2026-02-27&season_months=1,2,3&high_demand_multiplier=1.5"
        )
        assert resp.status_code == 200
        assert len(resp.data) == 1
        assert resp.data[0]["basis"]["season"] is None
        assert resp.data[0]["basis"]["high_demand_applied"] is True

    def test_suggest_rejects_invalid_season_months(self, api_client):
        resp = api_client.get("/api/craftsman/queries/suggest/?date=2026-02-27&season_months=jan,fev")
        assert resp.status_code == 400
        assert resp.data["error"] == "INVALID_SEASON_MONTHS"

    def test_suggest_rejects_invalid_multiplier(self, api_client):
        resp = api_client.get("/api/craftsman/queries/suggest/?date=2026-02-27&high_demand_multiplier=abc")
        assert resp.status_code == 400
        assert resp.data["error"] == "INVALID_MULTIPLIER"
