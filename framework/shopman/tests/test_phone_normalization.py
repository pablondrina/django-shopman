"""
Tests for P1: Phone normalization — iOS autofill zero in DDD.

Regression tests ensuring that (043) 98404-9009 and (43) 98404-9009
resolve to the SAME customer across all flows:
- Web checkout
- Manychat access webhook
- Customer lookup
- OTP login
"""

from __future__ import annotations

import pytest
from django.test import TestCase

from shopman.guestman.models import ContactPoint, Customer
from shopman.guestman.services import customer as customer_service
from shopman.omniman.models import Channel, Order
from shopman.utils.phone import normalize_phone

pytestmark = pytest.mark.django_db


# ── Core normalization: zero-prefix DDD variants ─────────────────────


class TestZeroPrefixDDDNormalization(TestCase):
    """All zero-prefix DDD variants must normalize identically."""

    EXPECTED = "+5543984049009"

    VARIANTS = [
        "(043) 98404-9009",   # iOS autofill with zero
        "(43) 98404-9009",    # Standard formatted
        "43984049009",        # Bare digits
        "043984049009",       # Bare digits with zero
        "+5543984049009",     # E.164
        "5543984049009",      # With country code, no plus
    ]

    def test_all_variants_normalize_to_same_e164(self):
        results = {v: normalize_phone(v) for v in self.VARIANTS}
        for variant, result in results.items():
            self.assertEqual(
                result, self.EXPECTED,
                f"normalize_phone({variant!r}) returned {result!r}, expected {self.EXPECTED!r}",
            )


# ── Customer dedup: same phone = same customer ──────────────────────


class TestCustomerPhoneDedup(TestCase):
    """Customers created with different phone formats must not duplicate."""

    def setUp(self):
        self.customer = Customer.objects.create(
            ref="TEST-001",
            first_name="Maria",
            phone="+5543984049009",
        )

    def test_get_by_phone_with_zero_ddd(self):
        """get_by_phone with (043) format finds the same customer."""
        found = customer_service.get_by_phone("(043) 98404-9009")
        self.assertIsNotNone(found)
        self.assertEqual(found.pk, self.customer.pk)

    def test_get_by_phone_without_zero_ddd(self):
        """get_by_phone with (43) format finds the same customer."""
        found = customer_service.get_by_phone("(43) 98404-9009")
        self.assertIsNotNone(found)
        self.assertEqual(found.pk, self.customer.pk)

    def test_get_by_phone_bare_digits_with_zero(self):
        """get_by_phone with bare digits including zero finds the same customer."""
        found = customer_service.get_by_phone("043984049009")
        self.assertIsNotNone(found)
        self.assertEqual(found.pk, self.customer.pk)

    def test_customer_save_normalizes_phone(self):
        """Customer.save() normalizes phone to E.164."""
        c = Customer.objects.create(
            ref="TEST-002",
            first_name="João",
            phone="(043) 98404-8888",
        )
        c.refresh_from_db()
        self.assertEqual(c.phone, "+5543984048888")


# ── ContactPoint dedup ───────────────────────────────────────────────


class TestContactPointPhoneDedup(TestCase):
    """ContactPoint with normalized phone matches regardless of input format."""

    def setUp(self):
        self.customer = Customer.objects.create(
            ref="TEST-CP-001",
            first_name="Ana",
            phone="+5543984049009",
        )
        ContactPoint.objects.create(
            customer=self.customer,
            type=ContactPoint.Type.WHATSAPP,
            value_normalized="+5543984049009",
            is_verified=True,
        )

    def test_contact_point_found_by_normalized_zero_ddd(self):
        """ContactPoint lookup with (043) format works."""
        phone = normalize_phone("(043) 98404-9009")
        cp = ContactPoint.objects.filter(
            type=ContactPoint.Type.WHATSAPP,
            value_normalized=phone,
        ).first()
        self.assertIsNotNone(cp)
        self.assertEqual(cp.customer.pk, self.customer.pk)

    def test_contact_point_found_by_normalized_standard(self):
        """ContactPoint lookup with (43) format works."""
        phone = normalize_phone("(43) 98404-9009")
        cp = ContactPoint.objects.filter(
            type=ContactPoint.Type.WHATSAPP,
            value_normalized=phone,
        ).first()
        self.assertIsNotNone(cp)
        self.assertEqual(cp.customer.pk, self.customer.pk)


# ── Order handle_ref lookup ──────────────────────────────────────────


class TestOrderHandleRefPhoneLookup(TestCase):
    """Orders stored with normalized phone are found by any variant."""

    def setUp(self):
        self.channel = Channel.objects.create(
            ref="web", name="Web",
        )
        self.order = Order.objects.create(
            ref="ORD-PHONE-001",
            channel=self.channel,
            status="new",
            total_q=1000,
            handle_type="phone",
            handle_ref="+5543984049009",
            data={},
        )

    def test_order_found_by_zero_ddd_phone(self):
        """Order lookup by handle_ref matches (043) variant."""
        phone = normalize_phone("(043) 98404-9009")
        order = Order.objects.filter(
            handle_type="phone",
            handle_ref=phone,
        ).first()
        self.assertIsNotNone(order)
        self.assertEqual(order.ref, "ORD-PHONE-001")

    def test_order_found_by_standard_phone(self):
        """Order lookup by handle_ref matches (43) variant."""
        phone = normalize_phone("(43) 98404-9009")
        order = Order.objects.filter(
            handle_type="phone",
            handle_ref=phone,
        ).first()
        self.assertIsNotNone(order)
        self.assertEqual(order.ref, "ORD-PHONE-001")
