"""Tests for CheckoutView._persist_new_address (omotenashi address persistence)."""

from __future__ import annotations

import pytest
from django.test import TestCase

from shopman.guestman.models import Customer, CustomerAddress, CustomerGroup
from shopman.storefront.intents.types import CheckoutIntent
from shopman.storefront.views.checkout import CheckoutView


PHONE = "+5543999990001"
FORMATTED = "Rua das Flores, 123, Centro, Londrina - PR, 86020-000"
STRUCTURED = {
    "route": "Rua das Flores",
    "street_number": "123",
    "complement": "Apto 4",
    "neighborhood": "Centro",
    "city": "Londrina",
    "state_code": "PR",
    "postal_code": "86020-000",
    "place_id": "ChIJ_test_place_id",
    "formatted_address": FORMATTED,
    "delivery_instructions": "Portão azul",
    "is_verified": True,
    "latitude": -23.31,
    "longitude": -51.16,
}


def _make_intent(
    *,
    fulfillment_type: str = "delivery",
    delivery_address: str | None = FORMATTED,
    delivery_address_structured: dict | None = STRUCTURED,
    saved_address_id: int | None = None,
    customer_phone: str = PHONE,
) -> CheckoutIntent:
    return CheckoutIntent(
        session_key="sk-test",
        channel_ref="web",
        customer_name="João Silva",
        customer_phone=customer_phone,
        fulfillment_type=fulfillment_type,
        payment_method="pix",
        delivery_address=delivery_address,
        delivery_address_structured=delivery_address_structured,
        saved_address_id=saved_address_id,
        delivery_date=None,
        delivery_time_slot=None,
        notes=None,
        loyalty_redeem=False,
        loyalty_balance_q=0,
        stock_check_unavailable=False,
        idempotency_key="idem-test",
        checkout_data={},
    )


def _make_customer(phone: str = PHONE) -> Customer:
    group, _ = CustomerGroup.objects.get_or_create(
        ref="regular", defaults={"name": "Regular", "is_default": True, "priority": 0}
    )
    return Customer.objects.create(
        ref=f"CUST-PA-{phone[-4:]}",
        first_name="João",
        last_name="Silva",
        phone=phone,
        group=group,
    )


class PersistNewAddressTests(TestCase):

    def setUp(self):
        self.customer = _make_customer()

    # ── Address IS persisted ─────────────────────────────────────────────

    def test_new_address_saved_to_customer_account(self):
        intent = _make_intent()
        CheckoutView._persist_new_address(intent, "ORD-PA-001")

        addrs = list(CustomerAddress.objects.filter(customer=self.customer))
        self.assertEqual(len(addrs), 1)
        addr = addrs[0]
        self.assertEqual(addr.formatted_address, FORMATTED)
        self.assertEqual(addr.complement, "Apto 4")
        self.assertEqual(addr.delivery_instructions, "Portão azul")
        self.assertEqual(addr.route, "Rua das Flores")
        self.assertEqual(addr.street_number, "123")
        self.assertEqual(addr.neighborhood, "Centro")
        self.assertEqual(addr.city, "Londrina")
        self.assertEqual(addr.state_code, "PR")
        self.assertEqual(addr.postal_code, "86020-000")
        self.assertEqual(addr.place_id, "ChIJ_test_place_id")
        self.assertIsNotNone(addr.latitude)
        self.assertIsNotNone(addr.longitude)
        self.assertEqual(addr.label, "other")
        self.assertEqual(addr.label_custom, "Entrega")

    def test_first_address_becomes_default(self):
        intent = _make_intent()
        CheckoutView._persist_new_address(intent, "ORD-PA-002")

        addr = CustomerAddress.objects.get(customer=self.customer)
        self.assertTrue(addr.is_default)

    def test_second_address_is_not_default(self):
        # Pre-existing address → first one is already default
        CustomerAddress.objects.create(
            customer=self.customer,
            label="home",
            formatted_address="Outra Rua, 456",
            is_default=True,
        )
        intent = _make_intent()
        CheckoutView._persist_new_address(intent, "ORD-PA-003")

        new_addr = CustomerAddress.objects.get(
            customer=self.customer, formatted_address=FORMATTED
        )
        self.assertFalse(new_addr.is_default)

    def test_address_without_structured_data(self):
        intent = _make_intent(delivery_address_structured=None)
        CheckoutView._persist_new_address(intent, "ORD-PA-004")

        addr = CustomerAddress.objects.get(customer=self.customer)
        self.assertEqual(addr.formatted_address, FORMATTED)
        self.assertEqual(addr.route, "")
        self.assertIsNone(addr.latitude)

    # ── Address is NOT persisted ─────────────────────────────────────────

    def test_pickup_order_skipped(self):
        intent = _make_intent(fulfillment_type="pickup")
        CheckoutView._persist_new_address(intent, "ORD-PA-005")

        self.assertFalse(CustomerAddress.objects.filter(customer=self.customer).exists())

    def test_saved_address_not_duplicated(self):
        existing = CustomerAddress.objects.create(
            customer=self.customer,
            label="home",
            formatted_address=FORMATTED,
            is_default=True,
        )
        intent = _make_intent(saved_address_id=existing.pk)
        CheckoutView._persist_new_address(intent, "ORD-PA-006")

        self.assertEqual(CustomerAddress.objects.filter(customer=self.customer).count(), 1)

    def test_duplicate_formatted_address_not_saved(self):
        CustomerAddress.objects.create(
            customer=self.customer,
            label="home",
            formatted_address=FORMATTED,
            is_default=True,
        )
        intent = _make_intent()  # no saved_address_id, new entry path
        CheckoutView._persist_new_address(intent, "ORD-PA-007")

        self.assertEqual(CustomerAddress.objects.filter(customer=self.customer).count(), 1)

    def test_no_delivery_address_skipped(self):
        intent = _make_intent(delivery_address=None)
        CheckoutView._persist_new_address(intent, "ORD-PA-008")

        self.assertFalse(CustomerAddress.objects.filter(customer=self.customer).exists())

    def test_unknown_phone_skipped(self):
        intent = _make_intent(customer_phone="+5500000000000")
        CheckoutView._persist_new_address(intent, "ORD-PA-009")

        self.assertFalse(CustomerAddress.objects.exists())

    # ── Exception safety ─────────────────────────────────────────────────

    def test_exception_does_not_propagate(self):
        from unittest.mock import patch

        intent = _make_intent()
        with patch(
            "shopman.guestman.services.address.has_address",
            side_effect=Exception("db error"),
        ):
            # Must not raise — checkout should never fail for address persistence
            CheckoutView._persist_new_address(intent, "ORD-PA-010")
