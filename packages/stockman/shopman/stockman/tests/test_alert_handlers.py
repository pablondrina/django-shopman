"""
Tests for stocking.contrib.alerts — signal-driven alert dispatch.

Uses transaction=True because the handler uses transaction.on_commit()
to ensure Quant._quantity is updated before checking alerts.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.utils import timezone

from shopman.stockman import stock
from shopman.stockman.models import Quant
from shopman.stockman.models.alert import StockAlert


pytestmark = [pytest.mark.django_db(transaction=True)]


# ── Fixtures ──


@pytest.fixture
def product(db):
    """Create a test product."""
    from shopman.offerman.models import Product

    p = Product.objects.create(
        sku="PAO-ALERT-TEST",
        name="Pao Alert Test",
        unit="un",
        base_price_q=1000,
        is_available=True,
        shelf_life_days=None,
        availability_policy="planned_ok",
    )
    p.shelflife = None
    return p


@pytest.fixture
def vitrine(db):
    """Get or create vitrine position."""
    from shopman.stockman.models import Position, PositionKind

    position, _ = Position.objects.get_or_create(
        ref="vitrine_alert_test",
        defaults={
            "name": "Vitrine Alert Test",
            "kind": PositionKind.PHYSICAL,
            "is_saleable": True,
        },
    )
    return position


@pytest.fixture
def alert(product, vitrine):
    """Create a stock alert for product at vitrine, min_quantity=20."""
    return StockAlert.objects.create(
        sku=product.sku,
        position=vitrine,
        min_quantity=Decimal("20"),
        is_active=True,
    )


@pytest.fixture
def stocked_product(product, vitrine):
    """Product with 50 units in stock. Returns (product, quant)."""
    quant = stock.receive(Decimal("50"), product.sku, vitrine, reason="Initial stock")
    return product, quant


# ── Signal handler tests ──


class TestMoveSignalTriggersAlertCheck:
    """post_save on Move triggers alert check for affected SKU."""

    def test_move_below_threshold_triggers_alert(self, stocked_product, vitrine, alert):
        """When stock drops below min_quantity, alert is triggered."""
        product, quant = stocked_product
        stock.issue(Decimal("35"), quant, reason="Sale")

        alert.refresh_from_db()
        assert alert.last_triggered_at is not None

    def test_move_above_threshold_no_trigger(self, stocked_product, vitrine, alert):
        """When stock stays above min_quantity, alert is not triggered."""
        product, quant = stocked_product
        stock.issue(Decimal("10"), quant, reason="Sale")

        alert.refresh_from_db()
        assert alert.last_triggered_at is None

    def test_inactive_alert_not_checked(self, stocked_product, vitrine, alert):
        """Inactive alerts are skipped."""
        product, quant = stocked_product
        alert.is_active = False
        alert.save()

        stock.issue(Decimal("45"), quant, reason="Big sale")

        alert.refresh_from_db()
        assert alert.last_triggered_at is None

    def test_receive_above_threshold_no_trigger(self, product, vitrine, alert):
        """Receiving stock above threshold does not trigger alert."""
        stock.receive(Decimal("50"), product.sku, vitrine, reason="Restock")

        alert.refresh_from_db()
        assert alert.last_triggered_at is None


class TestCooldown:
    """Alert dispatch respects cooldown period."""

    def test_cooldown_prevents_re_dispatch(self, stocked_product, vitrine, alert, settings):
        """Alert within cooldown period does not dispatch notification."""
        product, quant = stocked_product
        settings.STOCKMAN_ALERT_COOLDOWN_MINUTES = 60

        # Simulate recent trigger
        alert.last_triggered_at = timezone.now() - timedelta(minutes=10)
        alert.save()

        with patch("shopman.stockman.contrib.alerts.handlers._dispatch_notification") as mock_dispatch:
            stock.issue(Decimal("35"), quant, reason="Sale")
            mock_dispatch.assert_not_called()

    def test_expired_cooldown_allows_dispatch(self, stocked_product, vitrine, alert, settings):
        """Alert past cooldown period dispatches notification."""
        product, quant = stocked_product
        settings.STOCKMAN_ALERT_COOLDOWN_MINUTES = 60

        # Simulate old trigger (past cooldown)
        alert.last_triggered_at = timezone.now() - timedelta(hours=2)
        alert.save()

        with patch("shopman.stockman.contrib.alerts.handlers._dispatch_notification") as mock_dispatch:
            stock.issue(Decimal("35"), quant, reason="Sale")
            mock_dispatch.assert_called_once()


class TestDirectiveCreation:
    """Alert dispatch creates Directive when Omniman is available."""

    @pytest.mark.skip(reason="Requires shopman.omniman — not yet migrated")
    def test_dispatch_creates_directive(self, stocked_product, vitrine, alert):
        """Triggered alert creates a Directive with notification.send topic."""
        from shopman.omniman.models import Directive

        product, quant = stocked_product
        stock.issue(Decimal("35"), quant, reason="Sale")

        directives = Directive.objects.filter(topic="notification.send")
        assert directives.exists()
        d = directives.first()
        assert d.payload["event"] == "stock.alert.triggered"
        assert d.payload["context"]["alert_id"] == alert.pk

    def test_dispatch_graceful_without_ordering(self, stocked_product, vitrine, alert):
        """Without Omniman, dispatch logs and returns gracefully."""
        product, quant = stocked_product

        with patch(
            "shopman.stockman.contrib.alerts.handlers._dispatch_notification"
        ) as mock_dispatch:
            mock_dispatch.return_value = None
            stock.issue(Decimal("35"), quant, reason="Sale")
            mock_dispatch.assert_called_once()


class TestAlertConf:
    """Configuration for alert cooldown."""

    def test_default_cooldown(self):
        from shopman.stockman.contrib.alerts.conf import get_alert_cooldown_minutes

        assert get_alert_cooldown_minutes() == 60

    def test_custom_cooldown(self, settings):
        from shopman.stockman.contrib.alerts.conf import get_alert_cooldown_minutes

        settings.STOCKMAN_ALERT_COOLDOWN_MINUTES = 30
        assert get_alert_cooldown_minutes() == 30
