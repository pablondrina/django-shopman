"""POS kitchen handoff — progressive (course-by-course) fire from a comanda."""

from __future__ import annotations

from django.test import TestCase, override_settings
from shopman.orderman.models import Session

from shopman.backstage.models import KDSInstance, KDSTicket, POSTab
from shopman.shop.models import Channel, Shop
from shopman.shop.services import pos as pos_service


@override_settings(SHOPMAN_HAPPY_HOUR_START="00:00", SHOPMAN_HAPPY_HOUR_END="00:00")
class POSFireTabTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        Shop.objects.create(name="Test Shop", brand_name="Test")
        Channel.objects.create(ref="pdv", name="Balcão", is_active=True)
        POSTab.objects.create(ref="00002001", label="2001")
        # Catch-all picking station (no collections) keeps routing trivial.
        KDSInstance.objects.create(ref="cozinha", name="Cozinha", type="picking")
        from shopman.offerman.models import Product

        for sku in ("FIRE-A", "FIRE-B"):
            Product.objects.create(
                sku=sku, name=sku, base_price_q=1000,
                is_published=True, is_sellable=True,
            )

    def _open_tab_with_two_items(self) -> Session:
        opened = pos_service.open_pos_tab(
            channel_ref="pdv", tab_ref="2001",
            actor="pos:alice", operator_username="alice",
        )
        skey = opened["tab_session_key"]
        pos_service.save_pos_tab(
            channel_ref="pdv",
            payload={
                "items": [
                    {"sku": "FIRE-A", "name": "Fire A", "qty": 1, "unit_price_q": 1000},
                    {"sku": "FIRE-B", "name": "Fire B", "qty": 1, "unit_price_q": 1000},
                ],
                "customer_name": "Ana",
                "payment_method": "cash",
                "manual_discount": None,
                "tab_ref": "2001",
                "tab_session_key": skey,
            },
            actor="pos:alice", operator_username="alice",
        )
        return Session.objects.get(session_key=skey)

    def test_fire_whole_tab_creates_tickets_and_marks_fired(self) -> None:
        session = self._open_tab_with_two_items()
        line_ids = {it["line_id"] for it in session.items}

        result = pos_service.fire_pos_tab(
            channel_ref="pdv", session_key=session.session_key,
            actor="pos:alice", operator_username="alice",
        )

        self.assertTrue(result["ok"])
        # Both lines route to the one picking station → a single ticket.
        self.assertEqual(result["fired_count"], 1)
        self.assertEqual(set(result["fired_lines"]), line_ids)
        tickets = KDSTicket.objects.filter(session_key=session.session_key)
        self.assertEqual(tickets.count(), 1)
        self.assertEqual({it["line_id"] for it in tickets.first().items}, line_ids)
        # Comanda marker persisted and the cart payload annotates each line fired.
        session.refresh_from_db()
        self.assertEqual(set(session.data["fired_lines"]), line_ids)
        self.assertTrue(all(it["fired"] for it in result["tab"]["items"]))

    def test_progressive_fire_sends_only_the_delta(self) -> None:
        session = self._open_tab_with_two_items()
        line_ids = sorted(it["line_id"] for it in session.items)
        first_line, second_line = line_ids[0], line_ids[1]

        # Fire course 1 only.
        first = pos_service.fire_pos_tab(
            channel_ref="pdv", session_key=session.session_key,
            line_ids=[first_line], actor="pos:alice", operator_username="alice",
        )
        self.assertEqual(first["fired_count"], 1)
        self.assertEqual(first["fired_lines"], [first_line])

        # Fire the whole tab → only the still-unfired course 2 is dispatched.
        second = pos_service.fire_pos_tab(
            channel_ref="pdv", session_key=session.session_key,
            actor="pos:alice", operator_username="alice",
        )
        self.assertEqual(second["fired_count"], 1)
        self.assertEqual(second["fired_lines"], line_ids)
        ticket_lines = set()
        for ticket in KDSTicket.objects.filter(session_key=session.session_key):
            ticket_lines.update(it["line_id"] for it in ticket.items)
        self.assertEqual(ticket_lines, {first_line, second_line})

        # Re-firing once everything is out is a no-op.
        third = pos_service.fire_pos_tab(
            channel_ref="pdv", session_key=session.session_key,
            actor="pos:alice", operator_username="alice",
        )
        self.assertEqual(third["fired_count"], 0)
        self.assertEqual(KDSTicket.objects.filter(session_key=session.session_key).count(), 2)

    def test_fire_unknown_tab_raises(self) -> None:
        from shopman.shop.services.pos_intent import PosIntentError

        with self.assertRaises(PosIntentError):
            pos_service.fire_pos_tab(
                channel_ref="pdv", session_key="does-not-exist",
                actor="pos:alice", operator_username="alice",
            )
