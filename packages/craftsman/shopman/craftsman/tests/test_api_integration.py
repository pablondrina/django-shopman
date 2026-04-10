"""
API integration tests — HTTP-level tests using DRF's APIClient.

Covers:
- Authentication enforcement (401 without auth)
- HTTP status codes: 200, 400, 409
- Serializer validation (consumed sub-serializer, required fields)
- URL routing via router
"""

import pytest
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APIClient

from shopman.craftsman import craft, CraftError, StaleRevision
from shopman.craftsman.models import Recipe, RecipeItem, WorkOrder


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
        resp = anon_client.get("/api/crafting/work-orders/")
        assert resp.status_code in (401, 403)

    def test_close_requires_auth(self, anon_client, recipe):
        wo = craft.plan(recipe, 100)
        resp = anon_client.post(f"/api/crafting/work-orders/{wo.ref}/close/", {})
        assert resp.status_code in (401, 403)

    def test_authenticated_can_list(self, api_client, recipe):
        craft.plan(recipe, 100)
        resp = api_client.get("/api/crafting/work-orders/")
        assert resp.status_code == 200


# ══════════════════════════════════════════════════════════════
# CLOSE ENDPOINT
# ══════════════════════════════════════════════════════════════


class TestCloseEndpoint:
    def test_close_returns_200(self, api_client, recipe_with_items):
        wo = craft.plan(recipe_with_items, 100)
        resp = api_client.post(
            f"/api/crafting/work-orders/{wo.ref}/close/",
            {"produced": "93", "expected_rev": 0},
            format="json",
        )
        assert resp.status_code == 200
        assert resp.data["status"] == "done"
        assert resp.data["produced"] == "93.000"

    def test_close_terminal_returns_400(self, api_client, recipe):
        wo = craft.plan(recipe, 100)
        craft.close(wo, produced=93, expected_rev=0)

        resp = api_client.post(
            f"/api/crafting/work-orders/{wo.ref}/close/",
            {"produced": "50", "expected_rev": 1},
            format="json",
        )
        assert resp.status_code == 400
        assert resp.data["error"] == "TERMINAL_STATUS"

    def test_close_stale_rev_returns_409(self, api_client, recipe_with_items):
        wo = craft.plan(recipe_with_items, 100)
        craft.adjust(wo, quantity=97)  # rev now 1

        resp = api_client.post(
            f"/api/crafting/work-orders/{wo.ref}/close/",
            {"produced": "93", "expected_rev": 0},
            format="json",
        )
        assert resp.status_code == 409
        assert resp.data["error"] == "STALE_REVISION"

    def test_close_missing_produced_returns_400(self, api_client, recipe):
        wo = craft.plan(recipe, 100)
        resp = api_client.post(
            f"/api/crafting/work-orders/{wo.ref}/close/",
            {},
            format="json",
        )
        assert resp.status_code == 400
        assert "produced" in resp.data

    def test_close_with_valid_consumed(self, api_client, recipe_with_items):
        wo = craft.plan(recipe_with_items, 100)
        resp = api_client.post(
            f"/api/crafting/work-orders/{wo.ref}/close/",
            {
                "produced": "93",
                "expected_rev": 0,
                "consumed": [
                    {"item_ref": "farinha", "quantity": "48.5", "unit": "kg"},
                    {"item_ref": "agua", "quantity": "29", "unit": "L"},
                ],
            },
            format="json",
        )
        assert resp.status_code == 200

    def test_close_consumed_missing_item_ref_returns_400(self, api_client, recipe_with_items):
        wo = craft.plan(recipe_with_items, 100)
        resp = api_client.post(
            f"/api/crafting/work-orders/{wo.ref}/close/",
            {
                "produced": "93",
                "consumed": [
                    {"quantity": "48.5"},  # missing item_ref
                ],
            },
            format="json",
        )
        assert resp.status_code == 400

    def test_close_consumed_missing_quantity_returns_400(self, api_client, recipe_with_items):
        wo = craft.plan(recipe_with_items, 100)
        resp = api_client.post(
            f"/api/crafting/work-orders/{wo.ref}/close/",
            {
                "produced": "93",
                "consumed": [
                    {"item_ref": "farinha"},  # missing quantity
                ],
            },
            format="json",
        )
        assert resp.status_code == 400

    def test_close_with_idempotency(self, api_client, recipe_with_items):
        wo = craft.plan(recipe_with_items, 100)
        payload = {
            "produced": "93",
            "expected_rev": 0,
            "idempotency_key": "close-http-001",
        }
        resp1 = api_client.post(
            f"/api/crafting/work-orders/{wo.ref}/close/", payload, format="json",
        )
        assert resp1.status_code == 200

        resp2 = api_client.post(
            f"/api/crafting/work-orders/{wo.ref}/close/",
            {"produced": "50", "idempotency_key": "close-http-001"},
            format="json",
        )
        assert resp2.status_code == 200
        assert resp2.data["produced"] == "93.000"  # original preserved


# ══════════════════════════════════════════════════════════════
# ADJUST ENDPOINT
# ══════════════════════════════════════════════════════════════


class TestAdjustEndpoint:
    def test_adjust_returns_200(self, api_client, recipe):
        wo = craft.plan(recipe, 100)
        resp = api_client.post(
            f"/api/crafting/work-orders/{wo.ref}/adjust/",
            {"quantity": "97", "reason": "farinha insuficiente", "expected_rev": 0},
            format="json",
        )
        assert resp.status_code == 200
        assert resp.data["quantity"] == "97.000"

    def test_adjust_stale_rev_returns_409(self, api_client, recipe):
        wo = craft.plan(recipe, 100)
        craft.adjust(wo, quantity=97)  # rev now 1

        resp = api_client.post(
            f"/api/crafting/work-orders/{wo.ref}/adjust/",
            {"quantity": "95", "expected_rev": 0},
            format="json",
        )
        assert resp.status_code == 409

    def test_adjust_terminal_returns_400(self, api_client, recipe):
        wo = craft.plan(recipe, 100)
        craft.close(wo, produced=93, expected_rev=0)

        resp = api_client.post(
            f"/api/crafting/work-orders/{wo.ref}/adjust/",
            {"quantity": "50"},
            format="json",
        )
        assert resp.status_code == 400
        assert resp.data["error"] == "TERMINAL_STATUS"

    def test_adjust_missing_quantity_returns_400(self, api_client, recipe):
        wo = craft.plan(recipe, 100)
        resp = api_client.post(
            f"/api/crafting/work-orders/{wo.ref}/adjust/",
            {},
            format="json",
        )
        assert resp.status_code == 400
        assert "quantity" in resp.data


# ══════════════════════════════════════════════════════════════
# VOID ENDPOINT
# ══════════════════════════════════════════════════════════════


class TestVoidEndpoint:
    def test_void_returns_200(self, api_client, recipe):
        wo = craft.plan(recipe, 100)
        resp = api_client.post(
            f"/api/crafting/work-orders/{wo.ref}/void/",
            {"reason": "cliente cancelou", "expected_rev": 0},
            format="json",
        )
        assert resp.status_code == 200
        assert resp.data["status"] == "void"

    def test_void_from_done_returns_400(self, api_client, recipe):
        wo = craft.plan(recipe, 100)
        craft.close(wo, produced=93, expected_rev=0)

        resp = api_client.post(
            f"/api/crafting/work-orders/{wo.ref}/void/",
            {"reason": "teste", "expected_rev": 1},
            format="json",
        )
        assert resp.status_code == 400
        assert resp.data["error"] == "VOID_FROM_DONE"

    def test_void_stale_rev_returns_409(self, api_client, recipe):
        wo = craft.plan(recipe, 100)
        craft.adjust(wo, quantity=97)

        resp = api_client.post(
            f"/api/crafting/work-orders/{wo.ref}/void/",
            {"reason": "cancelado", "expected_rev": 0},
            format="json",
        )
        assert resp.status_code == 409

    def test_void_missing_reason_returns_400(self, api_client, recipe):
        wo = craft.plan(recipe, 100)
        resp = api_client.post(
            f"/api/crafting/work-orders/{wo.ref}/void/",
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

        resp = api_client.get("/api/crafting/work-orders/")
        assert resp.status_code == 200
        # Paginated response: {count, next, previous, results}
        assert resp.data["count"] == 2
        assert len(resp.data["results"]) == 2

    def test_retrieve_work_order(self, api_client, recipe):
        wo = craft.plan(recipe, 100)
        resp = api_client.get(f"/api/crafting/work-orders/{wo.ref}/")
        assert resp.status_code == 200
        assert resp.data["ref"] == wo.ref
        assert resp.data["output_ref"] == "croissant"

    def test_list_recipes(self, api_client, recipe):
        resp = api_client.get("/api/crafting/recipes/")
        assert resp.status_code == 200
        # Paginated response: {count, next, previous, results}
        assert resp.data["count"] == 1
        assert resp.data["results"][0]["code"] == "croissant-v1"

    def test_retrieve_recipe(self, api_client, recipe):
        resp = api_client.get(f"/api/crafting/recipes/{recipe.code}/")
        assert resp.status_code == 200
        assert resp.data["name"] == "Croissant Tradicional"

    def test_nonexistent_work_order_returns_404(self, api_client):
        resp = api_client.get("/api/crafting/work-orders/WO-9999-99999/")
        assert resp.status_code == 404
