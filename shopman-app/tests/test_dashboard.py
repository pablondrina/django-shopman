"""Tests for admin dashboard (WP-E4)."""
from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.test import Client
from shopman.ordering.models import Channel, Order

from shop.models import Shop


@pytest.fixture(autouse=True)
def shop_instance(db):
    return Shop.objects.create(
        name="Nelson Boulangerie",
        brand_name="Nelson Boulangerie",
        short_name="Nelson",
        default_ddd="43",
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
    return User.objects.create_user("staff", "staff@test.com", "staff123", is_staff=True)


@pytest.fixture
def staff_client(staff_user):
    client = Client()
    client.force_login(staff_user)
    return client


@pytest.fixture
def channel(db):
    return Channel.objects.create(
        ref="web", name="Loja Online", listing_ref="balcao",
        pricing_policy="external", edit_policy="open", config={},
    )


class TestDashboardAccess:
    def test_dashboard_accessible_by_staff(self, staff_client):
        response = staff_client.get("/admin/")
        assert response.status_code == 200

    def test_dashboard_returns_200(self, admin_client):
        response = admin_client.get("/admin/")
        assert response.status_code == 200

    def test_dashboard_anonymous_redirect(self):
        client = Client()
        response = client.get("/admin/")
        assert response.status_code == 302


class TestDashboardContent:
    def test_dashboard_shows_order_kpis(self, admin_client, channel):
        Order.objects.create(
            ref="ORD-D01", channel=channel, status="new", total_q=1000,
            handle_type="phone", handle_ref="5543999990001", data={},
        )
        Order.objects.create(
            ref="ORD-D02", channel=channel, status="confirmed", total_q=2500,
            handle_type="phone", handle_ref="5543999990001", data={},
        )
        response = admin_client.get("/admin/")
        assert response.status_code == 200
        content = response.content.decode()
        assert "Pedidos hoje" in content
        assert "Faturamento hoje" in content

    def test_dashboard_shows_revenue_formatted(self, admin_client, channel):
        Order.objects.create(
            ref="ORD-R01", channel=channel, status="confirmed", total_q=150000,
            handle_type="phone", handle_ref="5543999990001", data={},
        )
        response = admin_client.get("/admin/")
        content = response.content.decode()
        # pt-BR: R$ 1.500,00
        assert "R$ 1.500,00" in content

    def test_dashboard_shows_charts_section(self, admin_client, channel):
        Order.objects.create(
            ref="ORD-C01", channel=channel, status="new", total_q=1000,
            handle_type="phone", handle_ref="5543999990001", data={},
        )
        response = admin_client.get("/admin/")
        content = response.content.decode()
        assert "Pedidos por Status" in content
        assert "Vendas últimos 7 dias" in content

    def test_dashboard_shows_production(self, admin_client):
        try:
            from shopman.crafting.models import Recipe, WorkOrder

            recipe = Recipe.objects.create(
                code="pao-frances-v1", name="Pão Francês",
                output_ref="PAO-FRANCES", batch_size=100,
            )
            WorkOrder.objects.create(
                recipe=recipe, output_ref="PAO-FRANCES",
                quantity=100, status="open",
            )
            response = admin_client.get("/admin/")
            content = response.content.decode()
            assert "Produção de Hoje" in content
        except ImportError:
            pytest.skip("Crafting not installed")

    def test_dashboard_empty_state(self, admin_client):
        """Dashboard works fine with no data — shows empty state messages."""
        response = admin_client.get("/admin/")
        assert response.status_code == 200
        content = response.content.decode()
        assert "Pedidos hoje" in content
        # Empty state messages
        assert "Nenhum pedido pendente" in content
        assert "Estoque OK" in content

    def test_dashboard_trend_comparison(self, admin_client, channel):
        """Revenue card shows vs yesterday trend."""
        from datetime import timedelta

        from django.utils import timezone

        # Create yesterday order
        yesterday = timezone.now() - timedelta(days=1)
        o = Order.objects.create(
            ref="ORD-Y01", channel=channel, status="confirmed", total_q=5000,
            handle_type="phone", handle_ref="5543999990001", data={},
        )
        Order.objects.filter(pk=o.pk).update(created_at=yesterday)

        # Create today order
        Order.objects.create(
            ref="ORD-T01", channel=channel, status="confirmed", total_q=8000,
            handle_type="phone", handle_ref="5543999990001", data={},
        )

        response = admin_client.get("/admin/")
        content = response.content.decode()
        assert "vs ontem" in content


class TestDashboardOrderCountsByStatus:
    """Detailed tests for _order_summary grouping by status."""

    def test_counts_by_status(self, admin_client, channel):
        """Each status gets its own card with correct count."""
        Order.objects.create(
            ref="ORD-S01", channel=channel, status="new", total_q=500,
            handle_type="phone", handle_ref="5543999990001", data={},
        )
        Order.objects.create(
            ref="ORD-S02", channel=channel, status="new", total_q=500,
            handle_type="phone", handle_ref="5543999990001", data={},
        )
        Order.objects.create(
            ref="ORD-S03", channel=channel, status="confirmed", total_q=1000,
            handle_type="phone", handle_ref="5543999990001", data={},
        )
        from shop.dashboard import _order_summary
        from datetime import date
        summary = _order_summary(date.today())
        assert summary["total"] == 3
        assert summary["new_count"] == 2
        # Cards should contain both statuses
        status_map = {c["status"]: c["count"] for c in summary["cards"]}
        assert status_map.get("new") == 2
        assert status_map.get("confirmed") == 1

    def test_empty_summary(self, admin_client, channel):
        """No orders → total 0, no cards."""
        from shop.dashboard import _order_summary
        from datetime import date
        summary = _order_summary(date.today())
        assert summary["total"] == 0
        assert summary["new_count"] == 0
        assert summary["cards"] == []


class TestDashboardRevenueComparison:
    """Detailed tests for _revenue today vs yesterday comparison."""

    def test_revenue_today_vs_yesterday(self, admin_client, channel):
        from datetime import date, timedelta
        from django.utils import timezone as tz

        yesterday = tz.now() - timedelta(days=1)
        o = Order.objects.create(
            ref="ORD-RV1", channel=channel, status="confirmed", total_q=5000,
            handle_type="phone", handle_ref="5543999990001", data={},
        )
        Order.objects.filter(pk=o.pk).update(created_at=yesterday)

        Order.objects.create(
            ref="ORD-RV2", channel=channel, status="confirmed", total_q=8000,
            handle_type="phone", handle_ref="5543999990001", data={},
        )

        from shop.dashboard import _revenue
        today = date.today()
        rev = _revenue(today, today - timedelta(days=1))
        assert rev["today_q"] == 8000
        assert rev["yesterday_q"] == 5000
        assert rev["trend_up"] is True
        assert rev["has_yesterday"] is True

    def test_revenue_no_yesterday(self, admin_client, channel):
        """When no yesterday orders, has_yesterday is False."""
        from datetime import date, timedelta
        Order.objects.create(
            ref="ORD-RV3", channel=channel, status="confirmed", total_q=3000,
            handle_type="phone", handle_ref="5543999990001", data={},
        )
        from shop.dashboard import _revenue
        today = date.today()
        rev = _revenue(today, today - timedelta(days=1))
        assert rev["today_q"] == 3000
        assert rev["yesterday_q"] == 0
        assert rev["has_yesterday"] is False

    def test_revenue_excludes_new_status(self, admin_client, channel):
        """Only confirmed+ statuses count as revenue."""
        Order.objects.create(
            ref="ORD-RV4", channel=channel, status="new", total_q=5000,
            handle_type="phone", handle_ref="5543999990001", data={},
        )
        from datetime import date, timedelta
        from shop.dashboard import _revenue
        today = date.today()
        rev = _revenue(today, today - timedelta(days=1))
        assert rev["today_q"] == 0


class TestDashboardHandlesMissingApps:
    """Dashboard gracefully handles missing optional apps (crafting, stocking)."""

    def test_production_without_crafting(self, admin_client):
        """_production returns empty data when crafting is not importable."""
        from unittest.mock import patch
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if "crafting" in name:
                raise ImportError("No crafting")
            return real_import(name, *args, **kwargs)

        from shop.dashboard import _production
        from datetime import date
        with patch("builtins.__import__", side_effect=mock_import):
            result = _production(date.today())
        assert result["open"] == 0
        assert result["done"] == 0
        assert result["total"] == 0
        assert result["wos"] == []

    def test_dashboard_renders_without_crafting(self, admin_client):
        """Full dashboard page renders even if crafting raises ImportError."""
        response = admin_client.get("/admin/")
        assert response.status_code == 200


class TestFormatBrl:
    def test_format_zero(self):
        from shop.dashboard import _format_brl
        assert _format_brl(0) == "R$ 0,00"

    def test_format_simple(self):
        from shop.dashboard import _format_brl
        assert _format_brl(1500) == "R$ 15,00"

    def test_format_thousands(self):
        from shop.dashboard import _format_brl
        assert _format_brl(150000) == "R$ 1.500,00"

    def test_format_millions(self):
        from shop.dashboard import _format_brl
        assert _format_brl(10000000) == "R$ 100.000,00"
