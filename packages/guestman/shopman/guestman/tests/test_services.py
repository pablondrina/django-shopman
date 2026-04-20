"""Tests for Guestman services."""


import pytest
from django.utils import timezone
from shopman.guestman.contrib.identifiers import IdentifierService

# Contrib models
from shopman.guestman.contrib.identifiers.models import CustomerIdentifier, IdentifierType
from shopman.guestman.contrib.insights import InsightService

# Contrib services
from shopman.guestman.contrib.preferences import PreferenceService
from shopman.guestman.services import address as address_service

# Core services
from shopman.guestman.services import customer as customer_service
from shopman.guestman.services import identity as identity_service

pytestmark = pytest.mark.django_db


class TestCustomerService:
    """Tests for customer service."""

    def test_get_by_ref(self, customer):
        """Test getting customer by ref."""
        result = customer_service.get("CUST-001")
        assert result.ref == "CUST-001"

    def test_get_nonexistent(self, db):
        """Test getting nonexistent customer."""
        result = customer_service.get("NONEXISTENT")
        assert result is None

    def test_get_by_document(self, db, group_regular):
        """Test getting customer by document."""
        from shopman.guestman.models import Customer

        cust = Customer.objects.create(
            ref="DOC-TEST",
            first_name="Doc",
            document="12345678901",
            group=group_regular,
        )

        result = customer_service.get_by_document("123.456.789-01")
        assert result == cust

    def test_validate_valid_customer(self, customer, customer_address):
        """Test validating valid customer."""
        result = customer_service.validate("CUST-001")

        assert result.valid is True
        assert result.name == "John Doe"
        assert result.default_address is not None
        # Accept either English or Portuguese translation
        assert result.default_address["label"] in ("Home", "Casa")

    def test_validate_invalid_customer(self, db):
        """Test validating invalid customer."""
        result = customer_service.validate("NONEXISTENT")

        assert result.valid is False
        assert result.error_code == "CUSTOMER_NOT_FOUND"

    def test_get_listing_ref(self, customer_vip):
        """Test getting listing code."""
        result = customer_service.get_listing_ref("CUST-VIP")
        assert result == "vip"

    def test_get_by_email_multiple_returns_most_recent(self, db, group_regular):
        """get_by_email with duplicates returns most recently updated."""
        from shopman.guestman.models import Customer

        # Create customers without email to avoid ContactPoint uniqueness,
        # then set email directly on the cache field via SQL update.
        c1 = Customer.objects.create(
            ref="DUP-EMAIL-1",
            first_name="First",
            group=group_regular,
        )
        c2 = Customer.objects.create(
            ref="DUP-EMAIL-2",
            first_name="Second",
            group=group_regular,
        )
        # Set duplicate email directly (bypassing _sync_contact_points)
        Customer.objects.filter(pk=c1.pk).update(email="dup@example.com")
        Customer.objects.filter(pk=c2.pk).update(
            email="dup@example.com",
            updated_at=timezone.now(),
        )

        result = customer_service.get_by_email("dup@example.com")
        assert result is not None
        assert result.ref == "DUP-EMAIL-2"

    def test_get_by_phone_prefers_contact_point_source_of_truth(self, db, group_regular):
        """Phone lookup must work even when the cache field is stale."""
        from shopman.guestman.models import ContactPoint, Customer

        customer = Customer.objects.create(
            ref="CONTACT-PHONE-1",
            first_name="Phone",
            group=group_regular,
        )
        ContactPoint.objects.create(
            customer=customer,
            type=ContactPoint.Type.WHATSAPP,
            value_normalized="+5541991112222",
            is_primary=True,
            is_verified=True,
        )

        result = customer_service.get_by_phone("+5541991112222")
        assert result is not None
        assert result.ref == "CONTACT-PHONE-1"

    def test_get_by_email_prefers_contact_point_source_of_truth(self, db, group_regular):
        """Email lookup must work even when the cache field is stale."""
        from shopman.guestman.models import ContactPoint, Customer

        customer = Customer.objects.create(
            ref="CONTACT-EMAIL-1",
            first_name="Email",
            group=group_regular,
        )
        ContactPoint.objects.create(
            customer=customer,
            type=ContactPoint.Type.EMAIL,
            value_normalized="contact@example.com",
            is_primary=True,
            is_verified=True,
        )

        result = customer_service.get_by_email("contact@example.com")
        assert result is not None
        assert result.ref == "CONTACT-EMAIL-1"

    def test_search(self, customer, customer_vip):
        """Test search functionality."""
        results = customer_service.search("John")
        assert len(results) == 1
        assert results[0].ref == "CUST-001"

    def test_search_with_offset(self, customer, customer_vip):
        """Test search with offset for pagination."""
        page1 = customer_service.search("", limit=1, offset=0)
        page2 = customer_service.search("", limit=1, offset=1)

        assert len(page1) == 1
        assert len(page2) == 1
        assert page1[0].ref != page2[0].ref

    def test_create_customer(self, group_regular):
        """Test creating customer."""
        cust = customer_service.create(
            ref="NEW-001",
            first_name="New",
            last_name="Customer",
            email="new@example.com",
            phone="11111111111",
        )
        assert cust.ref == "NEW-001"
        assert cust.group == group_regular


class TestAddressService:
    """Tests for address service."""

    def test_addresses(self, customer, customer_address):
        """Test listing addresses."""
        result = address_service.addresses("CUST-001")
        assert len(result) == 1

    def test_default_address(self, customer, customer_address):
        """Test getting default address."""
        result = address_service.default_address("CUST-001")
        assert result == customer_address

    def test_add_address(self, customer):
        """Test adding address."""
        addr = address_service.add_address(
            "CUST-001",
            label="work",
            formatted_address="Av Work, 456",
            complement="10th floor",
        )
        assert addr.label == "work"
        assert addr.complement == "10th floor"

    def test_set_default_address(self, customer, customer_address):
        """Test setting default address."""
        new_addr = address_service.add_address(
            "CUST-001",
            label="work",
            formatted_address="Work address",
        )

        address_service.set_default_address("CUST-001", new_addr.id)
        new_addr.refresh_from_db()
        customer_address.refresh_from_db()

        assert new_addr.is_default is True
        assert customer_address.is_default is False

    def test_suggest_address_prefers_default(self, customer):
        """Default address wins over anything else in the cascade."""
        address_service.add_address(
            "CUST-001",
            label="work",
            formatted_address="Work, 1",
        )
        default = address_service.add_address(
            "CUST-001",
            label="home",
            formatted_address="Home, 1",
            is_default=True,
        )
        suggested = address_service.suggest_address("CUST-001")
        assert suggested is not None
        assert suggested.id == default.id

    def test_suggest_address_geo_compatible(self, customer):
        """When no default exists, a near-by saved address wins the cascade."""
        address_service.add_address(
            "CUST-001",
            label="work",
            formatted_address="Far, 1",
            coordinates=(-23.00, -51.00),  # ~80km from target
        )
        near = address_service.add_address(
            "CUST-001",
            label="home",
            formatted_address="Near, 1",
            coordinates=(-23.310001, -51.160001),  # ~0.2m from target
        )
        # Target ~same as `near` → geo cascade returns it.
        result = address_service.suggest_address(
            "CUST-001", location=(-23.31, -51.16),
        )
        assert result is not None
        assert result.id == near.id

    def test_suggest_address_fallback_to_latest(self, customer):
        """With no default and no location, the cascade returns the latest."""
        address_service.add_address(
            "CUST-001",
            label="home",
            formatted_address="Old, 1",
        )
        latest = address_service.add_address(
            "CUST-001",
            label="work",
            formatted_address="Recent, 1",
        )
        result = address_service.suggest_address("CUST-001")
        assert result is not None
        assert result.id == latest.id

    def test_suggest_address_empty_returns_none(self, customer):
        """No saved addresses → cascade returns None."""
        assert address_service.suggest_address("CUST-001") is None

    def test_update_address_accepts_coordinates_and_place_id(self, customer, customer_address):
        """update_address() must propagate lat/lng/place_id (not just components)."""
        addr = address_service.update_address(
            "CUST-001",
            customer_address.id,
            latitude=-23.55,
            longitude=-46.63,
            place_id="ChIJ-example",
        )
        assert addr.place_id == "ChIJ-example"
        assert float(addr.latitude) == -23.55
        assert float(addr.longitude) == -46.63


class TestPreferenceService:
    """Tests for preference service."""

    def test_get_preferences(self, customer, customer_preference):
        """Test listing preferences."""
        result = PreferenceService.get_preferences("CUST-001")
        assert len(result) == 1

    def test_get_preferences_dict(self, customer, customer_preference):
        """Test getting preferences by category."""
        result = PreferenceService.get_preferences_dict("CUST-001")
        assert "dietary" in result
        assert result["dietary"]["lactose_free"] is True

    def test_get_preference(self, customer, customer_preference):
        """Test getting specific preference."""
        result = PreferenceService.get_preference("CUST-001", "dietary", "lactose_free")
        assert result is True

    def test_set_preference(self, customer):
        """Test setting preference."""
        pref = PreferenceService.set_preference(
            "CUST-001",
            category="flavor",
            key="favorite_bread",
            value="croissant",
        )
        assert pref.value == "croissant"

    def test_get_restrictions(self, customer, customer_preference):
        """Test getting restrictions."""
        # customer_preference fixture already creates a restriction
        # Add another one to test listing multiple
        from shopman.guestman.contrib.preferences.models import PreferenceType
        PreferenceService.set_preference(
            "CUST-001",
            category="dietary",
            key="gluten_free",
            value=True,
            preference_type=PreferenceType.RESTRICTION,
        )
        restrictions = PreferenceService.get_restrictions("CUST-001")
        # customer_preference + gluten_free = 2 restrictions
        assert len(restrictions) == 2
        keys = {r.key for r in restrictions}
        assert "lactose_free" in keys
        assert "gluten_free" in keys


class TestInsightService:
    """Tests for insight service."""

    def test_get_insight(self, customer, customer_insight):
        """Test getting insight."""
        result = InsightService.get_insight("CUST-001")
        assert result.total_orders == 5

    def test_recalculate_no_backend(self, customer):
        """Test recalculating without backend (resets metrics)."""
        result = InsightService.recalculate("CUST-001")

        # Without an order backend, metrics should be reset to 0
        assert result.total_orders == 0
        assert result.total_spent_q == 0


class TestIdentifierService:
    """Tests for identifier service."""

    def test_find_by_identifier(self, customer):
        """Test finding by identifier."""
        CustomerIdentifier.objects.create(
            customer=customer,
            identifier_type=IdentifierType.EMAIL,
            identifier_value="john@example.com",
        )

        result = IdentifierService.find_by_identifier(IdentifierType.EMAIL, "john@example.com")
        assert result == customer

    def test_find_or_create_new(self, group_regular):
        """Test find_or_create creates new customer."""
        cust, created = IdentifierService.find_or_create_customer(
            identifier_type=IdentifierType.EMAIL,
            identifier_value="new@example.com",
            defaults={
                "first_name": "New",
                "last_name": "Person",
            },
        )

        assert created is True
        assert cust.first_name == "New"
        # Check identifier was created
        assert cust.identifiers.count() == 1

    def test_find_or_create_existing(self, customer):
        """Test find_or_create finds existing customer."""
        CustomerIdentifier.objects.create(
            customer=customer,
            identifier_type=IdentifierType.EMAIL,
            identifier_value="john@example.com",
        )

        cust, created = IdentifierService.find_or_create_customer(
            identifier_type=IdentifierType.EMAIL,
            identifier_value="john@example.com",
            defaults={"first_name": "Different"},
        )

        assert created is False
        assert cust == customer

    def test_add_identifier(self, customer):
        """Test adding identifier."""
        ident = IdentifierService.add_identifier(
            customer_ref="CUST-001",
            identifier_type=IdentifierType.INSTAGRAM,
            identifier_value="@johndoe",
        )
        assert ident.identifier_value == "johndoe"
        assert ident.customer == customer

    def test_get_identifiers(self, customer):
        """Test getting all identifiers for customer."""
        CustomerIdentifier.objects.create(
            customer=customer,
            identifier_type=IdentifierType.EMAIL,
            identifier_value="john@example.com",
        )
        CustomerIdentifier.objects.create(
            customer=customer,
            identifier_type=IdentifierType.PHONE,
            identifier_value="5511999999999",
        )

        identifiers = IdentifierService.get_identifiers("CUST-001")
        assert len(identifiers) == 2

    def test_ensure_identifier_reuses_existing(self, customer):
        ident1 = IdentifierService.ensure_identifier(
            customer_ref="CUST-001",
            identifier_type=IdentifierType.WHATSAPP,
            identifier_value="+5511999999999",
            is_primary=True,
            source_system="doorman",
        )
        ident2 = IdentifierService.ensure_identifier(
            customer_ref="CUST-001",
            identifier_type=IdentifierType.WHATSAPP,
            identifier_value="+55 11 99999-9999",
            is_primary=True,
            source_system="doorman",
        )

        assert ident1.pk == ident2.pk
        assert CustomerIdentifier.objects.filter(customer=customer).count() == 1


class TestIdentityService:
    """Tests for identity service."""

    def test_ensure_external_identity_reuses_existing(self, customer):
        identity = identity_service.ensure_external_identity(
            customer,
            provider="manychat",
            external_id="mc-123",
            metadata={"flow": "welcome"},
        )

        reused = identity_service.ensure_external_identity(
            customer,
            provider="manychat",
            external_id="mc-123",
            metadata={"flow": "welcome"},
        )

        assert reused.id == identity.id
        assert customer.external_identities.count() == 1
