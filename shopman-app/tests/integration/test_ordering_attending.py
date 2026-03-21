"""
Integration test: Ordering <-> Attending.

Tests the flow: customer -> session -> order.
"""

from decimal import Decimal

import pytest
from django.test import TestCase


class TestOrderingAttendingIntegration(TestCase):
    """Integration between Ordering (orders) and Attending (customers)."""

    def setUp(self):
        from shopman.attending.models import Customer, CustomerGroup
        from shopman.ordering.models import Channel, Session

        # Create customer group
        self.group = CustomerGroup.objects.create(
            ref="regular",
            name="Regular",
            is_default=True,
        )

        # Create customer
        self.customer = Customer.objects.create(
            ref="INT-CUST-001",
            first_name="Integration",
            last_name="Test",
            group=self.group,
        )

        # Create channel
        self.channel = Channel.objects.create(
            ref="loja-test",
            name="Loja Test",
            pricing_policy="external",
            edit_policy="open",
        )

    def test_session_with_customer_data(self):
        """Session can store customer reference."""
        from shopman.ordering.models import Session

        session = Session.objects.create(
            session_key="INT-SESSION-001",
            channel=self.channel,
            state="open",
            items=[],
            data={"customer_ref": self.customer.ref},
        )

        assert session.data["customer_ref"] == "INT-CUST-001"

    def test_customer_group_provides_listing_code(self):
        """Customer group can provide listing_code for pricing."""
        self.group.listing_code = "atacado"
        self.group.save()

        assert self.customer.group.listing_code == "atacado"

    def test_customer_lookup_by_ref(self):
        """Customer can be retrieved by ref for session association."""
        from shopman.attending.models import Customer

        found = Customer.objects.filter(ref="INT-CUST-001").first()
        assert found is not None
        assert found.first_name == "Integration"
