"""GIFT-UX — integridade do presente (entrega para terceiro).

Spec: docs/plans/GIFT-UX-PLAN.md. Cobre a guarda de integridade pura
(``build_gift_data``) e o contrato Session→Order (CommitService propaga
``is_gift``/``recipient``/``gift_message``; nunca grava recipient parcial; quando
não é presente, as chaves não existem).
"""

from __future__ import annotations

from django.test import TestCase
from shopman.orderman.ids import generate_session_key
from shopman.orderman.models import Order, Session
from shopman.orderman.services.modify import ModifyService

from shopman.shop.models import Channel, Shop
from shopman.shop.services import checkout as checkout_service
from shopman.storefront.intents.gift import build_gift_data


class BuildGiftDataTests(TestCase):
    """Função pura — sem request, sem DB."""

    def test_not_a_gift_returns_none(self) -> None:
        data, errors = build_gift_data(
            is_gift=False, fulfillment_type="delivery",
            recipient_name="Maria", recipient_phone="43999990000",
        )
        self.assertIsNone(data)
        self.assertEqual(errors, {})

    def test_valid_gift_delivery(self) -> None:
        data, errors = build_gift_data(
            is_gift=True,
            fulfillment_type="delivery",
            recipient_name="  Maria Silva ",
            recipient_phone="(43) 99999-0000",
            gift_message="  Feliz aniversário! ",
            hide_values=True,
        )
        self.assertEqual(errors, {})
        self.assertEqual(data["is_gift"], True)
        self.assertEqual(data["recipient"]["name"], "Maria Silva")
        self.assertEqual(data["recipient"]["phone"], "+5543999990000")
        self.assertEqual(data["gift_message"], "Feliz aniversário!")
        self.assertEqual(data["gift_hide_values"], True)

    def test_gift_message_and_hide_values_optional(self) -> None:
        data, errors = build_gift_data(
            is_gift=True, fulfillment_type="delivery",
            recipient_name="Maria", recipient_phone="43999990000",
        )
        self.assertEqual(errors, {})
        self.assertNotIn("gift_message", data)
        self.assertNotIn("gift_hide_values", data)

    def test_delivery_missing_name_errors(self) -> None:
        data, errors = build_gift_data(
            is_gift=True, fulfillment_type="delivery",
            recipient_name="  ", recipient_phone="43999990000",
        )
        self.assertIsNone(data)
        self.assertIn("recipient_name", errors)

    def test_delivery_missing_phone_errors(self) -> None:
        data, errors = build_gift_data(
            is_gift=True, fulfillment_type="delivery",
            recipient_name="Maria", recipient_phone="",
        )
        self.assertIsNone(data)
        self.assertIn("recipient_phone", errors)

    def test_delivery_invalid_phone_errors(self) -> None:
        data, errors = build_gift_data(
            is_gift=True, fulfillment_type="delivery",
            recipient_name="Maria", recipient_phone="123",
        )
        self.assertIsNone(data)
        self.assertIn("recipient_phone", errors)

    def test_delivery_never_partial_recipient(self) -> None:
        """Com erro na entrega, nunca devolve recipient parcial."""
        data, errors = build_gift_data(
            is_gift=True, fulfillment_type="delivery",
            recipient_name="Maria", recipient_phone="",
        )
        self.assertIsNone(data)

    def test_pickup_gift_without_recipient(self) -> None:
        """Retirada = 'embalar para presente': destinatário opcional, sem erro."""
        data, errors = build_gift_data(
            is_gift=True, fulfillment_type="pickup",
            recipient_name="", recipient_phone="",
            gift_message="Para a vovó", hide_values=True,
        )
        self.assertEqual(errors, {})
        self.assertEqual(data["is_gift"], True)
        self.assertNotIn("recipient", data)
        self.assertEqual(data["gift_message"], "Para a vovó")
        self.assertEqual(data["gift_hide_values"], True)

    def test_pickup_keeps_recipient_when_complete(self) -> None:
        data, errors = build_gift_data(
            is_gift=True, fulfillment_type="pickup",
            recipient_name="Maria", recipient_phone="43999990000",
        )
        self.assertEqual(errors, {})
        self.assertEqual(data["recipient"], {"name": "Maria", "phone": "+5543999990000"})


def _make_gift_session(channel_ref: str = "web") -> tuple[str, str]:
    channel = Channel.objects.get_or_create(
        ref=channel_ref,
        defaults={"name": channel_ref.capitalize(), "is_active": True},
    )[0]
    session_key = generate_session_key()
    Session.objects.create(
        session_key=session_key,
        channel_ref=channel.ref,
        state="open",
        pricing_policy="fixed",
        edit_policy="open",
    )
    from shopman.offerman.models import Product

    Product.objects.get_or_create(
        sku="GIFT-CAKE",
        defaults={
            "name": "Bolo Presente",
            "base_price_q": 5000,
            "is_published": True,
            "is_sellable": True,
        },
    )
    ModifyService.modify_session(
        session_key=session_key,
        channel_ref=channel.ref,
        ops=[{"op": "add_line", "sku": "GIFT-CAKE", "qty": 1, "unit_price_q": 5000}],
    )
    return session_key, channel.ref


class GiftPropagationContractTests(TestCase):
    """Session→Order: CommitService propaga as chaves de presente, íntegras."""

    def setUp(self) -> None:
        super().setUp()
        Shop.objects.create(name="Test Shop", brand_name="Test")

    def test_gift_propagates_to_order_data(self) -> None:
        session_key, channel_ref = _make_gift_session()
        result = checkout_service.process(
            session_key=session_key,
            channel_ref=channel_ref,
            data={
                "customer": {"name": "Pablo", "phone": "5543999887766"},
                "fulfillment_type": "pickup",
                "is_gift": True,
                "recipient": {"name": "Maria Silva", "phone": "5543999990000"},
                "gift_message": "Feliz aniversário!",
                "gift_hide_values": True,
            },
            idempotency_key="gift-test-1",
        )
        order = Order.objects.get(ref=result.order_ref)
        self.assertEqual(order.data["is_gift"], True)
        self.assertEqual(order.data["recipient"], {"name": "Maria Silva", "phone": "5543999990000"})
        self.assertEqual(order.data["gift_message"], "Feliz aniversário!")
        self.assertEqual(order.data["gift_hide_values"], True)
        # Cobrança/identidade continuam do comprador — recipient não sobrescreve.
        self.assertEqual(order.data["customer"]["phone"], "5543999887766")

    def test_non_gift_has_no_gift_keys(self) -> None:
        session_key, channel_ref = _make_gift_session()
        result = checkout_service.process(
            session_key=session_key,
            channel_ref=channel_ref,
            data={
                "customer": {"name": "Pablo", "phone": "5543999887766"},
                "fulfillment_type": "pickup",
            },
            idempotency_key="gift-test-2",
        )
        order = Order.objects.get(ref=result.order_ref)
        self.assertNotIn("is_gift", order.data)
        self.assertNotIn("recipient", order.data)
        self.assertNotIn("gift_message", order.data)
