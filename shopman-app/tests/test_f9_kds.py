"""Tests for WP-F9: KDS — Kitchen Display System."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.test import Client
from shopman.crafting.models import Recipe
from shopman.offering.models import Collection, CollectionItem, Product
from shopman.ordering.models import Channel, Order, OrderItem

from shop.models import KDSInstance, KDSTicket


@pytest.fixture(autouse=True)
def shop_instance(db):
    from shop.models import Shop

    return Shop.objects.create(
        name="Nelson Boulangerie",
        brand_name="Nelson Boulangerie",
        short_name="Nelson",
        tagline="Padaria Artesanal",
        primary_color="#C5A55A",
        default_ddd="43",
        city="Londrina",
        state_code="PR",
    )


@pytest.fixture
def channel(db):
    return Channel.objects.create(
        ref="web",
        name="Loja Online",
        listing_ref="balcao",
        pricing_policy="external",
        edit_policy="open",
        config={},
    )


@pytest.fixture
def staff_user(db):
    return User.objects.create_user(
        username="operador", password="test1234", is_staff=True,
    )


@pytest.fixture
def staff_client(staff_user):
    client = Client()
    client.login(username="operador", password="test1234")
    return client


# ── Catalog fixtures ────────────────────────────────────────────────


@pytest.fixture
def collection_paes(db):
    return Collection.objects.create(slug="paes", name="Pães")


@pytest.fixture
def collection_cafe(db):
    return Collection.objects.create(slug="cafe", name="Café")


@pytest.fixture
def product_croissant(db, collection_paes):
    p = Product.objects.create(sku="CROISSANT", name="Croissant Simples", base_price_q=800)
    CollectionItem.objects.create(collection=collection_paes, product=p, is_primary=True)
    return p


@pytest.fixture
def product_pao(db, collection_paes):
    p = Product.objects.create(sku="PAO-FRANCES", name="Pão Francês", base_price_q=150)
    CollectionItem.objects.create(collection=collection_paes, product=p, is_primary=True)
    return p


@pytest.fixture
def recipe_croissant(db, product_croissant):
    return Recipe.objects.create(
        code="croissant-v1",
        name="Croissant Simples",
        output_ref="CROISSANT",
        batch_size=Decimal("10"),
        is_active=True,
    )


# ── KDS fixtures ────────────────────────────────────────────────────


@pytest.fixture
def kds_prep(db, collection_paes):
    inst = KDSInstance.objects.create(ref="padaria", name="Padaria", type="prep")
    inst.collections.add(collection_paes)
    return inst


@pytest.fixture
def kds_picking(db, collection_paes):
    inst = KDSInstance.objects.create(ref="montagem", name="Montagem", type="picking")
    inst.collections.add(collection_paes)
    return inst


@pytest.fixture
def kds_expedition(db):
    return KDSInstance.objects.create(ref="expedicao", name="Expedição", type="expedition")


@pytest.fixture
def processing_order(channel, product_croissant, product_pao):
    order = Order.objects.create(
        ref="ORD-F9-001",
        channel=channel,
        status="new",
        total_q=2350,
        data={"customer_name": "Maria Silva"},
    )
    OrderItem.objects.create(
        order=order, line_id="L1", sku="CROISSANT", name="Croissant Simples",
        qty=Decimal("2"), unit_price_q=800, line_total_q=1600,
    )
    OrderItem.objects.create(
        order=order, line_id="L2", sku="PAO-FRANCES", name="Pão Francês",
        qty=Decimal("5"), unit_price_q=150, line_total_q=750,
    )
    order.transition_status("confirmed", actor="test")
    order.transition_status("processing", actor="test")
    return order


# ── TestKDSModels ───────────────────────────────────────────────────


class TestKDSModels:
    def test_kds_instance_creation(self, kds_prep, collection_paes):
        assert kds_prep.ref == "padaria"
        assert kds_prep.type == "prep"
        assert kds_prep.is_active is True
        assert collection_paes in kds_prep.collections.all()
        assert "Padaria" in str(kds_prep)

    def test_kds_ticket_creation(self, kds_prep, processing_order):
        ticket = KDSTicket.objects.create(
            order=processing_order,
            kds_instance=kds_prep,
            items=[{"sku": "CROISSANT", "name": "Croissant", "qty": 2, "notes": "", "checked": False}],
        )
        assert ticket.status == "pending"
        assert ticket.completed_at is None
        assert len(ticket.items) == 1
        assert "ORD-F9-001" in str(ticket)


# ── TestKDSAccess ───────────────────────────────────────────────────


class TestKDSAccess:
    def test_kds_index_requires_staff(self, client, kds_prep):
        resp = client.get("/kds/")
        assert resp.status_code == 302
        assert "/admin/login/" in resp.url

    def test_kds_display_requires_staff(self, client, kds_prep):
        resp = client.get("/kds/padaria/")
        assert resp.status_code == 302
        assert "/admin/login/" in resp.url


# ── TestKDSDisplay ──────────────────────────────────────────────────


class TestKDSDisplay:
    def test_kds_index_lists_active_instances(self, staff_client, kds_prep, kds_picking, kds_expedition):
        inactive = KDSInstance.objects.create(
            ref="inativo", name="Inativo", type="prep", is_active=False,
        )
        resp = staff_client.get("/kds/")
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "Padaria" in content
        assert "Montagem" in content
        assert "Expedição" in content
        assert "Inativo" not in content

    def test_kds_display_shows_tickets_for_instance(
        self, staff_client, kds_prep, kds_picking, processing_order,
    ):
        # Create tickets for different instances
        KDSTicket.objects.create(
            order=processing_order, kds_instance=kds_prep,
            items=[{"sku": "CROISSANT", "name": "Croissant", "qty": 2, "notes": "", "checked": False}],
        )
        KDSTicket.objects.create(
            order=processing_order, kds_instance=kds_picking,
            items=[{"sku": "PAO-FRANCES", "name": "Pão Francês", "qty": 5, "notes": "", "checked": False}],
        )

        resp = staff_client.get("/kds/padaria/")
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "Croissant" in content
        assert "Pão Francês" not in content


# ── TestKDSDispatch ─────────────────────────────────────────────────


class TestKDSDispatch:
    def test_dispatch_routes_prep_by_recipe(
        self, kds_prep, kds_picking, processing_order, recipe_croissant,
    ):
        from channels.handlers.kds_dispatch import dispatch_to_kds

        tickets = dispatch_to_kds(processing_order)
        prep_tickets = [t for t in tickets if t.kds_instance.type == "prep"]
        assert len(prep_tickets) == 1
        prep_skus = [it["sku"] for it in prep_tickets[0].items]
        assert "CROISSANT" in prep_skus

    def test_dispatch_routes_picking_no_recipe(
        self, kds_prep, kds_picking, processing_order, recipe_croissant,
    ):
        from channels.handlers.kds_dispatch import dispatch_to_kds

        tickets = dispatch_to_kds(processing_order)
        picking_tickets = [t for t in tickets if t.kds_instance.type == "picking"]
        assert len(picking_tickets) == 1
        picking_skus = [it["sku"] for it in picking_tickets[0].items]
        assert "PAO-FRANCES" in picking_skus

    def test_dispatch_skips_unmatched_items(self, channel):
        """Items with no matching KDS instance are silently skipped."""
        from channels.handlers.kds_dispatch import dispatch_to_kds

        # Create order with unmatched product (no collection, no KDS)
        p = Product.objects.create(sku="UNKNOWN", name="Unknown", base_price_q=100)
        order = Order.objects.create(
            ref="ORD-F9-SKIP", channel=channel, status="new", total_q=100,
        )
        OrderItem.objects.create(
            order=order, line_id="L1", sku="UNKNOWN", name="Unknown",
            qty=Decimal("1"), unit_price_q=100, line_total_q=100,
        )
        order.transition_status("confirmed", actor="test")
        order.transition_status("processing", actor="test")

        tickets = dispatch_to_kds(order)
        assert len(tickets) == 0


# ── TestKDSActions ──────────────────────────────────────────────────


class TestKDSActions:
    def test_check_item_toggles_checked(self, staff_client, kds_prep, processing_order):
        ticket = KDSTicket.objects.create(
            order=processing_order, kds_instance=kds_prep,
            items=[
                {"sku": "CROISSANT", "name": "Croissant", "qty": 2, "notes": "", "checked": False},
            ],
        )
        resp = staff_client.post(f"/kds/ticket/{ticket.pk}/check/", {"index": "0"})
        assert resp.status_code == 200
        ticket.refresh_from_db()
        assert ticket.items[0]["checked"] is True
        assert ticket.status == "in_progress"

    def test_mark_done_completes_ticket(self, staff_client, kds_prep, processing_order):
        ticket = KDSTicket.objects.create(
            order=processing_order, kds_instance=kds_prep,
            items=[
                {"sku": "CROISSANT", "name": "Croissant", "qty": 2, "notes": "", "checked": False},
            ],
        )
        resp = staff_client.post(f"/kds/ticket/{ticket.pk}/done/")
        assert resp.status_code == 200
        ticket.refresh_from_db()
        assert ticket.status == "done"
        assert ticket.completed_at is not None
        assert ticket.items[0]["checked"] is True

    def test_all_done_advances_order_to_ready(
        self, staff_client, kds_prep, kds_picking, processing_order,
    ):
        t1 = KDSTicket.objects.create(
            order=processing_order, kds_instance=kds_prep,
            items=[{"sku": "CROISSANT", "name": "Croissant", "qty": 2, "notes": "", "checked": False}],
        )
        t2 = KDSTicket.objects.create(
            order=processing_order, kds_instance=kds_picking,
            items=[{"sku": "PAO-FRANCES", "name": "Pão Francês", "qty": 5, "notes": "", "checked": False}],
        )

        # Complete first ticket
        staff_client.post(f"/kds/ticket/{t1.pk}/done/")
        processing_order.refresh_from_db()
        assert processing_order.status == "processing"  # Not ready yet

        # Complete second ticket → all done → order advances
        staff_client.post(f"/kds/ticket/{t2.pk}/done/")
        processing_order.refresh_from_db()
        assert processing_order.status == "ready"


# ── TestKDSExpedition ───────────────────────────────────────────────


class TestKDSExpedition:
    def test_expedition_shows_ready_orders(self, staff_client, kds_expedition, channel):
        ready_order = Order.objects.create(
            ref="ORD-F9-RDY", channel=channel, status="new", total_q=1000,
            data={"customer_name": "Ana"},
        )
        ready_order.transition_status("confirmed", actor="test")
        ready_order.transition_status("processing", actor="test")
        ready_order.transition_status("ready", actor="test")

        resp = staff_client.get("/kds/expedicao/")
        assert resp.status_code == 200
        assert "ORD-F9-RDY" in resp.content.decode()

    def test_expedition_dispatch_transitions_order(self, staff_client, kds_expedition, channel):
        order = Order.objects.create(
            ref="ORD-F9-DSP", channel=channel, status="new", total_q=1000,
            data={"delivery_method": "delivery"},
        )
        order.transition_status("confirmed", actor="test")
        order.transition_status("processing", actor="test")
        order.transition_status("ready", actor="test")

        resp = staff_client.post(
            f"/kds/expedition/{order.pk}/action/", {"action": "dispatch"},
        )
        assert resp.status_code == 200
        order.refresh_from_db()
        assert order.status == "dispatched"
