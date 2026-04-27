"""Tests for shopman.admin — admin registration, extensions, and dashboard."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.contrib import admin
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.test import Client, RequestFactory
from django.urls import reverse
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe, RecipeItem

from shopman.backstage.models import DayClosing, KDSInstance, OperatorAlert
from shopman.shop.models import (
    RuleConfig,
    Shop,
)

# ── Helpers ──────────────────────────────────────────────────────────


@pytest.fixture
def admin_user(db):
    return User.objects.create_superuser("admin", "admin@test.com", "pass")


@pytest.fixture
def rf():
    return RequestFactory()


@pytest.fixture
def shop(db):
    return Shop.objects.create(
        name="Test Shop",
        brand_name="Test",
        short_name="TS",
        primary_color="#C5A55A",
        default_ddd="43",
    )


def _shop_permission(codename: str) -> Permission:
    ct = ContentType.objects.get(app_label="shop", model="shop")
    return Permission.objects.get(content_type=ct, codename=codename)


# ── Registration tests ──────────────────────────────────────────────


class TestAdminRegistration:
    """All shopman models are registered in the admin."""

    def test_shop_registered(self, db):
        assert Shop in admin.site._registry

    def test_operator_alert_registered(self, db):
        assert OperatorAlert in admin.site._registry

    def test_kds_instance_registered(self, db):
        assert KDSInstance in admin.site._registry

    def test_day_closing_registered(self, db):
        assert DayClosing in admin.site._registry

    def test_rule_config_registered(self, db):
        assert RuleConfig in admin.site._registry


# ── Shop singleton behavior ─────────────────────────────────────────


class TestShopAdminStorefrontPreview:
    """WP-S4 — iframe preview no change do Shop."""

    def test_readonly_fields_include_storefront_preview(self, db):
        shop_admin = admin.site._registry[Shop]
        assert "storefront_preview" in (shop_admin.readonly_fields or ())

    def test_change_page_contains_preview_iframe(self, db, admin_user, shop):
        client = Client()
        client.force_login(admin_user)
        url = reverse("admin:shop_shop_change", args=[shop.pk])
        resp = client.get(url)
        assert resp.status_code == 200
        assert b"storefront-preview-iframe" in resp.content
        assert b"Atualizar preview" in resp.content


class TestShopAdminSingleton:
    def test_has_add_permission_when_empty(self, db, rf, admin_user):
        shop_admin = admin.site._registry[Shop]
        request = rf.get("/admin/shopman/shop/")
        request.user = admin_user
        assert shop_admin.has_add_permission(request) is True

    def test_has_add_permission_when_exists(self, shop, rf, admin_user):
        shop_admin = admin.site._registry[Shop]
        request = rf.get("/admin/shopman/shop/")
        request.user = admin_user
        assert shop_admin.has_add_permission(request) is False

    def test_has_delete_permission_always_false(self, shop, rf, admin_user):
        shop_admin = admin.site._registry[Shop]
        request = rf.get("/admin/shopman/shop/")
        request.user = admin_user
        assert shop_admin.has_delete_permission(request) is False
        assert shop_admin.has_delete_permission(request, obj=shop) is False


# ── DayClosing readonly behavior ────────────────────────────────────


class TestDayClosingAdmin:
    def test_no_change_permission(self, db, rf, admin_user):
        closing_admin = admin.site._registry[DayClosing]
        request = rf.get("/admin/shopman/dayclosing/")
        request.user = admin_user
        assert closing_admin.has_change_permission(request) is False

    def test_no_delete_permission(self, db, rf, admin_user):
        closing_admin = admin.site._registry[DayClosing]
        request = rf.get("/admin/shopman/dayclosing/")
        request.user = admin_user
        assert closing_admin.has_delete_permission(request) is False


# ── OperatorAlert admin ─────────────────────────────────────────────


class TestOperatorAlertAdmin:
    def test_list_display_fields(self, db):
        alert_admin = admin.site._registry[OperatorAlert]
        assert "type" in alert_admin.list_display
        assert "severity" in alert_admin.list_display
        assert "acknowledged" in alert_admin.list_display

    def test_mark_acknowledged_action(self, db):
        alert_admin = admin.site._registry[OperatorAlert]
        action_names = [a.__name__ if callable(a) else a for a in alert_admin.actions]
        assert "mark_acknowledged" in action_names


# ── Order admin extensions ──────────────────────────────────────────


class TestOrderAdminExtensions:
    def test_order_has_fulfillment_inline(self, db):
        from shopman.orderman.models import Order

        from shopman.shop.admin.orders import FulfillmentOrderInline

        if Order not in admin.site._registry:
            pytest.skip("Order not registered in admin")

        order_admin_cls = type(admin.site._registry[Order])
        assert FulfillmentOrderInline in (order_admin_cls.inlines or [])

    def test_order_has_payment_info(self, db):
        from shopman.orderman.models import Order

        if Order not in admin.site._registry:
            pytest.skip("Order not registered in admin")

        order_admin_cls = type(admin.site._registry[Order])
        assert "payment_info" in (order_admin_cls.readonly_fields or ())


class TestProductAdminExtension:
    def test_product_has_allows_next_day_sale(self, db):
        from shopman.offerman.models import Product

        if Product not in admin.site._registry:
            pytest.skip("Product not registered in admin")

        product_admin_cls = type(admin.site._registry[Product])
        fieldsets = product_admin_cls.fieldsets or []
        for title, opts in fieldsets:
            if title == "Configuration":
                assert "allows_next_day_sale" in opts["fields"]
                return
        pytest.skip("Configuration fieldset not found")


class TestBatchAdminExtension:
    def test_batch_has_supplier_filter(self, db):
        from shopman.stockman.models import Batch

        from shopman.shop.admin.orders import SupplierFilter

        if Batch not in admin.site._registry:
            pytest.skip("Batch not registered in admin")

        batch_admin_cls = type(admin.site._registry[Batch])
        assert SupplierFilter in (batch_admin_cls.list_filter or [])

    def test_batch_has_expiry_filter(self, db):
        from shopman.stockman.models import Batch

        from shopman.shop.admin.orders import ExpiryStatusFilter

        if Batch not in admin.site._registry:
            pytest.skip("Batch not registered in admin")

        batch_admin_cls = type(admin.site._registry[Batch])
        assert ExpiryStatusFilter in (batch_admin_cls.list_filter or [])


# ── Dashboard callback ──────────────────────────────────────────────


class TestDashboardCallback:
    def test_returns_context_with_kpis(self, db):
        from shopman.backstage.admin.dashboard import dashboard_callback

        request = RequestFactory().get("/admin/")
        context = {}
        result = dashboard_callback(request, context)

        assert "order_summary" in result
        assert "revenue" in result
        assert "production" in result
        assert "kpi_stock_alerts" in result
        assert "chart_pedidos_status" in result
        assert "chart_vendas_7dias" in result
        assert "table_pedidos_pendentes" in result
        assert "recent_orders" in result
        assert "operator_alerts" in result

    def test_order_summary_structure(self, db):
        from shopman.backstage.admin.dashboard import dashboard_callback

        request = RequestFactory().get("/admin/")
        context = {}
        result = dashboard_callback(request, context)

        summary = result["order_summary"]
        assert hasattr(summary, "total")
        assert hasattr(summary, "new_count")
        assert hasattr(summary, "cards")

    def test_revenue_structure(self, db):
        from shopman.backstage.admin.dashboard import dashboard_callback

        request = RequestFactory().get("/admin/")
        context = {}
        result = dashboard_callback(request, context)

        revenue = result["revenue"]
        assert hasattr(revenue, "today_q")
        assert hasattr(revenue, "today_display")
        assert hasattr(revenue, "yesterday_q")
        assert hasattr(revenue, "trend_up")

    def test_format_brl(self):
        from shopman.backstage.projections.dashboard import _format_brl

        assert _format_brl(0) == "R$ 0,00"
        assert _format_brl(1500) == "R$ 15,00"
        assert _format_brl(150000) == "R$ 1.500,00"
        assert _format_brl(None) == "R$ 0,00"


class TestProductionAdminView:
    def test_get_exposes_operational_summary_and_queue(self, db, rf, admin_user):
        from datetime import date

        from shopman.backstage.views.production import production_view

        recipe = Recipe.objects.create(
            ref="croissant-v1",
            name="Croissant Tradicional",
            output_sku="croissant",
            batch_size=10,
        )
        base = Recipe.objects.create(
            ref="massa-folhada",
            name="Massa Folhada",
            output_sku="MASSA-FOLHADA",
            batch_size=10,
        )
        RecipeItem.objects.create(recipe=recipe, input_sku=base.output_sku, quantity=3, unit="kg")
        craft.plan(recipe, 100, date=date.today(), position_ref="forno")
        started = craft.plan(recipe, 80, date=date.today(), position_ref="forno", operator_ref="user:joao")
        craft.start(started, quantity=75, expected_rev=0, position_ref="forno", operator_ref="user:joao")

        request = rf.get("/admin/shopman/shop/production/")
        request.user = admin_user
        response = production_view(request, admin.site)

        assert response.status_code == 200
        assert response.context_data["craft_summary"].total == 2
        assert len(response.context_data["planned_queue"]) == 1
        assert len(response.context_data["started_queue"]) == 1
        assert len(response.context_data["matrix_rows"]) == 1
        assert response.context_data["matrix_rows"][0].planned_qty == "100"
        assert response.context_data["matrix_rows"][0].started_qty == "75"
        assert response.context_data["matrix_groups"][0].name == "Massa Folhada"
        assert response.context_data["base_recipes"][0].output_sku == "MASSA-FOLHADA"

    def test_get_filters_by_date_position_and_operator(self, db, rf, admin_user):
        from datetime import date, timedelta

        from shopman.backstage.views.production import production_view

        recipe = Recipe.objects.create(
            ref="baguette-v1",
            name="Baguette",
            output_sku="baguette",
            batch_size=10,
        )
        target = date.today() + timedelta(days=1)
        craft.plan(recipe, 100, date=target, position_ref="forno", operator_ref="user:joao")
        craft.plan(recipe, 50, date=target, position_ref="bancada", operator_ref="user:maria")

        request = rf.get(
            "/admin/shopman/shop/production/",
            {"date": target.isoformat(), "position_ref": "forno", "operator_ref": "user:joao"},
        )
        request.user = admin_user
        response = production_view(request, admin.site)

        assert response.status_code == 200
        assert response.context_data["selected_date"] == target
        assert response.context_data["craft_summary"].total == 1
        assert len(response.context_data["planned_queue"]) == 1
        assert len(response.context_data["today_wos"]) == 1

    def test_get_filters_matrix_by_base_recipe(self, db, rf, admin_user):
        from datetime import date

        from shopman.backstage.views.production import production_view

        levain_base = Recipe.objects.create(
            ref="massa-levain",
            name="Massa Levain",
            output_sku="MASSA-LEVAIN",
            batch_size=10,
        )
        folhada_base = Recipe.objects.create(
            ref="massa-folhada",
            name="Massa Folhada",
            output_sku="MASSA-FOLHADA",
            batch_size=10,
        )
        levain = Recipe.objects.create(
            ref="levain-a",
            name="Levain A",
            output_sku="LEVAIN-A",
            batch_size=10,
        )
        folhado = Recipe.objects.create(
            ref="folhado-a",
            name="Folhado A",
            output_sku="FOLHADO-A",
            batch_size=10,
        )
        RecipeItem.objects.create(recipe=levain, input_sku=levain_base.output_sku, quantity=2, unit="kg")
        RecipeItem.objects.create(recipe=folhado, input_sku=folhada_base.output_sku, quantity=3, unit="kg")
        craft.plan(levain, 12, date=date.today(), position_ref="forno")
        craft.plan(folhado, 24, date=date.today(), position_ref="forno")

        request = rf.get("/admin/shopman/shop/production/", {"base_recipe": "MASSA-FOLHADA"})
        request.user = admin_user
        response = production_view(request, admin.site)

        assert response.status_code == 200
        assert response.context_data["selected_base_recipe"] == "MASSA-FOLHADA"
        assert [row.output_sku for row in response.context_data["matrix_rows"]] == ["FOLHADO-A"]
        assert {base.output_sku for base in response.context_data["base_recipes"]} == {
            "MASSA-FOLHADA",
            "MASSA-LEVAIN",
        }
        assert response.context_data["matrix_groups"][0].rows[0].usage.quantity_display == "3 kg"

    def test_get_allows_finished_column_only_operator(self, db, rf):
        from datetime import date

        from shopman.backstage.views.production import production_view

        user = User.objects.create_user("finished-op", password="pass", is_staff=True)
        user.user_permissions.add(_shop_permission("view_production_finished"))

        recipe = Recipe.objects.create(
            ref="pain-au-chocolat-v1",
            name="Pain au Chocolat",
            output_sku="PAIN-AU-CHOCOLAT",
            batch_size=10,
        )
        planned = craft.plan(recipe, 30, date=date.today(), position_ref="forno")
        finished = craft.plan(recipe, 20, date=date.today(), position_ref="forno")
        craft.finish(finished, finished=18, actor="test")

        request = rf.get("/admin/shopman/shop/production/")
        request.user = user
        response = production_view(request, admin.site)

        assert response.status_code == 200
        assert response.context_data["production_access"].can_view_finished is True
        assert response.context_data["production_access"].can_view_planned is False
        assert len(response.context_data["planned_queue"]) == 0
        assert len(response.context_data["finished_queue"]) == 1
        assert response.context_data["today_wos"][0].ref == finished.ref
        assert planned.ref not in [wo.ref for wo in response.context_data["today_wos"]]

    def test_post_requires_finished_edit_column(self, db, rf):
        from shopman.backstage.views.production import production_view

        user = User.objects.create_user("finished-viewer", password="pass", is_staff=True)
        user.user_permissions.add(_shop_permission("view_production_finished"))

        request = rf.post("/admin/shopman/shop/production/", {"recipe": "1", "quantity": "1"})
        request.user = user
        with patch("shopman.backstage.views.production.messages"):
            response = production_view(request, admin.site)

        assert response.status_code == 302

    def test_post_can_set_planned_start_and_finish_canonical_lifecycle(self, db, rf, admin_user):
        from datetime import date

        from shopman.backstage.views.production import production_view
        from shopman.craftsman.models import WorkOrder

        recipe = Recipe.objects.create(
            ref="rustico-v1",
            name="Italiano Rústico",
            output_sku="ITALIANO-RUSTICO",
            batch_size=10,
        )

        plan_request = rf.post(
            "/admin/shopman/shop/production/",
            {
                "action": "set_planned",
                "recipe": str(recipe.pk),
                "quantity": "12",
                "target_date": date.today().isoformat(),
                "operator_ref": "user:ana",
            },
        )
        plan_request.user = admin_user
        with patch("shopman.backstage.views.production.messages"):
            response = production_view(plan_request, admin.site)

        assert response.status_code == 302
        work_order = WorkOrder.objects.get(output_sku="ITALIANO-RUSTICO")
        assert work_order.status == WorkOrder.Status.PLANNED
        assert work_order.operator_ref == "user:ana"

        adjust_request = rf.post(
            "/admin/shopman/shop/production/",
            {
                "action": "set_planned",
                "recipe": str(recipe.pk),
                "quantity": "14",
                "target_date": date.today().isoformat(),
                "operator_ref": "user:ana",
            },
        )
        adjust_request.user = admin_user
        with patch("shopman.backstage.views.production.messages"):
            response = production_view(adjust_request, admin.site)

        assert response.status_code == 302
        assert WorkOrder.objects.filter(output_sku="ITALIANO-RUSTICO").count() == 1
        work_order.refresh_from_db()
        assert work_order.quantity == 14

        start_request = rf.post(
            "/admin/shopman/shop/production/",
            {
                "action": "start",
                "wo_id": str(work_order.pk),
                "quantity": "11",
                "target_date": date.today().isoformat(),
                "operator_ref": "user:bia",
            },
        )
        start_request.user = admin_user
        with patch("shopman.backstage.views.production.messages"):
            response = production_view(start_request, admin.site)

        assert response.status_code == 302
        work_order.refresh_from_db()
        assert work_order.status == WorkOrder.Status.STARTED
        assert work_order.started_qty == 11
        assert work_order.operator_ref == "user:bia"

        finish_request = rf.post(
            "/admin/shopman/shop/production/",
            {
                "action": "finish",
                "wo_id": str(work_order.pk),
                "quantity": "10",
                "target_date": date.today().isoformat(),
            },
        )
        finish_request.user = admin_user
        with patch("shopman.backstage.views.production.messages"):
            response = production_view(finish_request, admin.site)

        assert response.status_code == 302
        work_order.refresh_from_db()
        assert work_order.status == WorkOrder.Status.FINISHED
        assert work_order.finished == 10
        assert work_order.loss == 1

    def test_post_can_clear_planned_quantity_from_matrix(self, db, rf, admin_user):
        from datetime import date

        from shopman.backstage.views.production import production_view
        from shopman.craftsman.models import WorkOrder

        recipe = Recipe.objects.create(
            ref="focaccia-v1",
            name="Focaccia",
            output_sku="FOCACCIA",
            batch_size=10,
        )

        for quantity in ("8", "0"):
            request = rf.post(
                "/admin/shopman/shop/production/",
                {
                    "action": "set_planned",
                    "recipe": str(recipe.pk),
                    "quantity": quantity,
                    "target_date": date.today().isoformat(),
                },
            )
            request.user = admin_user
            with patch("shopman.backstage.views.production.messages"):
                response = production_view(request, admin.site)
            assert response.status_code == 302

        work_order = WorkOrder.objects.get(output_sku="FOCACCIA")
        assert work_order.status == WorkOrder.Status.VOID

    def test_suggested_editor_can_turn_suggestion_into_plan(self, db, rf):
        from datetime import date

        from shopman.backstage.views.production import production_view
        from shopman.craftsman.models import WorkOrder

        user = User.objects.create_user("suggestion-op", password="pass", is_staff=True)
        user.user_permissions.add(_shop_permission("edit_production_suggested"))
        recipe = Recipe.objects.create(
            ref="bagel-v1",
            name="Bagel",
            output_sku="BAGEL",
            batch_size=10,
        )

        request = rf.post(
            "/admin/shopman/shop/production/",
            {
                "action": "set_planned",
                "source": "suggested",
                "recipe": str(recipe.pk),
                "quantity": "9",
                "target_date": date.today().isoformat(),
            },
        )
        request.user = user
        with patch("shopman.backstage.views.production.messages"):
            response = production_view(request, admin.site)

        assert response.status_code == 302
        assert WorkOrder.objects.get(output_sku="BAGEL").quantity == 9
