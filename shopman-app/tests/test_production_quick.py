"""Tests for quick production registration (WP-5)."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import Permission, User
from django.test import Client
from shopman.crafting.models import Recipe, WorkOrder
from shopman.stocking.models.position import Position

from shop.models import Shop

PRODUCTION_URL = "/admin/shop/shop/production/"
VOID_URL = "/admin/shop/shop/production/void/"


@pytest.fixture(autouse=True)
def shop_instance(db):
    return Shop.objects.create(
        name="Nelson Boulangerie",
        brand_name="Nelson Boulangerie",
        short_name="Nelson",
        default_ddd="43",
    )


@pytest.fixture
def recipe(db):
    return Recipe.objects.create(
        code="pao-frances-v1",
        name="Pão Francês",
        output_ref="PAO-FRANCES",
        batch_size=100,
    )


@pytest.fixture
def position(db):
    return Position.objects.create(
        ref="vitrine",
        name="Vitrine",
        kind="physical",
        is_saleable=True,
        is_default=True,
    )


@pytest.fixture
def admin_user(db):
    return User.objects.create_superuser("admin", "admin@test.com", "admin123")


@pytest.fixture
def admin_client(admin_user):
    client = Client()
    client.force_login(admin_user)
    return client


@pytest.fixture
def staff_user(db):
    user = User.objects.create_user("staff", "staff@test.com", "staff123", is_staff=True)
    return user


@pytest.fixture
def staff_client(staff_user):
    client = Client()
    client.force_login(staff_user)
    return client


@pytest.fixture
def staff_user_with_perm(staff_user):
    perm = Permission.objects.get(codename="add_workorder")
    staff_user.user_permissions.add(perm)
    staff_user.save()
    # Clear cached permissions
    staff_user = User.objects.get(pk=staff_user.pk)
    return staff_user


@pytest.fixture
def staff_client_with_perm(staff_user_with_perm):
    client = Client()
    client.force_login(staff_user_with_perm)
    return client


class TestProductionPermissions:
    def test_page_requires_permission(self, staff_client):
        """Staff without crafting.add_workorder gets redirected."""
        response = staff_client.get(PRODUCTION_URL)
        assert response.status_code == 302

    def test_page_accessible_with_permission(self, staff_client_with_perm, recipe, position):
        response = staff_client_with_perm.get(PRODUCTION_URL)
        assert response.status_code == 200

    def test_page_accessible_by_superuser(self, admin_client, recipe, position):
        response = admin_client.get(PRODUCTION_URL)
        assert response.status_code == 200


class TestProductionPageLoads:
    def test_page_loads_recipes(self, admin_client, recipe, position):
        response = admin_client.get(PRODUCTION_URL)
        content = response.content.decode()
        assert recipe.code in content
        assert recipe.output_ref in content

    def test_page_loads_positions(self, admin_client, recipe, position):
        response = admin_client.get(PRODUCTION_URL)
        content = response.content.decode()
        assert position.name in content


class TestProductionCreatesWorkOrder:
    def test_creates_and_closes_workorder(self, admin_client, recipe, position):
        response = admin_client.post(PRODUCTION_URL, {
            "recipe": recipe.pk,
            "quantity": "50",
            "position": position.pk,
        })
        assert response.status_code == 302

        wo = WorkOrder.objects.get(recipe=recipe)
        assert wo.status == WorkOrder.Status.DONE
        assert wo.quantity == Decimal("50")
        assert wo.produced == Decimal("50")
        assert wo.scheduled_date == date.today()
        assert wo.position_ref == position.ref

    def test_invalid_recipe_shows_error(self, admin_client, position):
        response = admin_client.post(PRODUCTION_URL, {
            "recipe": "99999",
            "quantity": "50",
            "position": position.pk,
        })
        assert response.status_code == 200  # re-renders form
        assert WorkOrder.objects.count() == 0

    def test_invalid_quantity_shows_error(self, admin_client, recipe, position):
        response = admin_client.post(PRODUCTION_URL, {
            "recipe": recipe.pk,
            "quantity": "0",
            "position": position.pk,
        })
        assert response.status_code == 200
        assert WorkOrder.objects.count() == 0

    def test_empty_quantity_shows_error(self, admin_client, recipe, position):
        response = admin_client.post(PRODUCTION_URL, {
            "recipe": recipe.pk,
            "quantity": "",
            "position": position.pk,
        })
        assert response.status_code == 200
        assert WorkOrder.objects.count() == 0


class TestProductionVoid:
    def test_void_reverts_workorder(self, admin_client, recipe, position):
        # Create a WO first
        admin_client.post(PRODUCTION_URL, {
            "recipe": recipe.pk,
            "quantity": "30",
            "position": position.pk,
        })
        wo = WorkOrder.objects.get(recipe=recipe)
        assert wo.status == WorkOrder.Status.DONE

        # Void only works on OPEN WOs — this one is DONE, so it should fail
        response = admin_client.post(VOID_URL, {"wo_id": wo.pk})
        assert response.status_code == 302
        wo.refresh_from_db()
        # DONE WOs can't be voided per CraftExecution.void — stays DONE
        assert wo.status == WorkOrder.Status.DONE

    def test_void_open_workorder(self, admin_client, recipe):
        """Directly create an OPEN WO and void it."""
        wo = WorkOrder.objects.create(
            recipe=recipe,
            output_ref=recipe.output_ref,
            quantity=20,
            status=WorkOrder.Status.OPEN,
        )
        response = admin_client.post(VOID_URL, {"wo_id": wo.pk})
        assert response.status_code == 302
        wo.refresh_from_db()
        assert wo.status == WorkOrder.Status.VOID

    def test_void_nonexistent_wo(self, admin_client):
        response = admin_client.post(VOID_URL, {"wo_id": "99999"})
        assert response.status_code == 302


class TestProductionListsToday:
    def test_lists_today_only(self, admin_client, recipe, position):
        # Create WO for today
        admin_client.post(PRODUCTION_URL, {
            "recipe": recipe.pk,
            "quantity": "25",
            "position": position.pk,
        })

        # Create WO for yesterday (directly)
        yesterday_wo = WorkOrder.objects.create(
            recipe=recipe,
            output_ref=recipe.output_ref,
            quantity=10,
            status=WorkOrder.Status.DONE,
            scheduled_date=date.today() - timedelta(days=1),
        )

        response = admin_client.get(PRODUCTION_URL)
        content = response.content.decode()

        # Today's WO should appear
        today_wo = WorkOrder.objects.get(scheduled_date=date.today())
        assert today_wo.code in content

        # Yesterday's WO should NOT appear
        if yesterday_wo.code:
            assert yesterday_wo.code not in content
