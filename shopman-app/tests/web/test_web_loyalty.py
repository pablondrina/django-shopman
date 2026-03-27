"""Tests for WP-E2: Loyalty na UI."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from shopman.customers.contrib.loyalty.service import LoyaltyService
from shopman.customers.models import Customer
from shopman.ordering.models import Channel, Directive, Order

# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def loyalty_customer(db):
    return Customer.objects.create(
        ref="LOYAL-001",
        first_name="Maria",
        last_name="Santos",
        phone="5543991111111",
    )


@pytest.fixture
def loyalty_account(loyalty_customer):
    account = LoyaltyService.enroll(loyalty_customer.ref)
    LoyaltyService.earn_points(
        customer_ref=loyalty_customer.ref,
        points=150,
        description="Seed inicial",
        reference="seed:test",
        created_by="test",
    )
    return account


@pytest.fixture
def completed_order(db, loyalty_customer):
    channel = Channel.objects.create(
        ref="web-test",
        name="Web Test",
        listing_ref="balcao",
        pricing_policy="external",
        edit_policy="open",
        config={},
    )
    return Order.objects.create(
        ref="ORD-LOYAL-001",
        channel=channel,
        status="completed",
        total_q=5000,  # R$ 50,00 → 50 points
        handle_type="phone",
        handle_ref=loyalty_customer.phone,
        data={},
    )


# ── Handler tests ─────────────────────────────────────────────────────


class TestLoyaltyEarnHandler:
    def test_earn_handler_gives_points(self, db, loyalty_customer, completed_order):
        """Handler should award points based on order total."""
        from channels.handlers.loyalty import LoyaltyEarnHandler

        # Enroll first
        LoyaltyService.enroll(loyalty_customer.ref)

        directive = Directive.objects.create(
            topic="loyalty.earn",
            payload={"order_ref": completed_order.ref},
        )

        handler = LoyaltyEarnHandler()
        handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        assert directive.status == "completed"

        account = LoyaltyService.get_account(loyalty_customer.ref)
        assert account.points_balance == 50  # 5000 // 100

    def test_earn_handler_auto_enrolls(self, db, loyalty_customer, completed_order):
        """Handler should auto-enroll customer if not yet enrolled."""
        from channels.handlers.loyalty import LoyaltyEarnHandler

        # Do NOT enroll first
        assert LoyaltyService.get_account(loyalty_customer.ref) is None

        directive = Directive.objects.create(
            topic="loyalty.earn",
            payload={"order_ref": completed_order.ref},
        )

        handler = LoyaltyEarnHandler()
        handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        assert directive.status == "completed"

        account = LoyaltyService.get_account(loyalty_customer.ref)
        assert account is not None
        assert account.points_balance == 50

    def test_earn_handler_skips_without_customer(self, db):
        """Handler should skip gracefully if no customer found."""
        from channels.handlers.loyalty import LoyaltyEarnHandler

        channel = Channel.objects.create(
            ref="test-ch",
            name="Test",
            listing_ref="balcao",
            pricing_policy="external",
            edit_policy="open",
            config={},
        )
        order = Order.objects.create(
            ref="ORD-NOCUST",
            channel=channel,
            status="completed",
            total_q=3000,
            handle_type="phone",
            handle_ref="",  # No handle
            data={},
        )

        directive = Directive.objects.create(
            topic="loyalty.earn",
            payload={"order_ref": order.ref},
        )

        handler = LoyaltyEarnHandler()
        handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        assert directive.status == "completed"

    def test_earn_handler_skips_missing_order(self, db):
        """Handler should fail if order not found."""
        from channels.handlers.loyalty import LoyaltyEarnHandler

        directive = Directive.objects.create(
            topic="loyalty.earn",
            payload={"order_ref": "DOES-NOT-EXIST"},
        )

        handler = LoyaltyEarnHandler()
        handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        assert directive.status == "failed"


# ── Account UI tests ──────────────────────────────────────────────────


def _login_as_customer(client, customer):
    """Log in the Django test client as a customer via Django auth."""
    from shopman.auth.protocols.customer import AuthCustomerInfo
    from shopman.auth.services._user_bridge import get_or_create_user_for_customer

    info = AuthCustomerInfo(
        uuid=customer.uuid,
        name=customer.name,
        phone=customer.phone,
        email=getattr(customer, "email", None) or None,
        is_active=True,
    )
    user, _ = get_or_create_user_for_customer(info)
    client.force_login(user, backend="shopman.auth.backends.PhoneOTPBackend")
    return user


class TestAccountLoyaltyUI:
    def test_account_shows_loyalty_section(self, client, loyalty_customer, loyalty_account):
        """Account page should show loyalty info when customer has an account."""
        _login_as_customer(client, loyalty_customer)

        response = client.get("/minha-conta/")
        assert response.status_code == 200
        content = response.content.decode()
        assert "Fidelidade" in content
        assert "pontos disponíveis" in content

    def test_account_shows_loyalty_via_get(self, client, loyalty_customer, loyalty_account):
        """Loyalty section should appear when authenticated via GET."""
        _login_as_customer(client, loyalty_customer)

        response = client.get("/minha-conta/")
        assert response.status_code == 200
        content = response.content.decode()
        assert "Fidelidade" in content

    def test_account_hides_loyalty_if_not_enrolled(self, client, customer):
        """No loyalty section if customer has no loyalty account."""
        _login_as_customer(client, customer)

        response = client.get("/minha-conta/")
        assert response.status_code == 200
        content = response.content.decode()
        assert "Fidelidade" not in content

    def test_account_hides_loyalty_if_not_installed(self, client, customer):
        """Loyalty section should not appear if loyalty app is not installed."""
        with patch(
            "channels.web.views.account._get_loyalty_data",
            return_value=(None, []),
        ):
            _login_as_customer(client, customer)

            response = client.get("/minha-conta/")
            assert response.status_code == 200
            content = response.content.decode()
            assert "Fidelidade" not in content
