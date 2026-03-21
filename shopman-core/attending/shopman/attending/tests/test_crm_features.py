"""
Tests for Micro CRM features:
- Timeline (interaction history)
- Consent (LGPD opt-in/opt-out)
- Loyalty (points/stamps program)
- Customer → ContactPoint sync
- Address null safety
- AttendingError → BaseError inheritance
- InsightService enhancements (LTV, segmentation)
"""

from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from shopman.attending.models import Customer, CustomerGroup, CustomerAddress, ContactPoint
from shopman.attending.exceptions import AttendingError

# Contrib imports
from shopman.attending.contrib.timeline.models import TimelineEvent
from shopman.attending.contrib.timeline.service import TimelineService
from shopman.attending.contrib.consent.models import CommunicationConsent, ConsentStatus
from shopman.attending.contrib.consent.service import ConsentService
from shopman.attending.contrib.loyalty.models import LoyaltyAccount, LoyaltyTransaction
from shopman.attending.contrib.loyalty.service import LoyaltyService
from shopman.attending.contrib.insights.service import InsightService


pytestmark = pytest.mark.django_db


# ═══════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture
def group(db):
    return CustomerGroup.objects.create(
        ref="regular",
        name="Regular",
        is_default=True,
    )


@pytest.fixture
def customer(group):
    return Customer.objects.create(
        ref="CRM-001",
        first_name="Maria",
        last_name="Santos",
        phone="5541999990001",
        email="maria@example.com",
        group=group,
    )


@pytest.fixture
def customer_b(group):
    return Customer.objects.create(
        ref="CRM-002",
        first_name="João",
        last_name="Silva",
        group=group,
    )


# ═══════════════════════════════════════════════════════════════════
# AttendingError → BaseError
# ═══════════════════════════════════════════════════════════════════


class TestAttendingErrorInheritance:
    """AttendingError inherits from shopman.utils.BaseError."""

    def test_inherits_from_base_error(self):
        from shopman.utils.exceptions import BaseError

        err = AttendingError("CUSTOMER_NOT_FOUND")
        assert isinstance(err, BaseError)

    def test_default_messages(self):
        err = AttendingError("CUSTOMER_NOT_FOUND")
        assert err.message == "Customer not found"
        assert err.code == "CUSTOMER_NOT_FOUND"

    def test_custom_message(self):
        err = AttendingError("CUSTOMER_NOT_FOUND", message="Custom msg")
        assert err.message == "Custom msg"

    def test_as_dict(self):
        err = AttendingError("LOYALTY_NOT_ENROLLED", customer_ref="CRM-001")
        d = err.as_dict()
        assert d["code"] == "LOYALTY_NOT_ENROLLED"
        assert d["data"]["customer_ref"] == "CRM-001"


# ═══════════════════════════════════════════════════════════════════
# Customer → ContactPoint Sync (G2)
# ═══════════════════════════════════════════════════════════════════


class TestCustomerContactPointSync:
    """Customer.save() syncs phone/email to ContactPoint."""

    def test_phone_synced_on_create(self, customer):
        """Creating customer with phone creates phone ContactPoint."""
        cp = ContactPoint.objects.filter(
            customer=customer,
            type=ContactPoint.Type.PHONE,
        )
        assert cp.exists()
        assert cp.first().is_primary is True

    def test_email_synced_on_create(self, customer):
        """Creating customer with email creates email ContactPoint."""
        cp = ContactPoint.objects.filter(
            customer=customer,
            type=ContactPoint.Type.EMAIL,
        )
        assert cp.exists()
        assert cp.first().is_primary is True

    def test_no_duplicate_on_resave(self, customer):
        """Re-saving customer doesn't create duplicate ContactPoints."""
        customer.save()
        customer.save()
        phone_count = ContactPoint.objects.filter(
            customer=customer,
            type=ContactPoint.Type.PHONE,
        ).count()
        assert phone_count == 1

    def test_customer_without_phone_no_cp(self, group):
        """Customer without phone doesn't create phone ContactPoint."""
        cust = Customer.objects.create(
            ref="NO-PHONE",
            first_name="Test",
            group=group,
        )
        assert not ContactPoint.objects.filter(
            customer=cust,
            type=ContactPoint.Type.PHONE,
        ).exists()


# ═══════════════════════════════════════════════════════════════════
# Address Null Safety (G4)
# ═══════════════════════════════════════════════════════════════════


class TestAddressNullSafety:
    """Address properties are safe when fields are empty."""

    def test_short_address_no_route(self, customer):
        """short_address falls back to formatted_address when route is empty."""
        addr = CustomerAddress.objects.create(
            customer=customer,
            label="home",
            formatted_address="Complete address here, 123",
            route="",
            street_number="",
        )
        assert addr.short_address == "Complete address here, 123"[:60]

    def test_short_address_with_route(self, customer):
        """short_address works normally with route."""
        addr = CustomerAddress.objects.create(
            customer=customer,
            label="home",
            formatted_address="Full address",
            route="Rua Test",
            street_number="456",
            neighborhood="Centro",
        )
        assert addr.short_address == "Rua Test 456 - Centro"

    def test_str_with_empty_formatted(self, customer):
        """__str__ doesn't explode with empty formatted_address."""
        addr = CustomerAddress.objects.create(
            customer=customer,
            label="home",
            formatted_address="",
        )
        result = str(addr)
        assert isinstance(result, str)

    def test_str_with_other_label_no_custom(self, customer):
        """__str__ handles OTHER label without custom label."""
        addr = CustomerAddress.objects.create(
            customer=customer,
            label="other",
            label_custom="",
            formatted_address="Some address",
        )
        result = str(addr)
        assert isinstance(result, str)


# ═══════════════════════════════════════════════════════════════════
# Transaction Atomicity (G1)
# ═══════════════════════════════════════════════════════════════════


class TestTransactionAtomicity:
    """Services use transaction.atomic() for multi-record operations."""

    def test_add_address_is_default_atomic(self, customer):
        """add_address with is_default=True is atomic."""
        from shopman.attending.services import address as address_service

        addr1 = address_service.add_address(
            "CRM-001",
            label="home",
            formatted_address="Addr 1",
            is_default=True,
        )
        addr2 = address_service.add_address(
            "CRM-001",
            label="work",
            formatted_address="Addr 2",
            is_default=True,
        )
        addr1.refresh_from_db()
        assert addr1.is_default is False
        assert addr2.is_default is True


# ═══════════════════════════════════════════════════════════════════
# Timeline Service
# ═══════════════════════════════════════════════════════════════════


class TestTimelineService:
    """Tests for timeline service."""

    def test_log_event(self, customer):
        """Log a timeline event."""
        event = TimelineService.log_event(
            "CRM-001",
            event_type="order",
            title="Pedido #123 confirmado",
            channel="whatsapp",
            reference="order:123",
        )
        assert event.event_type == "order"
        assert event.title == "Pedido #123 confirmado"
        assert event.customer == customer

    def test_get_timeline(self, customer):
        """Get timeline returns events in reverse chronological order."""
        TimelineService.log_event("CRM-001", "order", "Pedido 1")
        TimelineService.log_event("CRM-001", "contact", "WhatsApp recebido")
        TimelineService.log_event("CRM-001", "note", "Cliente VIP")

        events = TimelineService.get_timeline("CRM-001")
        assert len(events) == 3
        assert events[0].event_type == "note"  # most recent first

    def test_get_timeline_by_type(self, customer):
        """Filter timeline by event type."""
        TimelineService.log_event("CRM-001", "order", "Pedido 1")
        TimelineService.log_event("CRM-001", "contact", "WhatsApp")
        TimelineService.log_event("CRM-001", "order", "Pedido 2")

        orders = TimelineService.get_timeline("CRM-001", event_type="order")
        assert len(orders) == 2
        assert all(e.event_type == "order" for e in orders)

    def test_get_timeline_limit(self, customer):
        """Timeline respects limit."""
        for i in range(5):
            TimelineService.log_event("CRM-001", "system", f"Event {i}")

        events = TimelineService.get_timeline("CRM-001", limit=3)
        assert len(events) == 3

    def test_log_event_nonexistent_customer(self, group):
        """Log event for nonexistent customer raises."""
        with pytest.raises(Customer.DoesNotExist):
            TimelineService.log_event("NONEXISTENT", "note", "Test")

    def test_get_recent_across_customers(self, customer, customer_b):
        """Get events across all customers."""
        TimelineService.log_event("CRM-001", "order", "Pedido Maria")
        TimelineService.log_event("CRM-002", "order", "Pedido João")

        events = TimelineService.get_recent_across_customers()
        assert len(events) == 2

    def test_timeline_with_metadata(self, customer):
        """Timeline event stores metadata."""
        event = TimelineService.log_event(
            "CRM-001",
            "order",
            "Pedido #100",
            metadata={"total_q": 5000, "items": 3},
        )
        assert event.metadata["total_q"] == 5000


# ═══════════════════════════════════════════════════════════════════
# Consent Service (LGPD)
# ═══════════════════════════════════════════════════════════════════


class TestConsentService:
    """Tests for LGPD consent service."""

    def test_grant_consent(self, customer):
        """Grant opt-in consent for a channel."""
        consent = ConsentService.grant_consent(
            "CRM-001",
            "whatsapp",
            source="checkout_form",
        )
        assert consent.status == "opted_in"
        assert consent.source == "checkout_form"
        assert consent.consented_at is not None

    def test_has_consent_true(self, customer):
        """has_consent returns True after opt-in."""
        ConsentService.grant_consent("CRM-001", "email")
        assert ConsentService.has_consent("CRM-001", "email") is True

    def test_has_consent_false_no_record(self, customer):
        """has_consent returns False when no consent record exists."""
        assert ConsentService.has_consent("CRM-001", "whatsapp") is False

    def test_revoke_consent(self, customer):
        """Revoke consent marks as opted_out."""
        ConsentService.grant_consent("CRM-001", "whatsapp")
        ConsentService.revoke_consent("CRM-001", "whatsapp")

        assert ConsentService.has_consent("CRM-001", "whatsapp") is False

        consent = CommunicationConsent.objects.get(
            customer=customer,
            channel="whatsapp",
        )
        assert consent.status == "opted_out"
        assert consent.revoked_at is not None

    def test_re_grant_after_revoke(self, customer):
        """Can re-grant consent after revocation."""
        ConsentService.grant_consent("CRM-001", "whatsapp")
        ConsentService.revoke_consent("CRM-001", "whatsapp")
        ConsentService.grant_consent("CRM-001", "whatsapp", source="re-opt-in")

        assert ConsentService.has_consent("CRM-001", "whatsapp") is True

    def test_get_consents(self, customer):
        """Get all consent records for a customer."""
        ConsentService.grant_consent("CRM-001", "whatsapp")
        ConsentService.grant_consent("CRM-001", "email")
        ConsentService.revoke_consent("CRM-001", "sms")

        consents = ConsentService.get_consents("CRM-001")
        assert len(consents) == 3

    def test_get_opted_in_channels(self, customer):
        """Get only opted-in channels."""
        ConsentService.grant_consent("CRM-001", "whatsapp")
        ConsentService.grant_consent("CRM-001", "email")
        ConsentService.revoke_consent("CRM-001", "sms")

        channels = ConsentService.get_opted_in_channels("CRM-001")
        assert set(channels) == {"whatsapp", "email"}

    def test_get_marketable_customers(self, customer, customer_b):
        """Get customers with active consent for a channel."""
        ConsentService.grant_consent("CRM-001", "whatsapp")
        ConsentService.grant_consent("CRM-002", "whatsapp")
        ConsentService.revoke_consent("CRM-002", "whatsapp")

        marketable = ConsentService.get_marketable_customers("whatsapp")
        assert marketable == ["CRM-001"]

    def test_unique_per_customer_channel(self, customer):
        """Only one consent record per (customer, channel)."""
        ConsentService.grant_consent("CRM-001", "whatsapp")
        ConsentService.grant_consent("CRM-001", "whatsapp", source="updated")

        count = CommunicationConsent.objects.filter(
            customer=customer,
            channel="whatsapp",
        ).count()
        assert count == 1

    def test_consent_with_ip(self, customer):
        """Consent records IP address."""
        consent = ConsentService.grant_consent(
            "CRM-001",
            "email",
            ip_address="192.168.1.1",
        )
        assert consent.ip_address == "192.168.1.1"


# ═══════════════════════════════════════════════════════════════════
# Loyalty Service
# ═══════════════════════════════════════════════════════════════════


class TestLoyaltyService:
    """Tests for loyalty program service."""

    def test_enroll(self, customer):
        """Enroll customer in loyalty program."""
        account = LoyaltyService.enroll("CRM-001")
        assert account.points_balance == 0
        assert account.tier == "bronze"
        assert account.customer == customer

    def test_enroll_idempotent(self, customer):
        """Enrolling twice returns same account."""
        acc1 = LoyaltyService.enroll("CRM-001")
        acc2 = LoyaltyService.enroll("CRM-001")
        assert acc1.pk == acc2.pk

    def test_earn_points(self, customer):
        """Earn points increases balance and lifetime."""
        LoyaltyService.enroll("CRM-001")
        tx = LoyaltyService.earn_points("CRM-001", 100, "Pedido #123")

        assert tx.points == 100
        assert tx.balance_after == 100
        assert tx.transaction_type == "earn"

        account = LoyaltyService.get_account("CRM-001")
        assert account.points_balance == 100
        assert account.lifetime_points == 100

    def test_redeem_points(self, customer):
        """Redeem points decreases balance."""
        LoyaltyService.enroll("CRM-001")
        LoyaltyService.earn_points("CRM-001", 200, "Earn")
        tx = LoyaltyService.redeem_points("CRM-001", 50, "Desconto")

        assert tx.points == -50
        assert tx.balance_after == 150

        account = LoyaltyService.get_account("CRM-001")
        assert account.points_balance == 150
        assert account.lifetime_points == 200  # lifetime doesn't decrease

    def test_redeem_insufficient_raises(self, customer):
        """Redeeming more than balance raises error."""
        LoyaltyService.enroll("CRM-001")
        LoyaltyService.earn_points("CRM-001", 50, "Earn")

        with pytest.raises(AttendingError, match="LOYALTY_INSUFFICIENT_POINTS"):
            LoyaltyService.redeem_points("CRM-001", 100, "Too much")

    def test_not_enrolled_raises(self, customer):
        """Operations on non-enrolled customer raise error."""
        with pytest.raises(AttendingError, match="LOYALTY_NOT_ENROLLED"):
            LoyaltyService.earn_points("CRM-001", 100, "Test")

    def test_get_balance(self, customer):
        """Get balance returns 0 when not enrolled."""
        assert LoyaltyService.get_balance("CRM-001") == 0

        LoyaltyService.enroll("CRM-001")
        LoyaltyService.earn_points("CRM-001", 100, "Test")
        assert LoyaltyService.get_balance("CRM-001") == 100

    def test_add_stamp(self, customer):
        """Add stamp increments counter."""
        LoyaltyService.enroll("CRM-001")
        account, completed = LoyaltyService.add_stamp("CRM-001", "Compra")

        assert account.stamps_current == 1
        assert completed is False

    def test_stamp_card_completion(self, customer):
        """Completing stamp card resets counter."""
        account = LoyaltyService.enroll("CRM-001")
        account.stamps_target = 3
        account.save()

        LoyaltyService.add_stamp("CRM-001", "Stamp 1")
        LoyaltyService.add_stamp("CRM-001", "Stamp 2")
        account, completed = LoyaltyService.add_stamp("CRM-001", "Stamp 3")

        assert completed is True
        assert account.stamps_current == 0
        assert account.stamps_completed == 1

    def test_tier_auto_upgrade(self, customer):
        """Tier upgrades automatically based on lifetime points."""
        LoyaltyService.enroll("CRM-001")

        # Earn enough for Silver (500+)
        LoyaltyService.earn_points("CRM-001", 500, "Big order")
        account = LoyaltyService.get_account("CRM-001")
        assert account.tier == "silver"

        # Earn enough for Gold (2000+)
        LoyaltyService.earn_points("CRM-001", 1500, "VIP purchase")
        account = LoyaltyService.get_account("CRM-001")
        assert account.tier == "gold"

    def test_get_transactions(self, customer):
        """Get transaction history."""
        LoyaltyService.enroll("CRM-001")
        LoyaltyService.earn_points("CRM-001", 100, "Pedido 1")
        LoyaltyService.earn_points("CRM-001", 50, "Pedido 2")
        LoyaltyService.redeem_points("CRM-001", 30, "Desconto")

        txs = LoyaltyService.get_transactions("CRM-001")
        assert len(txs) == 3

    def test_earn_zero_raises(self, customer):
        """Earning 0 or negative points raises."""
        LoyaltyService.enroll("CRM-001")
        with pytest.raises(AttendingError):
            LoyaltyService.earn_points("CRM-001", 0, "Invalid")
        with pytest.raises(AttendingError):
            LoyaltyService.earn_points("CRM-001", -10, "Invalid")

    def test_stamps_progress_percent(self, customer):
        """stamps_progress_percent calculates correctly."""
        account = LoyaltyService.enroll("CRM-001")
        assert account.stamps_progress_percent == 0

        LoyaltyService.add_stamp("CRM-001", "Stamp")
        account.refresh_from_db()
        assert account.stamps_progress_percent == 10  # 1/10 = 10%


# ═══════════════════════════════════════════════════════════════════
# InsightService Enhancements
# ═══════════════════════════════════════════════════════════════════


class TestInsightServiceEnhancements:
    """Tests for InsightService LTV and segmentation features."""

    def test_calculate_ltv_with_frequency(self):
        """LTV calculation with known purchase frequency."""
        ltv = InsightService._calculate_ltv(
            avg_ticket_q=5000,  # R$ 50
            avg_days_between=Decimal("30"),  # monthly
            total_orders=10,
        )
        # 5000 * (365/30) ≈ 60833
        assert ltv is not None
        assert ltv > 50000

    def test_calculate_ltv_no_frequency(self):
        """LTV fallback when frequency unknown."""
        ltv = InsightService._calculate_ltv(
            avg_ticket_q=5000,
            avg_days_between=None,
            total_orders=5,
        )
        # Fallback: 5000 * 5 * 2 = 50000
        assert ltv == 50000

    def test_calculate_ltv_zero_ticket(self):
        """LTV is 0 when ticket is 0."""
        ltv = InsightService._calculate_ltv(0, Decimal("30"), 10)
        assert ltv == 0

    def test_calculate_ltv_single_order(self):
        """LTV is None for single-order customers without frequency."""
        ltv = InsightService._calculate_ltv(5000, None, 1)
        assert ltv is None

    def test_get_segment_customers(self, customer):
        """Get customers by RFM segment."""
        from shopman.attending.contrib.insights.models import CustomerInsight

        CustomerInsight.objects.create(
            customer=customer,
            total_orders=10,
            total_spent_q=100000,
            rfm_segment="champion",
        )

        champions = InsightService.get_segment_customers("champion")
        assert len(champions) == 1
        assert champions[0].customer == customer

    def test_get_at_risk_customers(self, customer, customer_b):
        """Get customers with high churn risk."""
        from shopman.attending.contrib.insights.models import CustomerInsight

        CustomerInsight.objects.create(
            customer=customer,
            rfm_segment="at_risk",
            churn_risk=Decimal("0.85"),
        )
        CustomerInsight.objects.create(
            customer=customer_b,
            rfm_segment="champion",
            churn_risk=Decimal("0.1"),
        )

        at_risk = InsightService.get_at_risk_customers()
        assert len(at_risk) == 1
        assert at_risk[0].customer == customer


# ═══════════════════════════════════════════════════════════════════
# Timeline Model
# ═══════════════════════════════════════════════════════════════════


class TestTimelineEventModel:
    """Tests for TimelineEvent model."""

    def test_str(self, customer):
        event = TimelineEvent.objects.create(
            customer=customer,
            event_type="order",
            title="Pedido #100",
        )
        assert str(event) == "[order] Pedido #100"

    def test_ordering(self, customer):
        """Events ordered by most recent first."""
        e1 = TimelineEvent.objects.create(
            customer=customer, event_type="order", title="First"
        )
        e2 = TimelineEvent.objects.create(
            customer=customer, event_type="order", title="Second"
        )
        events = list(TimelineEvent.objects.filter(customer=customer))
        assert events[0] == e2


# ═══════════════════════════════════════════════════════════════════
# Consent Model
# ═══════════════════════════════════════════════════════════════════


class TestCommunicationConsentModel:
    """Tests for CommunicationConsent model."""

    def test_str(self, customer):
        consent = CommunicationConsent.objects.create(
            customer=customer,
            channel="whatsapp",
            status="opted_in",
        )
        assert "whatsapp" in str(consent)

    def test_is_active_property(self, customer):
        consent = CommunicationConsent.objects.create(
            customer=customer,
            channel="email",
            status="opted_in",
        )
        assert consent.is_active is True

        consent.status = "opted_out"
        assert consent.is_active is False

    def test_unique_constraint(self, customer):
        """Only one consent per (customer, channel)."""
        CommunicationConsent.objects.create(
            customer=customer, channel="whatsapp", status="opted_in"
        )
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                CommunicationConsent.objects.create(
                    customer=customer, channel="whatsapp", status="opted_out"
                )


# ═══════════════════════════════════════════════════════════════════
# Loyalty Models
# ═══════════════════════════════════════════════════════════════════


class TestLoyaltyModels:
    """Tests for loyalty models."""

    def test_account_str(self, customer):
        account = LoyaltyAccount.objects.create(
            customer=customer,
            points_balance=150,
            tier="silver",
        )
        assert "150pts" in str(account)
        assert "silver" in str(account)

    def test_stamps_remaining(self, customer):
        account = LoyaltyAccount.objects.create(
            customer=customer,
            stamps_current=7,
            stamps_target=10,
        )
        assert account.stamps_remaining == 3

    def test_transaction_str(self, customer):
        account = LoyaltyAccount.objects.create(customer=customer)
        tx = LoyaltyTransaction.objects.create(
            account=account,
            transaction_type="earn",
            points=100,
            balance_after=100,
            description="Test earn",
        )
        assert "+100pts" in str(tx)

    def test_transaction_immutable(self, customer):
        """Transactions are append-only in the admin (no add/delete)."""
        # This is enforced at admin level, not model level.
        # Just verify the model works.
        account = LoyaltyAccount.objects.create(customer=customer)
        tx = LoyaltyTransaction.objects.create(
            account=account,
            transaction_type="redeem",
            points=-50,
            balance_after=50,
            description="Redeem",
        )
        assert tx.points == -50
