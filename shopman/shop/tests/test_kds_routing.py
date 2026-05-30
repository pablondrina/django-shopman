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

    cafes = Collection.objects.create(ref="kdsroute-cafes", name="KDSRoute Cafés")
    product = Product.objects.create(
        sku="CAPPUCCINO",
        name="Cappuccino",
        base_price_q=1200,
    )
    CollectionItem.objects.create(collection=cafes, product=product, is_primary=True)

    cafes_kds = KDSInstance.objects.create(
        ref="kdsroute-cafes-station",
        name="KDSRoute Cafés",
        type="prep",
        target_time_minutes=3,
    )
    cafes_kds.collections.add(cafes)
    KDSInstance.objects.create(
        ref="kdsroute-encomendas",
        name="KDSRoute Encomendas",
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
    assert tickets[0].kds_instance.ref == "kdsroute-cafes-station"
    assert tickets[0].items == [
        {
            "sku": "CAPPUCCINO",
            "name": "Cappuccino",
            "qty": 1,
            "notes": "",
            "checked": False,
            "line_id": "1",
        },
    ]


@pytest.mark.django_db
def test_fire_lines_is_progressive_and_idempotent_per_line():
    """Progressive course-by-course firing — only the unfired delta each time.

    Uses a catch-all picking station (no collections) to keep routing trivial
    and Collection-free.
    """
    from shopman.orderman.models import Order, OrderItem

    from shopman.backstage.models import KDSInstance, KDSTicket
    from shopman.shop.adapters import kds as kds_adapter
    from shopman.shop.models import Channel
    from shopman.shop.services.kds import dispatch, fire_lines

    Channel.objects.create(ref="web", name="Web")
    KDSInstance.objects.create(ref="cozinha", name="Cozinha", type="picking")

    session_key = "sk-progressive-1"
    order = Order.objects.create(
        ref="ORD-PROG-001", channel_ref="web", session_key=session_key,
        status=Order.Status.NEW, total_q=3000,
    )
    for line_id, sku in (("1", "PAO"), ("2", "CAFE"), ("3", "BOLO")):
        OrderItem.objects.create(
            order=order, line_id=line_id, sku=sku, name=sku,
            qty="1", unit_price_q=1000, line_total_q=1000,
        )
    lines = [
        {"line_id": "1", "sku": "PAO", "name": "Pão", "qty": 1, "notes": "", "meta": {}},
        {"line_id": "2", "sku": "CAFE", "name": "Café", "qty": 1, "notes": "", "meta": {}},
        {"line_id": "3", "sku": "BOLO", "name": "Bolo", "qty": 1, "notes": "", "meta": {}},
    ]

    # Fire course 1 only → one ticket carrying line 1.
    first = fire_lines(session_key=session_key, lines=lines[:1])
    assert len(first) == 1
    assert {it["line_id"] for it in first[0].items} == {"1"}

    # Re-fire course 1 → no-op (already fired).
    assert fire_lines(session_key=session_key, lines=lines[:1]) == []

    # Fire courses 1+2 → only the line-2 delta is sent.
    second = fire_lines(session_key=session_key, lines=lines[:2])
    assert len(second) == 1
    assert {it["line_id"] for it in second[0].items} == {"2"}

    # Commit reconciliation: dispatch(order) fires only the still-unfired line 3.
    remainder = dispatch(order)
    assert len(remainder) == 1
    assert {it["line_id"] for it in remainder[0].items} == {"3"}

    # Everything fired → dispatch is now a no-op, ledger holds all three.
    assert dispatch(order) == []
    assert kds_adapter.fired_line_ids_for_session(session_key) == {"1", "2", "3"}
    assert KDSTicket.objects.filter(session_key=session_key).count() == 3


@pytest.mark.django_db
def test_cancelled_line_may_refire():
    """A cancelled ticket's line is absent from the ledger → it can re-fire."""
    from shopman.orderman.models import Order, OrderItem

    from shopman.backstage.models import KDSInstance
    from shopman.shop.models import Channel
    from shopman.shop.services.kds import dispatch, fire_lines

    Channel.objects.create(ref="web", name="Web")
    KDSInstance.objects.create(ref="cozinha", name="Cozinha", type="picking")

    session_key = "sk-refire-1"
    order = Order.objects.create(
        ref="ORD-REFIRE-001", channel_ref="web", session_key=session_key,
        status=Order.Status.NEW, total_q=1000,
    )
    OrderItem.objects.create(
        order=order, line_id="1", sku="PAO", name="Pão",
        qty="1", unit_price_q=1000, line_total_q=1000,
    )

    fired = dispatch(order)
    assert len(fired) == 1
    fired[0].status = "cancelled"
    fired[0].save(update_fields=["status"])

    # Same line re-fires because the cancelled ticket is out of the ledger.
    refired = fire_lines(
        session_key=session_key,
        lines=[{"line_id": "1", "sku": "PAO", "name": "Pão", "qty": 1, "notes": "", "meta": {}}],
    )
    assert len(refired) == 1
    assert {it["line_id"] for it in refired[0].items} == {"1"}
