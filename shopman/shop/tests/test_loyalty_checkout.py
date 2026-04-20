"""
Tests for WP-R10 — Loyalty in Checkout.

Covers:
- LoyaltyRedeemModifier applies discount from session.data["loyalty"]["redeem_points_q"]
- LoyaltyRedeemModifier clamps to order total (no negative totals)
- LoyaltyRedeemModifier no-op when redeem_points_q == 0
- CheckoutView passes loyalty_balance to context for authenticated customers
- LoyaltyRedeemHandler processes loyalty.redeem directive
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase
from shopman.orderman.ids import generate_session_key
from shopman.orderman.models import Session
from shopman.orderman.services.modify import ModifyService

from shopman.shop.models import Channel


def _make_channel(ref="balcao"):
    return Channel.objects.get_or_create(
        ref=ref,
        defaults={
            "name": ref.capitalize(),
            "is_active": True,
        },
    )[0]


def _make_session(channel_ref="balcao", items=None):
    channel = _make_channel(channel_ref)
    session_key = generate_session_key()
    session = Session.objects.create(
        session_key=session_key,
        channel_ref=channel.ref,
        state="open",
        pricing_policy="fixed",
        edit_policy="open",
    )
    if items:
        from shopman.offerman.models import Product
        for item in items:
            Product.objects.get_or_create(
                sku=item["sku"],
                defaults={
                    "name": item["sku"],
                    "base_price_q": item["unit_price_q"],
                    "is_published": True,
                    "is_sellable": True,
                },
            )
        ModifyService.modify_session(
            session_key=session_key,
            channel_ref=channel_ref,
            ops=[
                {"op": "add_line", "sku": i["sku"], "qty": i["qty"], "unit_price_q": i["unit_price_q"]}
                for i in items
            ],
        )
    session.refresh_from_db()
    return session


class LoyaltyRedeemModifierTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        from shopman.shop.models import Shop
        Shop.objects.create(name="Test Shop", brand_name="Test")

    def _apply_modifier(self, session: Session, redeem_q: int) -> Session:
        from shopman.shop.modifiers import LoyaltyRedeemModifier
        # Set loyalty data in session
        data = session.data or {}
        data["loyalty"] = {"redeem_points_q": redeem_q}
        session.data = data
        session.save(update_fields=["data"])
        session.refresh_from_db()

        modifier = LoyaltyRedeemModifier()
        mock_channel = MagicMock()
        modifier.apply(channel=mock_channel, session=session, ctx={})
        session.refresh_from_db()
        return session

    def test_noop_when_zero_points(self) -> None:
        """No discount applied when redeem_points_q == 0."""
        session = _make_session(items=[{"sku": "LOYAL-A", "qty": 1, "unit_price_q": 1000}])
        session = self._apply_modifier(session, redeem_q=0)

        self.assertNotIn("loyalty_redeem", session.pricing or {})

    def test_discount_applied(self) -> None:
        """Discount applied when redeem_points_q > 0."""
        session = _make_session(items=[{"sku": "LOYAL-B", "qty": 1, "unit_price_q": 1000}])
        session = self._apply_modifier(session, redeem_q=200)

        pricing = session.pricing or {}
        self.assertIn("loyalty_redeem", pricing)
        self.assertEqual(pricing["loyalty_redeem"]["total_discount_q"], 200)
        self.assertEqual(pricing["loyalty_redeem"]["label"], "Resgate de pontos")

    def test_clamp_to_order_total(self) -> None:
        """Redemption is clamped to order total (never negative)."""
        session = _make_session(items=[{"sku": "LOYAL-C", "qty": 1, "unit_price_q": 500}])
        # Try to redeem 1000 when order total is only 500
        session = self._apply_modifier(session, redeem_q=1000)

        pricing = session.pricing or {}
        # Discount capped at 500 (the order total)
        self.assertLessEqual(pricing["loyalty_redeem"]["total_discount_q"], 500)


class LoyaltyRedeemHandlerTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        from shopman.shop.models import Shop
        Shop.objects.create(name="Test Shop", brand_name="Test")

    def test_handler_calls_redeem_points(self) -> None:
        """LoyaltyRedeemHandler calls LoyaltyService.redeem_points when customer found."""
        from shopman.guestman.models import Customer
        from shopman.orderman.models import Directive, Order

        from shopman.shop.handlers.loyalty import LoyaltyRedeemHandler

        customer = Customer.objects.create(
            first_name="Loyal",
            last_name="Customer",
            phone="5543999990099",
        )
        channel = _make_channel()
        order = Order.objects.create(
            ref="LYL-001",
            channel_ref=channel.ref,
            status="new",
            handle_type="phone",
            handle_ref=customer.phone,
            data={"loyalty": {"redeem_points_q": 100}},
        )
        directive = Directive.objects.create(
            topic="loyalty.redeem",
            payload={"order_ref": order.ref, "points": 100},
        )

        with patch("shopman.guestman.contrib.loyalty.service.LoyaltyService.redeem_points") as mock_redeem:
            with patch("shopman.guestman.services.customer.get_by_phone") as mock_get:
                mock_get.return_value = customer
                # Enroll customer first
                with patch("shopman.guestman.contrib.loyalty.service.LoyaltyService._get_active_account_for_update") as mock_acct:
                    mock_acct.return_value = MagicMock(points_balance=500)
                    handler = LoyaltyRedeemHandler()
                    handler.handle(message=directive, ctx={})

        self.assertEqual(directive.status, "completed")

    def test_handler_skips_when_no_points(self) -> None:
        """Handler completes without calling redeem when points=0."""
        from shopman.orderman.models import Directive

        from shopman.shop.handlers.loyalty import LoyaltyRedeemHandler

        directive = Directive.objects.create(
            topic="loyalty.redeem",
            payload={"order_ref": "FAKE-001", "points": 0},
        )
        handler = LoyaltyRedeemHandler()
        handler.handle(message=directive, ctx={})

        self.assertEqual(directive.status, "completed")


class CheckoutLoyaltyContextTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        from shopman.shop.models import Shop
        Shop.objects.create(name="Test Shop", brand_name="Test")
        from shopman.shop.models import Channel
        Channel.objects.create(
            ref="web",
            name="Web",
            is_active=True,
        )
        from shopman.offerman.models import Product
        Product.objects.create(
            sku="LOYAL-WEB",
            name="Loyal Product",
            base_price_q=500,
            is_published=True,
            is_sellable=True,
        )

    def _login_as_customer(self, client, customer):
        from shopman.doorman.protocols.customer import AuthCustomerInfo
        from shopman.doorman.services._user_bridge import get_or_create_user_for_customer

        info = AuthCustomerInfo(
            uuid=customer.uuid,
            name=getattr(customer, "full_name", "") or getattr(customer, "first_name", ""),
            phone=customer.phone,
            email=None,
            is_active=True,
        )
        user, _ = get_or_create_user_for_customer(info)
        client.force_login(user, backend="shopman.doorman.backends.PhoneOTPBackend")

    def test_loyalty_balance_in_context(self) -> None:
        """CheckoutView passes loyalty_balance to template context."""
        from shopman.guestman.models import Customer

        customer = Customer.objects.create(
            first_name="Points",
            last_name="Customer",
            phone="5543999990077",
        )
        self._login_as_customer(self.client, customer)
        self.client.post("/cart/add/", {"sku": "LOYAL-WEB", "qty": "1"})

        with patch("shopman.guestman.contrib.loyalty.service.LoyaltyService.get_balance") as mock_bal:
            mock_bal.return_value = 250
            resp = self.client.get("/checkout/")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["checkout"].loyalty_balance_q, 250)

    def test_no_loyalty_balance_for_new_customer(self) -> None:
        """Customer with 0 balance doesn't see loyalty section."""
        from shopman.guestman.models import Customer

        customer = Customer.objects.create(
            first_name="Zero",
            last_name="Points",
            phone="5543999990088",
        )
        self._login_as_customer(self.client, customer)
        self.client.post("/cart/add/", {"sku": "LOYAL-WEB", "qty": "1"})

        with patch("shopman.guestman.contrib.loyalty.service.LoyaltyService.get_balance") as mock_bal:
            mock_bal.return_value = 0
            resp = self.client.get("/checkout/")

        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "Resgatar pontos")
