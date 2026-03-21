"""
Tests for Manychat integration: service + webhook.

Service tests (6 scenarios):
1. New subscriber → creates Customer + identifiers
2. Existing by Manychat ID → updates without duplicating
3. Existing by phone → links Manychat ID
4. Existing by email → links Manychat ID
5. Partial data (only Manychat ID)
6. Phone normalization

Webhook tests (4 scenarios):
7. Valid POST with HMAC → 200 + customer created
8. Invalid/missing HMAC → 401
9. Duplicate event (replay) → 200 + "duplicate"
10. Partial data → 200 + customer created
"""

import hashlib
import hmac
import json

import pytest
from django.test import RequestFactory

from shopman.attending.contrib.manychat.service import ManychatService
from shopman.attending.contrib.manychat.views import ManychatWebhookView
from shopman.attending.contrib.identifiers.models import CustomerIdentifier, IdentifierType
from shopman.attending.models import Customer


# ═══════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════

WEBHOOK_SECRET = "test-webhook-secret-12345"


@pytest.fixture(autouse=True)
def _enable_db(db):
    """Enable DB access for all tests."""


@pytest.fixture
def factory():
    return RequestFactory()


@pytest.fixture
def subscriber_data():
    """Full Manychat subscriber payload."""
    return {
        "id": "mc-subscriber-001",
        "first_name": "Maria",
        "last_name": "Silva",
        "phone": "+5511999887766",
        "email": "maria@example.com",
    }


@pytest.fixture
def subscriber_partial():
    """Minimal Manychat subscriber (ID only)."""
    return {
        "id": "mc-subscriber-minimal",
    }


@pytest.fixture
def existing_customer(db):
    """Customer already in the database."""
    return Customer.objects.create(
        ref="EXISTING-001",
        first_name="João",
        last_name="Oliveira",
        email="joao@example.com",
        phone="5511988776655",
    )


# ═══════════════════════════════════════════════════════════════════
# Service Tests
# ═══════════════════════════════════════════════════════════════════


class TestManychatServiceSync:
    """ManychatService.sync_subscriber() scenarios."""

    def test_new_subscriber_creates_customer(self, subscriber_data):
        """Scenario 1: New subscriber → creates Customer + identifiers."""
        customer, created = ManychatService.sync_subscriber(subscriber_data)

        assert created is True
        assert customer.pk is not None
        assert customer.first_name == "Maria"
        assert customer.last_name == "Silva"
        assert customer.ref.startswith("MC-")

        # Verify Manychat identifier was created
        assert CustomerIdentifier.objects.filter(
            customer=customer,
            identifier_type=IdentifierType.MANYCHAT,
            identifier_value="mc-subscriber-001",
        ).exists()

    def test_existing_by_manychat_id_updates(self, subscriber_data):
        """Scenario 2: Existing by Manychat ID → updates, no duplicate."""
        customer1, created1 = ManychatService.sync_subscriber(subscriber_data)
        assert created1 is True

        # Second sync — should find by Manychat ID
        subscriber_data["first_name"] = "Maria Updated"
        customer2, created2 = ManychatService.sync_subscriber(subscriber_data)

        assert created2 is False
        assert customer2.pk == customer1.pk
        # Only 1 customer total
        assert Customer.objects.filter(ref=customer1.ref).count() == 1

    def test_existing_by_phone_links_manychat(self, existing_customer):
        """Scenario 3: Existing by phone → links Manychat ID."""
        # Add phone identifier to existing customer
        CustomerIdentifier.objects.create(
            customer=existing_customer,
            identifier_type=IdentifierType.PHONE,
            identifier_value="5511988776655",
            source_system="manual",
        )

        data = {
            "id": "mc-link-phone-001",
            "first_name": "João",
            "phone": "5511988776655",
        }
        customer, created = ManychatService.sync_subscriber(data)

        assert created is False
        assert customer.pk == existing_customer.pk

        # Manychat ID now linked
        assert CustomerIdentifier.objects.filter(
            customer=existing_customer,
            identifier_type=IdentifierType.MANYCHAT,
            identifier_value="mc-link-phone-001",
        ).exists()

    def test_existing_by_email_links_manychat(self, existing_customer):
        """Scenario 4: Existing by email → links Manychat ID."""
        CustomerIdentifier.objects.create(
            customer=existing_customer,
            identifier_type=IdentifierType.EMAIL,
            identifier_value="joao@example.com",
            source_system="manual",
        )

        data = {
            "id": "mc-link-email-001",
            "first_name": "João",
            "email": "joao@example.com",
        }
        customer, created = ManychatService.sync_subscriber(data)

        assert created is False
        assert customer.pk == existing_customer.pk

    def test_partial_data_only_manychat_id(self, subscriber_partial):
        """Scenario 5: Minimal data (only ID) → still creates customer."""
        customer, created = ManychatService.sync_subscriber(subscriber_partial)

        assert created is True
        assert customer.pk is not None
        assert customer.ref.startswith("MC-")

    def test_phone_normalization(self):
        """Scenario 6: Phone is normalized before matching."""
        data = {
            "id": "mc-phone-norm-001",
            "first_name": "Ana",
            "phone": "(11) 99988-7766",
        }
        customer, created = ManychatService.sync_subscriber(data)
        assert created is True

        # Verify normalized phone is stored
        phone_ids = CustomerIdentifier.objects.filter(
            customer=customer,
            identifier_type=IdentifierType.PHONE,
        )
        assert phone_ids.exists()
        # Should be normalized (digits only, possibly with country code)
        stored_phone = phone_ids.first().identifier_value
        assert "(" not in stored_phone
        assert " " not in stored_phone
        assert "-" not in stored_phone


# ═══════════════════════════════════════════════════════════════════
# Webhook Tests
# ═══════════════════════════════════════════════════════════════════


def _make_signature(body: bytes, secret: str) -> str:
    """Generate HMAC-SHA256 signature for webhook payload."""
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _make_webhook_request(factory, body: bytes, signature: str = ""):
    """Build a POST request with JSON body and signature header."""
    request = factory.post(
        "/manychat/webhook/",
        data=body,
        content_type="application/json",
    )
    if signature:
        request.META["HTTP_X_HUB_SIGNATURE_256"] = f"sha256={signature}"
    return request


class TestManychatWebhook:
    """ManychatWebhookView POST scenarios."""

    @pytest.fixture(autouse=True)
    def _set_webhook_secret(self, settings):
        settings.MANYCHAT_WEBHOOK_SECRET = WEBHOOK_SECRET

    def test_valid_post_creates_customer(self, factory):
        """Scenario 7: Valid POST with HMAC → 200 + customer created."""
        payload = {
            "id": "evt-001",
            "subscriber": {
                "id": "mc-webhook-001",
                "first_name": "Webhook",
                "last_name": "Test",
                "phone": "+5511999001122",
            },
        }
        body = json.dumps(payload).encode()
        sig = _make_signature(body, WEBHOOK_SECRET)
        request = _make_webhook_request(factory, body, sig)

        response = ManychatWebhookView.as_view()(request)

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["status"] == "created"
        assert data["customer_ref"].startswith("MC-")

        # Customer actually exists
        assert Customer.objects.filter(ref=data["customer_ref"]).exists()

    def test_invalid_hmac_returns_401(self, factory):
        """Scenario 8: Invalid HMAC → 401."""
        body = json.dumps({"id": "evt-bad", "subscriber": {"id": "mc-bad"}}).encode()
        request = _make_webhook_request(factory, body, "invalid-signature")

        response = ManychatWebhookView.as_view()(request)

        assert response.status_code == 401

    def test_missing_hmac_returns_401(self, factory):
        """Scenario 8b: Missing HMAC → 401."""
        body = json.dumps({"id": "evt-nosig"}).encode()
        request = _make_webhook_request(factory, body, "")

        response = ManychatWebhookView.as_view()(request)

        assert response.status_code == 401

    def test_duplicate_event_returns_200_duplicate(self, factory):
        """Scenario 9: Duplicate event (replay) → 200 + 'duplicate'."""
        payload = {
            "id": "evt-replay-001",
            "subscriber": {
                "id": "mc-replay-001",
                "first_name": "Replay",
            },
        }
        body = json.dumps(payload).encode()
        sig = _make_signature(body, WEBHOOK_SECRET)

        # First request — succeeds
        request1 = _make_webhook_request(factory, body, sig)
        response1 = ManychatWebhookView.as_view()(request1)
        assert response1.status_code == 200
        data1 = json.loads(response1.content)
        assert data1["status"] == "created"

        # Second request — same event ID → duplicate
        request2 = _make_webhook_request(factory, body, sig)
        response2 = ManychatWebhookView.as_view()(request2)
        assert response2.status_code == 200
        data2 = json.loads(response2.content)
        assert data2["status"] == "duplicate"

    def test_partial_subscriber_data(self, factory):
        """Scenario 10: Minimal subscriber data → still creates customer."""
        payload = {
            "id": "evt-partial-001",
            "subscriber": {
                "id": "mc-partial-001",
            },
        }
        body = json.dumps(payload).encode()
        sig = _make_signature(body, WEBHOOK_SECRET)
        request = _make_webhook_request(factory, body, sig)

        response = ManychatWebhookView.as_view()(request)

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["status"] == "created"
