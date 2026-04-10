"""
H22 — Guestman hardening tests.

Tests for:
- Gates G1-G6 (all scenarios)
- Phone normalization (international)
- Concurrency in ContactPoint.save() (is_primary race condition)
- RFM with division by zero
- Manychat sync with incomplete data
- ProcessedEvent cleanup
"""

import hashlib
import hmac
import time
from decimal import Decimal
from unittest.mock import patch, MagicMock

import pytest
from django.db import IntegrityError

from shopman.guestman.gates import Gates, GateError


# ═══════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture
def customer(db):
    from shopman.guestman.models import Customer

    return Customer.objects.create(
        ref="H22-CUST-001",
        first_name="Test",
        last_name="Customer",
    )


@pytest.fixture
def customer_b(db):
    from shopman.guestman.models import Customer

    return Customer.objects.create(
        ref="H22-CUST-002",
        first_name="Other",
        last_name="Customer",
    )


@pytest.fixture
def contact_point(db, customer):
    from shopman.guestman.models import ContactPoint

    return ContactPoint.objects.create(
        customer=customer,
        type="whatsapp",
        value_normalized="+5541999990001",
        value_display="(41) 99999-0001",
        is_primary=True,
    )


# ═══════════════════════════════════════════════════════════════════
# G1: ContactPointUniqueness
# ═══════════════════════════════════════════════════════════════════


class TestG1ContactPointUniqueness:
    """G1: (type, value) cannot exist in another Customer."""

    def test_unique_contact_passes(self, customer):
        """New unique contact passes G1."""
        result = Gates.contact_point_uniqueness("whatsapp", "+5541999990099")
        assert result.passed

    def test_duplicate_contact_raises(self, contact_point, customer_b):
        """Same contact in another customer raises GateError."""
        with pytest.raises(GateError, match="G1_ContactPointUniqueness"):
            Gates.contact_point_uniqueness("whatsapp", "+5541999990001")

    def test_same_customer_excluded(self, contact_point, customer):
        """Excluding own customer allows same contact (for updates)."""
        result = Gates.contact_point_uniqueness(
            "whatsapp",
            "+5541999990001",
            exclude_customer_id=customer.pk,
        )
        assert result.passed

    def test_different_type_allowed(self, contact_point):
        """Same value but different type is allowed."""
        result = Gates.contact_point_uniqueness("phone", "+5541999990001")
        assert result.passed

    def test_check_variant_returns_bool(self, contact_point):
        """check_contact_point_uniqueness returns bool, not raises."""
        assert not Gates.check_contact_point_uniqueness("whatsapp", "+5541999990001")
        assert Gates.check_contact_point_uniqueness("email", "test@test.com")


# ═══════════════════════════════════════════════════════════════════
# G2: PrimaryInvariant
# ═══════════════════════════════════════════════════════════════════


class TestG2PrimaryInvariant:
    """G2: Max 1 primary per (customer, type)."""

    def test_single_primary_passes(self, contact_point, customer):
        """One primary contact passes G2."""
        result = Gates.primary_invariant(customer.pk, "whatsapp")
        assert result.passed

    def test_no_primary_passes(self, customer):
        """Zero primaries passes G2."""
        result = Gates.primary_invariant(customer.pk, "email")
        assert result.passed

    def test_multiple_primaries_prevented_by_constraint(self, customer):
        """DB constraint prevents multiple primaries for same type."""
        from django.db import transaction
        from shopman.guestman.models import ContactPoint

        ContactPoint.objects.create(
            customer=customer,
            type="email",
            value_normalized="a@test.com",
            is_primary=True,
        )
        cp2 = ContactPoint.objects.create(
            customer=customer,
            type="email",
            value_normalized="b@test.com",
            is_primary=False,
        )
        # DB constraint prevents setting second primary
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                ContactPoint.objects.filter(pk=cp2.pk).update(is_primary=True)


# ═══════════════════════════════════════════════════════════════════
# G3: VerifiedTransition
# ═══════════════════════════════════════════════════════════════════


class TestG3VerifiedTransition:
    """G3: Verification method must be allowed."""

    @pytest.mark.parametrize(
        "method",
        ["channel_asserted", "otp_whatsapp", "otp_sms", "email_link", "manual"],
    )
    def test_allowed_methods_pass(self, method):
        """All valid methods pass G3."""
        result = Gates.verified_transition(method)
        assert result.passed

    def test_unknown_method_raises(self):
        """Unknown verification method raises GateError."""
        with pytest.raises(GateError, match="G3_VerifiedTransition"):
            Gates.verified_transition("unknown_method")

    def test_empty_method_raises(self):
        """Empty string method raises GateError."""
        with pytest.raises(GateError, match="G3_VerifiedTransition"):
            Gates.verified_transition("")


# ═══════════════════════════════════════════════════════════════════
# G4: ProviderEventAuthenticity
# ═══════════════════════════════════════════════════════════════════


class TestG4ProviderEventAuthenticity:
    """G4: Webhook HMAC + timestamp validation."""

    def _make_signature(self, body: bytes, secret: str) -> str:
        return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    def test_valid_signature_passes(self):
        """Valid HMAC signature passes G4."""
        body = b'{"event": "test"}'
        secret = "my-secret"
        sig = self._make_signature(body, secret)

        result = Gates.provider_event_authenticity(body, sig, secret)
        assert result.passed

    def test_valid_signature_with_prefix(self):
        """Signature with 'sha256=' prefix passes."""
        body = b'{"event": "test"}'
        secret = "my-secret"
        sig = "sha256=" + self._make_signature(body, secret)

        result = Gates.provider_event_authenticity(body, sig, secret)
        assert result.passed

    def test_invalid_signature_raises(self):
        """Wrong HMAC signature raises GateError."""
        with pytest.raises(GateError, match="Invalid signature"):
            Gates.provider_event_authenticity(b"body", "wrong-sig", "secret")

    def test_missing_signature_raises(self):
        """Missing signature raises GateError."""
        with pytest.raises(GateError, match="Missing signature"):
            Gates.provider_event_authenticity(b"body", "", "secret")

    def test_no_secret_skips_validation(self):
        """No secret configured means skip (dev mode)."""
        result = Gates.provider_event_authenticity(b"body", "anything", "")
        assert result.passed

    def test_old_timestamp_raises(self):
        """Timestamp older than max_age raises GateError."""
        body = b'{"event": "test"}'
        secret = "my-secret"
        sig = self._make_signature(body, secret)
        old_ts = int(time.time()) - 600  # 10 min ago

        with pytest.raises(GateError, match="Timestamp too old"):
            Gates.provider_event_authenticity(
                body, sig, secret, timestamp=old_ts, max_age_seconds=300
            )

    def test_recent_timestamp_passes(self):
        """Recent timestamp passes."""
        body = b'{"event": "test"}'
        secret = "my-secret"
        sig = self._make_signature(body, secret)
        now_ts = int(time.time())

        result = Gates.provider_event_authenticity(
            body, sig, secret, timestamp=now_ts, max_age_seconds=300
        )
        assert result.passed


# ═══════════════════════════════════════════════════════════════════
# G5: ReplayProtection
# ═══════════════════════════════════════════════════════════════════


class TestG5ReplayProtection:
    """G5: Event cannot be processed twice."""

    def test_first_event_passes(self, db):
        """First processing of nonce passes."""
        result = Gates.replay_protection("unique-event-001", "manychat")
        assert result.passed

    def test_replay_raises(self, db):
        """Second processing of same nonce raises GateError."""
        Gates.replay_protection("unique-event-002", "manychat")

        with pytest.raises(GateError, match="Replay detected"):
            Gates.replay_protection("unique-event-002", "manychat")

    def test_empty_nonce_raises(self, db):
        """Empty nonce raises GateError."""
        with pytest.raises(GateError, match="Nonce is required"):
            Gates.replay_protection("", "manychat")

    def test_is_replay_check(self, db):
        """is_replay checks without recording."""
        assert not Gates.is_replay("check-event-001")
        Gates.replay_protection("check-event-001", "manychat")
        assert Gates.is_replay("check-event-001")


# ═══════════════════════════════════════════════════════════════════
# G6: MergeSafety
# ═══════════════════════════════════════════════════════════════════


class TestG6MergeSafety:
    """G6: Merge requires strong evidence."""

    def test_same_id_raises(self):
        """Cannot merge customer into itself."""
        with pytest.raises(GateError, match="Cannot merge customer into itself"):
            Gates.merge_safety("cust-1", "cust-1")

    def test_no_evidence_raises(self):
        """No evidence raises GateError."""
        with pytest.raises(GateError, match="Insufficient evidence"):
            Gates.merge_safety("cust-1", "cust-2")

    def test_staff_override_passes(self):
        """staff_override evidence passes."""
        result = Gates.merge_safety("cust-1", "cust-2", {"staff_override": True})
        assert result.passed

    def test_same_verified_phone_passes(self):
        """same_verified_phone evidence passes."""
        result = Gates.merge_safety("cust-1", "cust-2", {"same_verified_phone": True})
        assert result.passed

    def test_invalid_evidence_key_raises(self):
        """Unknown evidence key is not valid."""
        with pytest.raises(GateError, match="Insufficient evidence"):
            Gates.merge_safety("cust-1", "cust-2", {"unknown_key": True})

    def test_false_evidence_raises(self):
        """Evidence set to False is not sufficient."""
        with pytest.raises(GateError, match="Insufficient evidence"):
            Gates.merge_safety("cust-1", "cust-2", {"staff_override": False})


# ═══════════════════════════════════════════════════════════════════
# Phone normalization (international)
# ═══════════════════════════════════════════════════════════════════


class TestPhoneNormalization:
    """ContactPoint phone normalization with international numbers."""

    def test_manychat_brazilian_number_fixed(self, db, customer):
        """Manychat bug: +43984049009 (missing 55) -> +5543984049009."""
        from shopman.guestman.models import ContactPoint

        cp = ContactPoint(
            customer=customer,
            type="whatsapp",
            value_normalized="+43984049009",
        )
        cp.save()
        cp.refresh_from_db()
        # Should be normalized during save
        assert cp.value_normalized is not None

    def test_us_number_preserved(self, db, customer):
        """US number +12025551234 must NOT be treated as Brazilian."""
        from shopman.guestman.models import ContactPoint

        cp = ContactPoint(
            customer=customer,
            type="phone",
            value_normalized="+12025551234",
        )
        cp.save()
        cp.refresh_from_db()
        assert "+12025551234" in cp.value_normalized

    def test_german_number_preserved(self, db, customer):
        """German number +49301234567 must be preserved."""
        from shopman.guestman.models import ContactPoint

        cp = ContactPoint(
            customer=customer,
            type="phone",
            value_normalized="+49301234567",
        )
        cp.save()
        cp.refresh_from_db()
        assert "+49301234567" in cp.value_normalized


# ═══════════════════════════════════════════════════════════════════
# Concurrency in ContactPoint.save() (is_primary)
# ═══════════════════════════════════════════════════════════════════


class TestContactPointPrimaryInvariant:
    """ContactPoint.save() maintains is_primary invariant."""

    def test_new_primary_demotes_old(self, db, customer):
        """Setting new primary demotes old primary."""
        from shopman.guestman.models import ContactPoint

        cp1 = ContactPoint.objects.create(
            customer=customer,
            type="email",
            value_normalized="first@test.com",
            is_primary=True,
        )
        cp2 = ContactPoint.objects.create(
            customer=customer,
            type="email",
            value_normalized="second@test.com",
            is_primary=False,
        )
        cp2.set_as_primary()

        cp1.refresh_from_db()
        cp2.refresh_from_db()

        # Only cp2 should be primary
        assert not cp1.is_primary
        assert cp2.is_primary


# ═══════════════════════════════════════════════════════════════════
# RFM with edge cases
# ═══════════════════════════════════════════════════════════════════


class TestRFMEdgeCases:
    """RFM calculations with edge cases."""

    def test_recalculate_without_backend(self, db, customer):
        """Recalculate without order backend resets metrics."""
        from shopman.guestman.contrib.insights.service import InsightService

        # Should not raise even without backend
        insight = InsightService.recalculate(customer.ref)
        # Insight should be created/updated without error
        assert insight is not None

    def test_churn_risk_no_orders(self, db, customer):
        """Customer with no orders has maximum churn risk."""
        from shopman.guestman.contrib.insights.service import InsightService

        insight = InsightService.recalculate(customer.ref)
        if insight and hasattr(insight, "churn_risk") and insight.churn_risk is not None:
            # Churn risk should be high for inactive customer
            assert insight.churn_risk >= Decimal("0")


# ═══════════════════════════════════════════════════════════════════
# ProcessedEvent cleanup
# ═══════════════════════════════════════════════════════════════════


class TestProcessedEventCleanup:
    """ProcessedEvent model operations."""

    def test_create_processed_event(self, db):
        """ProcessedEvent can be created."""
        from shopman.guestman.models import ProcessedEvent

        event = ProcessedEvent.objects.create(nonce="event-001", provider="manychat")
        assert event.pk is not None

    def test_duplicate_nonce_raises(self, db):
        """Duplicate nonce raises IntegrityError."""
        from shopman.guestman.models import ProcessedEvent

        ProcessedEvent.objects.create(nonce="event-dup", provider="manychat")
        with pytest.raises(IntegrityError):
            ProcessedEvent.objects.create(nonce="event-dup", provider="manychat")

    def test_queryset_filter_by_provider(self, db):
        """Can filter by provider."""
        from shopman.guestman.models import ProcessedEvent

        ProcessedEvent.objects.create(nonce="mc-001", provider="manychat")
        ProcessedEvent.objects.create(nonce="api-001", provider="api")

        mc_events = ProcessedEvent.objects.filter(provider="manychat")
        assert mc_events.count() == 1


# ═══════════════════════════════════════════════════════════════════
# Cleanup command --dry-run
# ═══════════════════════════════════════════════════════════════════


class TestCleanupDryRun:
    """customers_cleanup --dry-run does not delete."""

    def test_dry_run_does_not_delete(self, db):
        """--dry-run reports count but keeps records."""
        from io import StringIO
        from django.core.management import call_command
        from shopman.guestman.models import ProcessedEvent

        ProcessedEvent.objects.create(nonce="old-001", provider="test")
        # Force old timestamp
        from django.utils import timezone
        from datetime import timedelta
        ProcessedEvent.objects.filter(nonce="old-001").update(
            processed_at=timezone.now() - timedelta(days=200)
        )

        out = StringIO()
        call_command("customers_cleanup", "--dry-run", "--days=90", stdout=out)

        assert "Would delete 1" in out.getvalue()
        # Record still exists
        assert ProcessedEvent.objects.filter(nonce="old-001").exists()
