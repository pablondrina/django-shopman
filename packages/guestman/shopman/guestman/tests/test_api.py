"""Tests for Guestman REST API (SPEC-002)."""
from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from shopman.guestman.models import Customer, CustomerAddress, CustomerGroup


@pytest.fixture
def user(db):
    return User.objects.create_user(username="agent", password="testpass123")


@pytest.fixture
def api_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def anon_client():
    return APIClient()


# ─── Data fixtures ───────────────────────────────────────────────────────────


@pytest.fixture
def group_regular(db):
    return CustomerGroup.objects.create(ref="regular", name="Regular", is_default=True, priority=0)


@pytest.fixture
def group_vip(db):
    return CustomerGroup.objects.create(ref="vip", name="VIP", listing_ref="vip", priority=10)


@pytest.fixture
def customer(db, group_regular):
    return Customer.objects.create(
        ref="CUST-001",
        first_name="John",
        last_name="Doe",
        email="john@example.com",
        phone="+5543999999999",
        group=group_regular,
    )


@pytest.fixture
def customer_vip(db, group_vip):
    return Customer.objects.create(
        ref="CUST-VIP",
        first_name="Jane",
        last_name="VIP",
        email="jane@example.com",
        phone="+5543888888888",
        group=group_vip,
    )


@pytest.fixture
def customer_inactive(db, group_regular):
    return Customer.objects.create(
        ref="CUST-GONE",
        first_name="Gone",
        last_name="User",
        phone="+5543777777777",
        group=group_regular,
        is_active=False,
    )


@pytest.fixture
def customer_address(db, customer):
    return CustomerAddress.objects.create(
        customer=customer,
        label="home",
        formatted_address="Rua Example, 123 - Centro, Londrina - PR",
        route="Rua Example",
        street_number="123",
        neighborhood="Centro",
        city="Londrina",
        state_code="PR",
        latitude=Decimal("-23.3045"),
        longitude=Decimal("-51.1696"),
        complement="Apto 42",
        delivery_instructions="Portao branco",
        is_default=True,
    )


@pytest.fixture
def customer_insight(db, customer):
    from shopman.guestman.contrib.insights.models import CustomerInsight

    return CustomerInsight.objects.create(
        customer=customer,
        total_orders=5,
        total_spent_q=25000,
        average_ticket_q=5000,
        days_since_last_order=10,
        rfm_recency=4,
        rfm_frequency=3,
        rfm_monetary=3,
        rfm_segment="loyal_customer",
        churn_risk=Decimal("0.2"),
        favorite_products=[{"sku": "CROISSANT", "name": "Croissant", "qty": 10}],
    )


@pytest.fixture
def customer_preference(db, customer):
    from shopman.guestman.contrib.preferences.models import CustomerPreference

    return CustomerPreference.objects.create(
        customer=customer,
        category="dietary",
        key="lactose_free",
        value=True,
        preference_type="restriction",
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  CUSTOMERS
# ═══════════════════════════════════════════════════════════════════════════════


class TestCustomerList:
    """GET /api/customers/customers/"""

    def test_list_active_customers(self, api_client, customer, customer_vip):
        resp = api_client.get("/api/customers/customers/")
        assert resp.status_code == 200
        codes = {c["ref"] for c in resp.data["results"]}
        assert "CUST-001" in codes
        assert "CUST-VIP" in codes

    def test_excludes_inactive(self, api_client, customer, customer_inactive):
        resp = api_client.get("/api/customers/customers/")
        codes = {c["ref"] for c in resp.data["results"]}
        assert "CUST-001" in codes
        assert "CUST-GONE" not in codes

    def test_filter_by_group(self, api_client, customer, customer_vip):
        resp = api_client.get("/api/customers/customers/", {"group": "vip"})
        codes = {c["ref"] for c in resp.data["results"]}
        assert "CUST-VIP" in codes
        assert "CUST-001" not in codes

    def test_search_by_name(self, api_client, customer, customer_vip):
        resp = api_client.get("/api/customers/customers/", {"search": "John"})
        codes = {c["ref"] for c in resp.data["results"]}
        assert "CUST-001" in codes
        assert "CUST-VIP" not in codes

    def test_search_by_phone(self, api_client, customer):
        resp = api_client.get("/api/customers/customers/", {"search": "999999999"})
        codes = {c["ref"] for c in resp.data["results"]}
        assert "CUST-001" in codes

    def test_search_by_email(self, api_client, customer):
        resp = api_client.get("/api/customers/customers/", {"search": "john@example"})
        codes = {c["ref"] for c in resp.data["results"]}
        assert "CUST-001" in codes

    def test_pagination(self, api_client, customer):
        resp = api_client.get("/api/customers/customers/")
        assert "count" in resp.data
        assert "results" in resp.data

    def test_serializer_fields(self, api_client, customer):
        resp = api_client.get("/api/customers/customers/")
        cust = resp.data["results"][0]
        expected = {
            "ref", "uuid", "first_name", "last_name", "customer_type",
            "phone", "phone_display", "email", "group_name", "listing_ref", "is_active",
        }
        assert set(cust.keys()) == expected


class TestCustomerDetail:
    """GET /api/customers/customers/{ref}/"""

    def test_retrieve_by_code(self, api_client, customer):
        resp = api_client.get(f"/api/customers/customers/{customer.ref}/")
        assert resp.status_code == 200
        assert resp.data["ref"] == "CUST-001"
        assert resp.data["first_name"] == "John"

    def test_detail_includes_contacts(self, api_client, customer):
        resp = api_client.get(f"/api/customers/customers/{customer.ref}/")
        assert "contacts" in resp.data
        assert isinstance(resp.data["contacts"], list)

    def test_detail_includes_addresses(self, api_client, customer, customer_address):
        resp = api_client.get(f"/api/customers/customers/{customer.ref}/")
        assert "addresses" in resp.data
        assert len(resp.data["addresses"]) == 1
        addr = resp.data["addresses"][0]
        assert addr["formatted_address"] == "Rua Example, 123 - Centro, Londrina - PR"
        assert addr["is_default"] is True

    def test_detail_includes_notes(self, api_client, customer):
        resp = api_client.get(f"/api/customers/customers/{customer.ref}/")
        assert "notes" in resp.data

    def test_404_for_nonexistent(self, api_client):
        resp = api_client.get("/api/customers/customers/NOPE/")
        assert resp.status_code == 404

    def test_404_for_inactive(self, api_client, customer_inactive):
        resp = api_client.get(f"/api/customers/customers/{customer_inactive.ref}/")
        assert resp.status_code == 404


class TestCustomerCreate:
    """POST /api/customers/customers/"""

    def test_create_customer(self, api_client, group_regular):
        resp = api_client.post(
            "/api/customers/customers/",
            {"first_name": "Maria", "phone": "+5543911111111"},
            format="json",
        )
        assert resp.status_code == 201
        assert resp.data["first_name"] == "Maria"
        assert resp.data["ref"].startswith("CUST-")

    def test_create_with_all_fields(self, api_client, group_regular):
        resp = api_client.post(
            "/api/customers/customers/",
            {
                "first_name": "Carlos",
                "last_name": "Silva",
                "phone": "+5543922222222",
                "email": "carlos@example.com",
                "customer_type": "individual",
                "group_ref": "regular",
            },
            format="json",
        )
        assert resp.status_code == 201
        assert resp.data["last_name"] == "Silva"
        assert resp.data["email"] == "carlos@example.com"

    def test_create_generates_contact_point(self, api_client, group_regular):
        resp = api_client.post(
            "/api/customers/customers/",
            {"first_name": "Ana", "phone": "+5543933333333"},
            format="json",
        )
        assert resp.status_code == 201
        # Verify contact point was created via detail endpoint
        ref = resp.data["ref"]
        detail = api_client.get(f"/api/customers/customers/{ref}/")
        assert len(detail.data["contacts"]) >= 1

    def test_create_requires_phone(self, api_client, group_regular):
        resp = api_client.post(
            "/api/customers/customers/",
            {"first_name": "NoPhone"},
            format="json",
        )
        assert resp.status_code == 400

    def test_create_requires_first_name(self, api_client, group_regular):
        resp = api_client.post(
            "/api/customers/customers/",
            {"phone": "+5543944444444"},
            format="json",
        )
        assert resp.status_code == 400


class TestCustomerUpdate:
    """PATCH /api/customers/customers/{ref}/"""

    def test_update_first_name(self, api_client, customer):
        resp = api_client.patch(
            f"/api/customers/customers/{customer.ref}/",
            {"first_name": "Jonathan"},
            format="json",
        )
        assert resp.status_code == 200
        assert resp.data["first_name"] == "Jonathan"

    def test_update_notes(self, api_client, customer):
        resp = api_client.patch(
            f"/api/customers/customers/{customer.ref}/",
            {"notes": "VIP treatment"},
            format="json",
        )
        assert resp.status_code == 200

    def test_delete_not_allowed(self, api_client, customer):
        resp = api_client.delete(f"/api/customers/customers/{customer.ref}/")
        assert resp.status_code == 405


# ═══════════════════════════════════════════════════════════════════════════════
#  CONTACTS & ADDRESSES
# ═══════════════════════════════════════════════════════════════════════════════


class TestContacts:
    """GET /api/customers/customers/{ref}/contacts/"""

    def test_list_contacts(self, api_client, customer):
        resp = api_client.get(f"/api/customers/customers/{customer.ref}/contacts/")
        assert resp.status_code == 200
        assert isinstance(resp.data, list)

    def test_contact_fields(self, api_client, customer):
        resp = api_client.get(f"/api/customers/customers/{customer.ref}/contacts/")
        if resp.data:
            contact = resp.data[0]
            assert "type" in contact
            assert "value_normalized" in contact
            assert "is_primary" in contact
            assert "is_verified" in contact


class TestAddresses:
    """GET/POST /api/customers/customers/{ref}/addresses/"""

    def test_list_addresses(self, api_client, customer, customer_address):
        resp = api_client.get(f"/api/customers/customers/{customer.ref}/addresses/")
        assert resp.status_code == 200
        assert len(resp.data) == 1

    def test_create_address(self, api_client, customer):
        resp = api_client.post(
            f"/api/customers/customers/{customer.ref}/addresses/",
            {
                "label": "work",
                "formatted_address": "Av. Higienopolis, 500 - Centro, Londrina - PR",
                "complement": "Sala 10",
                "is_default": False,
            },
            format="json",
        )
        assert resp.status_code == 201
        assert resp.data["formatted_address"] == "Av. Higienopolis, 500 - Centro, Londrina - PR"

    def test_address_fields(self, api_client, customer, customer_address):
        resp = api_client.get(f"/api/customers/customers/{customer.ref}/addresses/")
        addr = resp.data[0]
        expected = {
            "id", "label", "label_custom", "formatted_address", "short_address",
            "display_label", "complement", "delivery_instructions",
            "latitude", "longitude", "is_default",
        }
        assert set(addr.keys()) == expected


# ═══════════════════════════════════════════════════════════════════════════════
#  LOOKUP
# ═══════════════════════════════════════════════════════════════════════════════


class TestLookup:
    """GET /api/customers/lookup/"""

    def test_lookup_by_phone(self, api_client, customer):
        resp = api_client.get("/api/customers/lookup/", {"phone": "+5543999999999"})
        assert resp.status_code == 200
        assert resp.data["ref"] == "CUST-001"

    def test_lookup_by_email(self, api_client, customer):
        resp = api_client.get("/api/customers/lookup/", {"email": "john@example.com"})
        assert resp.status_code == 200
        assert resp.data["ref"] == "CUST-001"

    def test_lookup_not_found(self, api_client, customer):
        resp = api_client.get("/api/customers/lookup/", {"phone": "+5543000000000"})
        assert resp.status_code == 404

    def test_lookup_requires_param(self, api_client):
        resp = api_client.get("/api/customers/lookup/")
        assert resp.status_code == 400

    def test_lookup_returns_serializer_fields(self, api_client, customer):
        resp = api_client.get("/api/customers/lookup/", {"phone": "+5543999999999"})
        expected = {
            "ref", "uuid", "first_name", "last_name", "customer_type",
            "phone", "phone_display", "email", "group_name", "listing_ref", "is_active",
        }
        assert set(resp.data.keys()) == expected


# ═══════════════════════════════════════════════════════════════════════════════
#  INSIGHTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestInsights:
    """GET /api/customers/customers/{ref}/insights/"""

    def test_get_insights(self, api_client, customer, customer_insight):
        resp = api_client.get(f"/api/customers/customers/{customer.ref}/insights/")
        assert resp.status_code == 200
        assert resp.data["total_orders"] == 5
        assert resp.data["total_spent_q"] == 25000
        assert resp.data["rfm_segment"] == "loyal_customer"
        assert resp.data["is_vip"] is True
        assert resp.data["is_at_risk"] is False

    def test_insights_not_found(self, api_client, customer_vip):
        resp = api_client.get(f"/api/customers/customers/{customer_vip.ref}/insights/")
        assert resp.status_code == 404


class TestInsightsSummary:
    """GET /api/customers/insights/summary/"""

    def test_summary(self, api_client, customer, customer_insight):
        resp = api_client.get("/api/customers/insights/summary/")
        assert resp.status_code == 200
        assert resp.data["total_customers"] == 1
        assert resp.data["total_vip"] == 1
        assert resp.data["total_at_risk"] == 0
        assert "segments_distribution" in resp.data
        assert resp.data["segments_distribution"]["loyal_customer"] == 1

    def test_summary_empty(self, api_client):
        resp = api_client.get("/api/customers/insights/summary/")
        assert resp.status_code == 200
        assert resp.data["total_customers"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
#  PREFERENCES
# ═══════════════════════════════════════════════════════════════════════════════


class TestPreferences:
    """GET/PATCH /api/customers/customers/{ref}/preferences/"""

    def test_get_preferences(self, api_client, customer, customer_preference):
        resp = api_client.get(f"/api/customers/customers/{customer.ref}/preferences/")
        assert resp.status_code == 200
        assert "dietary" in resp.data
        assert resp.data["dietary"]["lactose_free"] is True

    def test_get_preferences_empty(self, api_client, customer):
        resp = api_client.get(f"/api/customers/customers/{customer.ref}/preferences/")
        assert resp.status_code == 200
        assert resp.data == {}

    def test_update_preferences(self, api_client, customer):
        resp = api_client.patch(
            f"/api/customers/customers/{customer.ref}/preferences/",
            {"flavor": {"chocolate": True, "vanilla": False}},
            format="json",
        )
        assert resp.status_code == 200
        assert resp.data["flavor"]["chocolate"] is True
        assert resp.data["flavor"]["vanilla"] is False


# ═══════════════════════════════════════════════════════════════════════════════
#  AUTHENTICATION
# ═══════════════════════════════════════════════════════════════════════════════


class TestAuthentication:
    """All endpoints require authentication."""

    def test_customers_requires_auth(self, anon_client, customer):
        resp = anon_client.get("/api/customers/customers/")
        assert resp.status_code == 403

    def test_lookup_requires_auth(self, anon_client, customer):
        resp = anon_client.get("/api/customers/lookup/", {"phone": "+5543999999999"})
        assert resp.status_code == 403

    def test_insights_summary_requires_auth(self, anon_client):
        resp = anon_client.get("/api/customers/insights/summary/")
        assert resp.status_code == 403

    def test_customer_create_requires_auth(self, anon_client):
        resp = anon_client.post(
            "/api/customers/customers/",
            {"first_name": "X", "phone": "+5543900000000"},
            format="json",
        )
        assert resp.status_code == 403
