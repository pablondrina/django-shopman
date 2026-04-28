"""Nelson seed coverage for operator production surfaces."""

from __future__ import annotations

from datetime import date, timedelta
from io import StringIO

import pytest
from django.core.management import call_command

from shopman.backstage.models import OperatorAlert
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe, WorkOrder
from shopman.offerman.models import Product
from shopman.orderman.models import OrderItem
from shopman.stockman.models import Batch


@pytest.mark.django_db
def test_nelson_seed_populates_production_history_alerts_and_batches():
    call_command("seed", "--flush", stdout=StringIO())

    assert not Product.objects.filter(sku__startswith="DEMO-").exists()
    assert OrderItem.objects.filter(
        order__ref__startswith="NB-PROD-HIST-",
        sku="CROISSANT",
    ).count() >= 4

    recipe = Recipe.objects.get(ref="croissant")
    assert recipe.meta["requires_batch_tracking"] is True
    assert recipe.meta["max_started_minutes"] > 0
    assert recipe.steps

    suggestions = craft.suggest(date.today() + timedelta(days=1), output_skus=["CROISSANT"])
    assert suggestions
    assert suggestions[0].quantity > 0

    assert WorkOrder.objects.filter(source_ref__startswith="seed:production:today:").exists()
    assert Batch.objects.filter(sku="CROISSANT").exists()
    assert OperatorAlert.objects.filter(type="production_late", acknowledged=False).exists()
    assert OperatorAlert.objects.filter(type="production_low_yield", acknowledged=False).exists()
    assert OperatorAlert.objects.filter(type="production_stock_short", acknowledged=False).exists()
