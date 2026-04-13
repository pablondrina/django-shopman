"""Tests for shopman.admin — admin registration, extensions, and dashboard."""

from __future__ import annotations

import pytest
from django.contrib import admin
from django.contrib.auth.models import User
from django.test import Client, RequestFactory
from django.urls import reverse

from shopman.craftsman import craft
from shopman.craftsman.models import Recipe
from shopman.models import (
    DayClosing,
    KDSInstance,
    OperatorAlert,
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
        url = reverse("admin:shopman_shop_change", args=[shop.pk])
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
        from shopman.admin.orders import FulfillmentOrderInline
        from shopman.orderman.models import Order

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
        from shopman.admin.orders import SupplierFilter
        from shopman.stockman.models import Batch

        if Batch not in admin.site._registry:
            pytest.skip("Batch not registered in admin")

        batch_admin_cls = type(admin.site._registry[Batch])
        assert SupplierFilter in (batch_admin_cls.list_filter or [])

    def test_batch_has_expiry_filter(self, db):
        from shopman.admin.orders import ExpiryStatusFilter
        from shopman.stockman.models import Batch

        if Batch not in admin.site._registry:
            pytest.skip("Batch not registered in admin")

        batch_admin_cls = type(admin.site._registry[Batch])
        assert ExpiryStatusFilter in (batch_admin_cls.list_filter or [])


# ── Dashboard callback ──────────────────────────────────────────────


class TestDashboardCallback:
    def test_returns_context_with_kpis(self, db):
        from shopman.admin.dashboard import dashboard_callback

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
        from shopman.admin.dashboard import dashboard_callback

        request = RequestFactory().get("/admin/")
        context = {}
        result = dashboard_callback(request, context)

        summary = result["order_summary"]
        assert "total" in summary
        assert "new_count" in summary
        assert "cards" in summary

    def test_revenue_structure(self, db):
        from shopman.admin.dashboard import dashboard_callback

        request = RequestFactory().get("/admin/")
        context = {}
        result = dashboard_callback(request, context)

        revenue = result["revenue"]
        assert "today_q" in revenue
        assert "today_display" in revenue
        assert "yesterday_q" in revenue
        assert "trend_up" in revenue

    def test_format_brl(self):
        from shopman.admin.dashboard import _format_brl

        assert _format_brl(0) == "R$ 0,00"
        assert _format_brl(1500) == "R$ 15,00"
        assert _format_brl(150000) == "R$ 1.500,00"
        assert _format_brl(None) == "R$ 0,00"


class TestProductionAdminView:
    def test_get_exposes_operational_summary_and_queue(self, db, rf, admin_user):
        from datetime import date

        from shopman.web.views.production import production_view

        recipe = Recipe.objects.create(
            code="croissant-v1",
            name="Croissant Tradicional",
            output_ref="croissant",
            batch_size=10,
        )
        craft.plan(recipe, 100, date=date.today(), position_ref="forno")
        started = craft.plan(recipe, 80, date=date.today(), position_ref="forno", operator_ref="user:joao")
        craft.start(started, quantity=75, expected_rev=0, position_ref="forno", operator_ref="user:joao")

        request = rf.get("/admin/shopman/shop/production/")
        request.user = admin_user
        response = production_view(request, admin.site)

        assert response.status_code == 200
        assert response.context_data["craft_summary"].total_orders == 2
        assert len(response.context_data["planned_queue"]) == 1
        assert len(response.context_data["started_queue"]) == 1

    def test_get_filters_by_date_position_and_operator(self, db, rf, admin_user):
        from datetime import date, timedelta

        from shopman.web.views.production import production_view

        recipe = Recipe.objects.create(
            code="baguette-v1",
            name="Baguette",
            output_ref="baguette",
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
        assert response.context_data["craft_summary"].total_orders == 1
        assert len(response.context_data["planned_queue"]) == 1
        assert response.context_data["today_wos"].count() == 1
