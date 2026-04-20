"""
Tests for :func:`quants_eligible_for` — the canonical quant scope gate.

Validates filtering by:

- Position allowlist (``allowed_positions``)
- Position denylist (``excluded_positions``)
- Shelflife window (``product.shelf_life_days``)
- Batch expiry
- ``target_date`` gate
- Combinations of the above
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from shopman.stockman.models import Batch, Position, PositionKind, Quant
from shopman.stockman.services.scope import quants_eligible_for

pytestmark = pytest.mark.django_db


@pytest.fixture
def perishable_validator(settings):
    settings.STOCKMAN = {
        "SKU_VALIDATOR": "shopman.stockman.tests.fakes.PerishableSkuValidator",
    }
    from shopman.stockman.adapters.sku_validation import reset_sku_validator

    reset_sku_validator()
    yield
    reset_sku_validator()


@pytest.fixture
def ontem_position(db):
    position, _ = Position.objects.get_or_create(
        ref="ontem",
        defaults={
            "name": "Vitrine D-1",
            "kind": PositionKind.PHYSICAL,
            "is_saleable": True,
        },
    )
    return position


@pytest.fixture
def deposito_position(db):
    position, _ = Position.objects.get_or_create(
        ref="deposito",
        defaults={
            "name": "Depósito",
            "kind": PositionKind.PHYSICAL,
            "is_saleable": False,
        },
    )
    return position


class TestBaseFilter:
    def test_returns_only_positive_quantities_for_sku(self, product, vitrine, today):
        Quant.objects.create(
            sku=product.sku, position=vitrine, _quantity=Decimal("10"),
        )
        Quant.objects.create(
            sku=product.sku, position=vitrine, target_date=today,
            _quantity=Decimal("0"),
        )
        Quant.objects.create(
            sku="OTHER-SKU", position=vitrine, _quantity=Decimal("99"),
        )

        qs = quants_eligible_for(product.sku, target_date=today)

        assert qs.count() == 1
        assert qs.first()._quantity == Decimal("10")


class TestTargetDateGate:
    def test_excludes_future_quants_beyond_target(
        self, product, vitrine, today, tomorrow,
    ):
        Quant.objects.create(
            sku=product.sku, position=vitrine, _quantity=Decimal("5"),
        )
        Quant.objects.create(
            sku=product.sku, position=vitrine, target_date=tomorrow,
            _quantity=Decimal("7"),
        )

        qs = quants_eligible_for(product.sku, target_date=today)

        assert qs.count() == 1
        assert qs.first()._quantity == Decimal("5")

    def test_includes_future_quants_within_target(
        self, product, vitrine, today, tomorrow,
    ):
        Quant.objects.create(
            sku=product.sku, position=vitrine, target_date=tomorrow,
            _quantity=Decimal("7"),
        )

        qs = quants_eligible_for(product.sku, target_date=tomorrow)

        assert qs.count() == 1


class TestShelflife:
    def test_perishable_excludes_stale_physical_quants(
        self, perishable_product, vitrine, today, perishable_validator,
    ):
        """shelf_life_days=0 means only same-day physical stock is valid."""
        quant = Quant.objects.create(
            sku=perishable_product.sku,
            position=vitrine,
            _quantity=Decimal("10"),
        )
        Quant.objects.filter(pk=quant.pk).update(
            created_at=quant.created_at - timedelta(days=1),
        )

        qs = quants_eligible_for(perishable_product.sku, target_date=today)

        assert qs.count() == 0

    def test_perishable_keeps_same_day_physical_quants(
        self, perishable_product, vitrine, today, perishable_validator,
    ):
        Quant.objects.create(
            sku=perishable_product.sku,
            position=vitrine,
            _quantity=Decimal("10"),
        )

        qs = quants_eligible_for(perishable_product.sku, target_date=today)

        assert qs.count() == 1

    def test_non_perishable_keeps_old_physical_quants(
        self, product, vitrine, today,
    ):
        """shelf_life_days=None disables the shelflife window."""
        quant = Quant.objects.create(
            sku=product.sku,
            position=vitrine,
            _quantity=Decimal("10"),
        )
        Quant.objects.filter(pk=quant.pk).update(
            created_at=quant.created_at - timedelta(days=365),
        )

        qs = quants_eligible_for(product.sku, target_date=today)

        assert qs.count() == 1


class TestPositionScope:
    def test_allowed_positions_limits_to_listed_refs(
        self, product, vitrine, ontem_position, today,
    ):
        Quant.objects.create(
            sku=product.sku, position=vitrine, _quantity=Decimal("5"),
        )
        Quant.objects.create(
            sku=product.sku, position=ontem_position, _quantity=Decimal("7"),
        )

        qs = quants_eligible_for(
            product.sku, target_date=today, allowed_positions=["vitrine"],
        )

        assert qs.count() == 1
        assert qs.first().position.ref == "vitrine"

    def test_excluded_positions_removes_listed_refs(
        self, product, vitrine, ontem_position, today,
    ):
        Quant.objects.create(
            sku=product.sku, position=vitrine, _quantity=Decimal("5"),
        )
        Quant.objects.create(
            sku=product.sku, position=ontem_position, _quantity=Decimal("7"),
        )

        qs = quants_eligible_for(
            product.sku, target_date=today, excluded_positions=["ontem"],
        )

        assert qs.count() == 1
        assert qs.first().position.ref == "vitrine"

    def test_excluded_positions_keeps_quants_without_position(
        self, product, vitrine, ontem_position, today, tomorrow,
    ):
        """Planned quants typically have position=None and must survive a
        denylist check — the denylist only removes quants sitting at the
        listed refs."""
        Quant.objects.create(
            sku=product.sku, position=ontem_position, _quantity=Decimal("5"),
        )
        Quant.objects.create(
            sku=product.sku, target_date=tomorrow, _quantity=Decimal("8"),
        )

        qs = quants_eligible_for(
            product.sku, target_date=tomorrow, excluded_positions=["ontem"],
        )

        assert qs.count() == 1
        assert qs.first().position is None

    def test_allowed_and_excluded_combine(
        self, product, vitrine, ontem_position, deposito_position, today,
    ):
        Quant.objects.create(
            sku=product.sku, position=vitrine, _quantity=Decimal("5"),
        )
        Quant.objects.create(
            sku=product.sku, position=ontem_position, _quantity=Decimal("7"),
        )
        Quant.objects.create(
            sku=product.sku, position=deposito_position, _quantity=Decimal("9"),
        )

        qs = quants_eligible_for(
            product.sku,
            target_date=today,
            allowed_positions=["vitrine", "ontem", "deposito"],
            excluded_positions=["ontem"],
        )

        refs = sorted(q.position.ref for q in qs)
        assert refs == ["deposito", "vitrine"]


class TestBatchExpiry:
    def test_expired_batch_is_filtered_out(
        self, product, vitrine, today,
    ):
        yesterday = today - timedelta(days=1)
        Batch.objects.create(
            sku=product.sku, ref="OLD", expiry_date=yesterday,
        )
        Quant.objects.create(
            sku=product.sku, position=vitrine, batch="OLD",
            _quantity=Decimal("3"),
        )
        Quant.objects.create(
            sku=product.sku, position=vitrine, batch="FRESH",
            _quantity=Decimal("4"),
        )

        qs = quants_eligible_for(product.sku, target_date=today)

        refs = [q.batch for q in qs]
        assert refs == ["FRESH"]


class TestCombinations:
    def test_denylist_plus_shelflife_plus_target(
        self, perishable_product, vitrine, ontem_position, today, tomorrow,
        perishable_validator,
    ):
        """Realistic remote-channel scenario for a daily bread:
        - vitrine today: eligible
        - ontem: excluded by denylist
        - tomorrow's planned stock: excluded by target gate (target=today)
        """
        Quant.objects.create(
            sku=perishable_product.sku, position=vitrine,
            _quantity=Decimal("25"),
        )
        Quant.objects.create(
            sku=perishable_product.sku, position=ontem_position,
            _quantity=Decimal("27"),
        )
        Quant.objects.create(
            sku=perishable_product.sku, target_date=tomorrow,
            _quantity=Decimal("30"),
        )

        qs = quants_eligible_for(
            perishable_product.sku,
            target_date=today,
            excluded_positions=["ontem"],
        )

        positions = sorted(
            (q.position.ref if q.position else None) for q in qs
        )
        assert positions == ["vitrine"]
