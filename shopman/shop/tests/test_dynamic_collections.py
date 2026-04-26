from decimal import Decimal

import pytest
from django.utils import timezone
from shopman.craftsman.models import Recipe, WorkOrder
from shopman.offerman.models import Product

from shopman.shop import dynamic_collections


@pytest.mark.django_db
def test_fresh_from_oven_uses_current_craftsman_work_order_contract():
    Product.objects.create(
        sku="CROISSANT-FRESH",
        name="Croissant",
        base_price_q=1200,
        is_published=True,
        is_sellable=True,
    )
    recipe = Recipe.objects.create(
        ref="croissant-fresh",
        name="Croissant",
        output_sku="CROISSANT-FRESH",
        batch_size=Decimal("12"),
    )
    WorkOrder.objects.create(
        recipe=recipe,
        output_sku="CROISSANT-FRESH",
        quantity=Decimal("12"),
        finished=Decimal("12"),
        status=WorkOrder.Status.FINISHED,
        finished_at=timezone.now(),
    )

    section = dynamic_collections.resolve("fresh_from_oven", channel_ref="web")

    assert section is not None
    assert [product.sku for product in section.products] == ["CROISSANT-FRESH"]
