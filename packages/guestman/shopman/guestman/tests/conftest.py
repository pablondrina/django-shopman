"""Pytest fixtures for Customers tests."""

from decimal import Decimal

import pytest

from shopman.guestman.models import (
    Customer,
    CustomerGroup,
    CustomerAddress,
)

# Import contrib models only if available
try:
    from shopman.guestman.contrib.preferences.models import CustomerPreference
except ImportError:
    CustomerPreference = None

try:
    from shopman.guestman.contrib.insights.models import CustomerInsight
except ImportError:
    CustomerInsight = None


@pytest.fixture
def group_regular(db):
    """Create regular customer group."""
    return CustomerGroup.objects.create(
        ref="regular",
        name="Regular",
        is_default=True,
        priority=0,
    )


@pytest.fixture
def group_vip(db):
    """Create VIP customer group."""
    return CustomerGroup.objects.create(
        ref="vip",
        name="VIP",
        listing_ref="vip",
        priority=10,
    )


@pytest.fixture
def customer(db, group_regular):
    """Create a test customer."""
    return Customer.objects.create(
        ref="CUST-001",
        first_name="John",
        last_name="Doe",
        email="john@example.com",
        phone="11999999999",
        group=group_regular,
    )


@pytest.fixture
def customer_vip(db, group_vip):
    """Create a VIP customer."""
    return Customer.objects.create(
        ref="CUST-VIP",
        first_name="Jane",
        last_name="VIP",
        email="jane@example.com",
        phone="11888888888",
        group=group_vip,
    )


@pytest.fixture
def customer_address(db, customer):
    """Create a customer address."""
    return CustomerAddress.objects.create(
        customer=customer,
        label="home",
        formatted_address="Rua Example, 123 - Centro, Sao Paulo - SP, 01234-567",
        route="Rua Example",
        street_number="123",
        neighborhood="Centro",
        city="Sao Paulo",
        state="Sao Paulo",
        state_code="SP",
        postal_code="01234-567",
        latitude=Decimal("-23.5505"),
        longitude=Decimal("-46.6333"),
        is_default=True,
        is_verified=True,
    )


@pytest.fixture
def customer_preference(db, customer):
    """Create a customer preference (requires shopman.guestman.contrib.preferences)."""
    if CustomerPreference is None:
        pytest.skip("CustomerPreference not available - install shopman.guestman.contrib.preferences")
    return CustomerPreference.objects.create(
        customer=customer,
        category="dietary",
        key="lactose_free",
        value=True,
        preference_type="restriction",
    )


@pytest.fixture
def customer_insight(db, customer):
    """Create a customer insight (requires shopman.guestman.contrib.insights)."""
    if CustomerInsight is None:
        pytest.skip("CustomerInsight not available - install shopman.guestman.contrib.insights")
    return CustomerInsight.objects.create(
        customer=customer,
        total_orders=5,
        total_spent_q=25000,
        average_ticket_q=5000,
        rfm_recency=4,
        rfm_frequency=3,
        rfm_monetary=3,
        rfm_segment="loyal_customer",
        churn_risk=Decimal("0.2"),
    )
