"""Transfer / split / merge comanda lines via move_pos_tab_lines."""

from __future__ import annotations

from django.test import TestCase
from shopman.orderman.models import Session

from shopman.backstage.models import POSTab
from shopman.shop.models import Channel, Shop
from shopman.shop.services import pos as pos_service
from shopman.shop.services.pos_intent import PosIntentError


def _payload(*, sku: str, qty: int, tab_ref: str, tab_session_key: str) -> dict:
    return {
        "items": [{"sku": sku, "name": sku, "qty": qty, "unit_price_q": 1000}],
        "payment_method": "cash",
        "manual_discount": None,
        "tab_ref": tab_ref,
        "tab_session_key": tab_session_key or None,
    }


class POSMoveTabLinesTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        Shop.objects.create(name="Test Shop", brand_name="Test")
        Channel.objects.create(ref="pdv", name="Balcão", is_active=True)
        POSTab.objects.create(ref="00001007", label="1007")
        POSTab.objects.create(ref="00001008", label="1008")
        from shopman.offerman.models import Product

        Product.objects.create(sku="POS-A", name="A", base_price_q=1000, is_published=True, is_sellable=True)
        Product.objects.create(sku="POS-B", name="B", base_price_q=1000, is_published=True, is_sellable=True)

    def _open_with_item(self, tab_ref: str, *, sku: str, qty: int) -> Session:
        opened = pos_service.open_pos_tab(
            channel_ref="pdv", tab_ref=tab_ref, actor="pos:alice", operator_username="alice",
        )
        pos_service.save_pos_tab(
            channel_ref="pdv",
            payload=_payload(sku=sku, qty=qty, tab_ref=opened["tab_ref"], tab_session_key=opened["tab_session_key"]),
            actor="pos:alice", operator_username="alice",
        )
        return Session.objects.get(session_key=opened["tab_session_key"])

    def test_transfer_line_to_existing_tab_freezes_price(self) -> None:
        source = self._open_with_item("00001007", sku="POS-A", qty=2)
        target = self._open_with_item("00001008", sku="POS-B", qty=1)
        line_id = source.items[0]["line_id"]

        result = pos_service.move_pos_tab_lines(
            channel_ref="pdv",
            from_session_key=source.session_key,
            to_session_key=target.session_key,
            line_ids=[line_id],
            actor="pos:alice", operator_username="alice",
        )

        self.assertTrue(result["ok"])
        self.assertFalse(result["source_closed"])
        source.refresh_from_db()
        target.refresh_from_db()
        self.assertEqual(source.items, [])
        moved = next(item for item in target.items if item["sku"] == "POS-A")
        self.assertEqual(int(moved["qty"]), 2)
        self.assertEqual(moved["unit_price_q"], 1000)  # frozen verbatim

    def test_split_creates_new_tab_with_moved_line(self) -> None:
        source = self._open_with_item("00001007", sku="POS-A", qty=2)
        line_id = source.items[0]["line_id"]

        result = pos_service.move_pos_tab_lines(
            channel_ref="pdv",
            from_session_key=source.session_key,
            to_tab_ref="1009",
            line_ids=[line_id],
            actor="pos:alice", operator_username="alice",
        )

        self.assertTrue(result["ok"])
        source.refresh_from_db()
        self.assertEqual(source.items, [])
        target = Session.objects.get(
            channel_ref="pdv", handle_type="pos_tab", handle_ref="00001009", state="open",
        )
        self.assertEqual(int(target.items[0]["qty"]), 2)
        self.assertEqual(target.items[0]["unit_price_q"], 1000)

    def test_merge_closes_emptied_source(self) -> None:
        source = self._open_with_item("00001007", sku="POS-A", qty=2)
        target = self._open_with_item("00001008", sku="POS-B", qty=1)
        line_ids = [item["line_id"] for item in source.items]

        result = pos_service.move_pos_tab_lines(
            channel_ref="pdv",
            from_session_key=source.session_key,
            to_session_key=target.session_key,
            line_ids=line_ids,
            close_source_when_empty=True,
            actor="pos:alice", operator_username="alice",
        )

        self.assertTrue(result["source_closed"])
        self.assertIsNone(result["source"])
        source.refresh_from_db()
        self.assertEqual(source.state, "abandoned")
        target.refresh_from_db()
        self.assertEqual(len(target.items), 2)

    def test_split_to_occupied_ref_is_rejected(self) -> None:
        source = self._open_with_item("00001007", sku="POS-A", qty=2)
        self._open_with_item("00001008", sku="POS-B", qty=1)
        line_id = source.items[0]["line_id"]

        with self.assertRaises(PosIntentError) as ctx:
            pos_service.move_pos_tab_lines(
                channel_ref="pdv",
                from_session_key=source.session_key,
                to_tab_ref="1008",
                line_ids=[line_id],
                actor="pos:alice", operator_username="alice",
            )
        self.assertEqual(ctx.exception.code, "tab_in_use")
