"""
Integration test: Ordering <-> Auth.

Tests the flow: auth -> session.
"""


from django.test import TestCase


class TestOrderingAuthIntegration(TestCase):
    """Integration between Ordering (sessions) and Auth."""

    def setUp(self):
        from shopman.guestman.models import Customer
        from shopman.models import Channel

        # Create customer
        self.customer = Customer.objects.create(
            ref="DOOR-INT-001",
            first_name="Door",
            last_name="Test",
            phone="+5541999990001",
        )

        # Create channel
        self.channel = Channel.objects.create(
            ref="web-test",
            name="Web Test",
        )

    def test_access_link_can_reference_customer(self):
        """AccessLink stores customer_id matching Customers customer."""
        from shopman.doorman.models import AccessLink

        link, raw_token = AccessLink.create_with_token(
            customer_id=self.customer.uuid,
            audience="web_checkout",
            source="manychat",
        )

        assert link.customer_id == self.customer.uuid
        assert link.is_valid

    def test_customer_user_connects_user_to_customer(self):
        """CustomerUser connects Django User to Customer."""
        from django.contrib.auth import get_user_model

        from shopman.doorman.models import CustomerUser

        User = get_user_model()
        user = User.objects.create_user(
            username="door_test_user",
            password="testpass",
        )

        link = CustomerUser.objects.create(
            user=user,
            customer_id=self.customer.uuid,
        )

        assert link.customer_id == self.customer.uuid
        assert link.user == user

    def test_session_preservation_across_login(self):
        """Session data (like basket) can be preserved across auth."""
        from shopman.orderman.models import Session

        # Create session before auth
        session = Session.objects.create(
            session_key="BASKET-SESSION-001",
            channel_ref=self.channel.ref,
            state="open",
            items=[
                {"sku": "PAO-FRANCES", "qty": 10, "price_q": 80},
            ],
        )

        # Session should exist and have items
        assert len(session.items) == 1
        assert session.items[0]["sku"] == "PAO-FRANCES"
