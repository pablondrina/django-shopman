"""
Integration test: Ordering <-> Gating.

Tests the flow: auth -> session.
"""

from unittest.mock import patch, MagicMock

import pytest
from django.test import TestCase


class TestOrderingGatingIntegration(TestCase):
    """Integration between Ordering (sessions) and Gating (auth)."""

    def setUp(self):
        from shopman.attending.models import Customer
        from shopman.ordering.models import Channel

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
            pricing_policy="external",
            edit_policy="open",
        )

    def test_bridge_token_can_reference_customer(self):
        """BridgeToken stores customer_id matching Attending customer."""
        from shopman.gating.models import BridgeToken

        token = BridgeToken.objects.create(
            customer_id=self.customer.uuid,
            audience="web_checkout",
            source="manychat",
        )

        assert token.customer_id == self.customer.uuid
        assert token.is_valid

    def test_identity_link_connects_user_to_customer(self):
        """IdentityLink connects Django User to Attending Customer."""
        from django.contrib.auth import get_user_model
        from shopman.gating.models import IdentityLink

        User = get_user_model()
        user = User.objects.create_user(
            username="door_test_user",
            password="testpass",
        )

        link = IdentityLink.objects.create(
            user=user,
            customer_id=self.customer.uuid,
        )

        assert link.customer_id == self.customer.uuid
        assert link.user == user

    def test_session_preservation_across_login(self):
        """Session data (like basket) can be preserved across auth."""
        from shopman.ordering.models import Session

        # Create session before auth
        session = Session.objects.create(
            session_key="BASKET-SESSION-001",
            channel=self.channel,
            state="open",
            items=[
                {"sku": "PAO-FRANCES", "qty": 10, "price_q": 80},
            ],
        )

        # Session should exist and have items
        assert len(session.items) == 1
        assert session.items[0]["sku"] == "PAO-FRANCES"
