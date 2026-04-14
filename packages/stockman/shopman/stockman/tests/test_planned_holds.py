"""
Tests for planned stock holds and materialization flow.

Verifies:
- Holds against planned quants work correctly
- realize() sets TTL on materialized holds
- realize() emits holds_materialized signal
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from shopman.stockman.models.enums import HoldStatus
from shopman.stockman.models.hold import Hold
from shopman.stockman.services.holds import StockHolds
from shopman.stockman.services.movements import StockMovements
from shopman.stockman.services.planning import StockPlanning


@pytest.mark.django_db
class TestPlannedHolds:
    """Test holds against planned (future) quants."""

    def test_hold_against_planned_quant(self, product, producao, tomorrow):
        """Hold can be created against a planned quant."""
        # Create planned stock for tomorrow
        StockMovements.receive(
            quantity=Decimal("50"),
            sku=product.sku,
            position=producao,
            target_date=tomorrow,
            reason="Planned production",
        )

        # Create hold against it
        hold_id = StockHolds.hold(
            quantity=Decimal("10"),
            product=product,
            target_date=tomorrow,
            expires_at=None,
        )

        assert hold_id.startswith("hold:")
        pk = int(hold_id.split(":")[1])
        hold = Hold.objects.get(pk=pk)
        assert hold.quant is not None
        assert hold.quant.target_date == tomorrow
        assert hold.expires_at is None  # No timeout
        assert hold.status == HoldStatus.PENDING

    def test_hold_against_planned_is_reservation(self, product, producao, tomorrow):
        """Hold against planned stock is a reservation (not demand)."""
        StockMovements.receive(
            quantity=Decimal("50"),
            sku=product.sku,
            position=producao,
            target_date=tomorrow,
        )

        hold_id = StockHolds.hold(
            quantity=Decimal("10"),
            product=product,
            target_date=tomorrow,
        )

        pk = int(hold_id.split(":")[1])
        hold = Hold.objects.get(pk=pk)
        assert hold.is_reservation
        assert not hold.is_demand


@pytest.mark.django_db
class TestRealizeWithHolds:
    """Test StockPlanning.realize() with hold materialization."""

    def _setup_planned_with_hold(self, product, producao, vitrine, target_date):
        """Helper: create planned quant with a hold."""
        StockMovements.receive(
            quantity=Decimal("50"),
            sku=product.sku,
            position=producao,
            target_date=target_date,
            reason="Planned production",
        )

        hold_id = StockHolds.hold(
            quantity=Decimal("10"),
            product=product,
            target_date=target_date,
            expires_at=None,
            reference="session-123",
        )

        return hold_id

    def test_realize_sets_ttl_on_materialized_holds(
        self, product, producao, vitrine, tomorrow
    ):
        """realize() sets expires_at on holds that had no timeout."""
        hold_id = self._setup_planned_with_hold(
            product, producao, vitrine, tomorrow
        )
        pk = int(hold_id.split(":")[1])

        # Before realize: hold has no expiry
        hold = Hold.objects.get(pk=pk)
        assert hold.expires_at is None

        # Realize production
        StockPlanning.realize(
            product=product,
            target_date=tomorrow,
            actual_quantity=Decimal("50"),
            to_position=vitrine,
            from_position=producao,
        )

        # After realize: hold has expiry (clock started)
        hold.refresh_from_db()
        assert hold.expires_at is not None
        assert hold.quant.target_date is None  # Now physical

    def test_realize_preserves_existing_ttl(
        self, product, producao, vitrine, tomorrow
    ):
        """realize() doesn't override existing expires_at on holds."""
        from django.utils import timezone

        StockMovements.receive(
            quantity=Decimal("50"),
            sku=product.sku,
            position=producao,
            target_date=tomorrow,
        )

        # Create hold WITH explicit TTL
        original_expiry = timezone.now() + timedelta(hours=2)
        hold_id = StockHolds.hold(
            quantity=Decimal("10"),
            product=product,
            target_date=tomorrow,
            expires_at=original_expiry,
        )

        # Realize
        StockPlanning.realize(
            product=product,
            target_date=tomorrow,
            actual_quantity=Decimal("50"),
            to_position=vitrine,
            from_position=producao,
        )

        # TTL should be preserved (not overwritten)
        pk = int(hold_id.split(":")[1])
        hold = Hold.objects.get(pk=pk)
        assert abs(hold.expires_at - original_expiry) < timedelta(seconds=1)

    @pytest.mark.django_db(transaction=True)
    def test_realize_emits_holds_materialized_signal(
        self, product, producao, vitrine, tomorrow
    ):
        """realize() emits holds_materialized signal for transferred holds."""
        from shopman.stockman.signals import holds_materialized

        hold_id = self._setup_planned_with_hold(
            product, producao, vitrine, tomorrow
        )

        received = []

        def handler(sender, hold_ids, sku, target_date, **kwargs):
            received.append({
                "hold_ids": hold_ids,
                "sku": sku,
                "target_date": target_date,
            })

        holds_materialized.connect(handler)
        try:
            StockPlanning.realize(
                product=product,
                target_date=tomorrow,
                actual_quantity=Decimal("50"),
                to_position=vitrine,
                from_position=producao,
            )

            assert len(received) == 1
            assert hold_id in received[0]["hold_ids"]
            assert received[0]["sku"] == product.sku
            assert received[0]["target_date"] == tomorrow
        finally:
            holds_materialized.disconnect(handler)

    @pytest.mark.django_db(transaction=True)
    def test_realize_no_signal_without_holds(
        self, product, producao, vitrine, tomorrow
    ):
        """realize() doesn't emit signal when there are no holds to transfer."""
        from shopman.stockman.signals import holds_materialized

        # Create planned stock without holds
        StockMovements.receive(
            quantity=Decimal("50"),
            sku=product.sku,
            position=producao,
            target_date=tomorrow,
        )

        received = []

        def handler(sender, **kwargs):
            received.append(True)

        holds_materialized.connect(handler)
        try:
            StockPlanning.realize(
                product=product,
                target_date=tomorrow,
                actual_quantity=Decimal("50"),
                to_position=vitrine,
                from_position=producao,
            )

            assert len(received) == 0
        finally:
            holds_materialized.disconnect(handler)

    def test_realize_hold_metadata_preserved(
        self, product, producao, vitrine, tomorrow
    ):
        """realize() preserves hold metadata (reference, channel_ref)."""
        StockMovements.receive(
            quantity=Decimal("50"),
            sku=product.sku,
            position=producao,
            target_date=tomorrow,
        )

        hold_id = StockHolds.hold(
            quantity=Decimal("10"),
            product=product,
            target_date=tomorrow,
            expires_at=None,
            reference="session-abc",
            channel_ref="whatsapp",
        )

        StockPlanning.realize(
            product=product,
            target_date=tomorrow,
            actual_quantity=Decimal("50"),
            to_position=vitrine,
            from_position=producao,
        )

        pk = int(hold_id.split(":")[1])
        hold = Hold.objects.get(pk=pk)
        assert hold.metadata["reference"] == "session-abc"
        assert hold.metadata["channel_ref"] == "whatsapp"
