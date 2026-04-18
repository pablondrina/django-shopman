"""
Tests for the ``cleanup_stale_planning`` management command.
"""

from datetime import date, timedelta
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command

pytestmark = pytest.mark.django_db


class TestCleanupStalePlanning:
    def test_removes_orphan_planning_quants(self, db):
        from shopman.stockman.models import Quant

        yesterday = date.today() - timedelta(days=1)
        Quant.objects.create(
            sku="GHOST", target_date=yesterday, _quantity=Decimal("5"),
        )
        Quant.objects.create(
            sku="OTHER", target_date=yesterday, _quantity=Decimal("3"),
        )

        call_command("cleanup_stale_planning", stdout=StringIO())

        assert Quant.objects.filter(sku="GHOST").count() == 0
        assert Quant.objects.filter(sku="OTHER").count() == 0

    def test_preserves_quants_with_position(self, db, position_loja):
        from shopman.stockman.models import Quant

        yesterday = date.today() - timedelta(days=1)
        q = Quant.objects.create(
            sku="KEEP", position=position_loja, target_date=yesterday,
            _quantity=Decimal("5"),
        )
        call_command("cleanup_stale_planning", stdout=StringIO())
        assert Quant.objects.filter(pk=q.pk).exists()

    def test_preserves_quants_with_moves(self, db):
        from shopman.stockman.models import Move, Quant

        yesterday = date.today() - timedelta(days=1)
        q = Quant.objects.create(
            sku="KEEP-HIST", target_date=yesterday, _quantity=Decimal("5"),
        )
        Move.objects.create(quant=q, delta=Decimal("5"), reason="histórico")

        call_command("cleanup_stale_planning", stdout=StringIO())
        assert Quant.objects.filter(pk=q.pk).exists()

    def test_preserves_future_planning_quants(self, db):
        from shopman.stockman.models import Quant

        tomorrow = date.today() + timedelta(days=1)
        q = Quant.objects.create(
            sku="PLANNED", target_date=tomorrow, _quantity=Decimal("5"),
        )
        call_command("cleanup_stale_planning", stdout=StringIO())
        assert Quant.objects.filter(pk=q.pk).exists()

    def test_dry_run_removes_nothing(self, db):
        from shopman.stockman.models import Quant

        yesterday = date.today() - timedelta(days=1)
        Quant.objects.create(
            sku="DRY", target_date=yesterday, _quantity=Decimal("5"),
        )
        call_command("cleanup_stale_planning", "--dry-run", stdout=StringIO())
        assert Quant.objects.filter(sku="DRY").count() == 1
