"""Tests for Customers models."""

from decimal import Decimal

import pytest

# Core models
from shopman.guestman.models import (
    Customer,
    CustomerGroup,
    CustomerAddress,
    AddressLabel,
)

# Contrib models
from shopman.guestman.contrib.identifiers.models import CustomerIdentifier, IdentifierType
from shopman.guestman.contrib.preferences.models import CustomerPreference
from shopman.guestman.contrib.insights.models import CustomerInsight


pytestmark = pytest.mark.django_db


class TestCustomerGroup:
    """Tests for CustomerGroup model."""

    def test_create_group(self, db):
        """Test group creation."""
        group = CustomerGroup.objects.create(
            ref="atacado",
            name="Atacado",
            listing_ref="atacado",
            priority=5,
        )
        assert group.ref == "atacado"
        assert group.listing_ref == "atacado"

    def test_only_one_default(self, group_regular, db):
        """Test only one default group allowed."""
        new_default = CustomerGroup.objects.create(
            ref="new-default",
            name="New Default",
            is_default=True,
        )
        group_regular.refresh_from_db()

        assert new_default.is_default is True
        assert group_regular.is_default is False


class TestCustomer:
    """Tests for Customer model."""

    def test_create_customer(self, customer):
        """Test customer creation."""
        assert customer.ref == "CUST-001"
        assert customer.name == "John Doe"
        assert customer.is_active is True

    def test_name_property(self, db, group_regular):
        """Test name property concatenation."""
        cust = Customer.objects.create(
            ref="TEST",
            first_name="First",
            last_name="Last",
            group=group_regular,
        )
        assert cust.name == "First Last"

        cust_no_last = Customer.objects.create(
            ref="TEST2",
            first_name="OnlyFirst",
            group=group_regular,
        )
        assert cust_no_last.name == "OnlyFirst"

    def test_listing_ref_from_group(self, customer_vip, group_vip):
        """Test listing_ref comes from group."""
        assert customer_vip.listing_ref == "vip"

    def test_default_group_assigned(self, db, group_regular):
        """Test default group assigned on save."""
        cust = Customer.objects.create(
            ref="NEW-CUST",
            first_name="New",
        )
        assert cust.group == group_regular

    def test_default_address_property(self, customer, customer_address):
        """Test default_address property."""
        assert customer.default_address == customer_address


class TestCustomerIdentifier:
    """Tests for CustomerIdentifier model."""

    def test_create_identifier(self, customer):
        """Test identifier creation."""
        ident = CustomerIdentifier.objects.create(
            customer=customer,
            identifier_type=IdentifierType.PHONE,
            identifier_value="5511999999999",
        )
        assert ident.identifier_value == "+5511999999999"

    def test_phone_normalization(self, customer):
        """Test phone number normalization."""
        ident = CustomerIdentifier.objects.create(
            customer=customer,
            identifier_type=IdentifierType.PHONE,
            identifier_value="(11) 98765-4321",
        )
        assert ident.identifier_value == "+5511987654321"

    def test_email_normalization(self, customer):
        """Test email normalization."""
        ident = CustomerIdentifier.objects.create(
            customer=customer,
            identifier_type=IdentifierType.EMAIL,
            identifier_value="  JOHN@Example.COM  ",
        )
        assert ident.identifier_value == "john@example.com"

    def test_unique_identifier(self, customer, customer_vip):
        """Test identifier uniqueness."""
        CustomerIdentifier.objects.create(
            customer=customer,
            identifier_type=IdentifierType.EMAIL,
            identifier_value="unique@example.com",
        )

        # Same identifier for different customer should fail
        with pytest.raises(Exception):  # IntegrityError
            CustomerIdentifier.objects.create(
                customer=customer_vip,
                identifier_type=IdentifierType.EMAIL,
                identifier_value="unique@example.com",
            )


class TestCustomerAddress:
    """Tests for CustomerAddress model."""

    def test_create_address(self, customer_address):
        """Test address creation."""
        assert customer_address.label == "home"
        assert customer_address.is_default is True
        assert customer_address.is_verified is True

    def test_display_label_standard(self, customer_address):
        """Test display_label for standard labels."""
        # Accept either English or Portuguese translation
        assert customer_address.display_label in ("Home", "Casa")

    def test_display_label_custom(self, customer):
        """Test display_label for custom labels."""
        addr = CustomerAddress.objects.create(
            customer=customer,
            label=AddressLabel.OTHER,
            label_custom="Grandma's house",
            formatted_address="Some address",
        )
        assert addr.display_label == "Grandma's house"

    def test_only_one_default(self, customer, customer_address):
        """Test only one default address per customer."""
        new_addr = CustomerAddress.objects.create(
            customer=customer,
            label="work",
            formatted_address="Work address",
            is_default=True,
        )
        customer_address.refresh_from_db()

        assert new_addr.is_default is True
        assert customer_address.is_default is False


class TestCustomerPreference:
    """Tests for CustomerPreference model."""

    def test_create_preference(self, customer_preference):
        """Test preference creation."""
        assert customer_preference.category == "dietary"
        assert customer_preference.key == "lactose_free"
        assert customer_preference.value is True

    def test_unique_per_customer_category_key(self, customer, customer_preference):
        """Test uniqueness constraint."""
        with pytest.raises(Exception):  # IntegrityError
            CustomerPreference.objects.create(
                customer=customer,
                category="dietary",
                key="lactose_free",
                value=False,
            )


class TestCustomerInsight:
    """Tests for CustomerInsight model."""

    def test_create_insight(self, customer_insight):
        """Test insight creation."""
        assert customer_insight.total_orders == 5
        assert customer_insight.total_spent == Decimal("250.00")
        assert customer_insight.average_ticket == Decimal("50.00")

    def test_is_vip_property(self, customer_insight):
        """Test is_vip property."""
        assert customer_insight.is_vip is True

        customer_insight.rfm_segment = "regular"
        assert customer_insight.is_vip is False

    def test_is_at_risk_property(self, customer_insight):
        """Test is_at_risk property."""
        assert customer_insight.is_at_risk is False

        customer_insight.churn_risk = Decimal("0.8")
        assert customer_insight.is_at_risk is True


# Note: OrderSnapshot not yet implemented.
# See spec 005-customers.md for planned model.
