from __future__ import annotations

import pytest


@pytest.mark.django_db
def test_dispatch_prefers_collection_specific_station_before_picking_catchall():
    from shopman.offerman.models import Collection, CollectionItem, Product
    from shopman.orderman.models import Order, OrderItem

    from shopman.backstage.models import KDSInstance
    from shopman.shop.models import Channel
    from shopman.shop.services.kds import dispatch

    Channel.objects.create(ref="web", name="Web")

    cafes = Collection.objects.create(ref="cafes-bebidas", name="Cafés e bebidas")
    product = Product.objects.create(
        sku="CAPPUCCINO",
        name="Cappuccino",
        base_price_q=1200,
    )
    CollectionItem.objects.create(collection=cafes, product=product, is_primary=True)

    cafes_kds = KDSInstance.objects.create(
        ref="cafes",
        name="Cafés",
        type="prep",
        target_time_minutes=3,
    )
    cafes_kds.collections.add(cafes)
    KDSInstance.objects.create(
        ref="encomendas",
        name="Encomendas",
        type="picking",
        target_time_minutes=5,
    )

    order = Order.objects.create(
        ref="ORD-KDS-CAFES-001",
        channel_ref="web",
        status=Order.Status.PREPARING,
        total_q=1200,
    )
    OrderItem.objects.create(
        order=order,
        line_id="1",
        sku="CAPPUCCINO",
        name="Cappuccino",
        qty="1",
        unit_price_q=1200,
        line_total_q=1200,
    )

    tickets = dispatch(order)

    assert len(tickets) == 1
    assert tickets[0].kds_instance.ref == "cafes"
    assert tickets[0].items == [
        {
            "sku": "CAPPUCCINO",
            "name": "Cappuccino",
            "qty": 1,
            "notes": "",
            "checked": False,
        },
    ]
