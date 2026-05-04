"""Unit tests for shopman.shop.projections.account.

Uses customer fixtures from conftest.py. Verifies CustomerProfileProjection
shape, loyalty embedding, address projection, notification prefs, food prefs,
and graceful degradation when services are unavailable.
"""
from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from shopman.shop.projections.types import (
    FoodPrefProjection,
    NotificationPrefProjection,
    OrderSummaryProjection,
    SavedAddressProjection,
)
from shopman.storefront.projections.account import (
    CustomerProfileProjection,
    LoyaltyProjection,
    build_account,
)

pytestmark = pytest.mark.django_db


# ──────────────────────────────────────────────────────────────────────
# CustomerProfileProjection — shape
# ──────────────────────────────────────────────────────────────────────


class TestCustomerProfileShape:
    def test_returns_projection(self, customer):
        proj = build_account(customer)
        assert isinstance(proj, CustomerProfileProjection)

    def test_is_immutable(self, customer):
        proj = build_account(customer)
        with pytest.raises(FrozenInstanceError):
            proj.customer_name = "Outro"  # type: ignore[misc]

    def test_customer_fields(self, customer):
        proj = build_account(customer)
        assert proj.customer_ref == customer.ref
        assert proj.customer_first_name == customer.first_name
        assert proj.customer_phone == customer.phone

    def test_email_defaults_empty(self, customer):
        proj = build_account(customer)
        assert isinstance(proj.customer_email, str)

    def test_birthday_none_when_not_set(self, customer):
        proj = build_account(customer)
        assert proj.customer_birthday_display is None

    def test_birthday_formatted(self, customer):
        from datetime import date
        customer.birthday = date(1990, 4, 15)
        customer.save()
        proj = build_account(customer)
        assert proj.customer_birthday_display == "15/04/1990"

    def test_tab_options_present(self, customer):
        proj = build_account(customer)
        assert len(proj.tab_options) == 4
        assert proj.tab_options[0] == ("perfil", "Perfil")


# ──────────────────────────────────────────────────────────────────────
# Loyalty
# ──────────────────────────────────────────────────────────────────────


class TestCustomerProfileLoyalty:
    def test_loyalty_none_when_no_account(self, customer):
        proj = build_account(customer)
        assert proj.loyalty is None

    def test_loyalty_projection_when_enrolled(self, customer):
        from shopman.guestman.contrib.loyalty import LoyaltyService

        LoyaltyService.enroll(customer.ref)
        proj = build_account(customer)
        assert isinstance(proj.loyalty, LoyaltyProjection)
        assert proj.loyalty.points_balance == 0

    def test_loyalty_tier_display(self, customer):
        from shopman.guestman.contrib.loyalty import LoyaltyService

        LoyaltyService.enroll(customer.ref)
        proj = build_account(customer)
        assert proj.loyalty is not None
        assert isinstance(proj.loyalty.tier_display, str)
        assert len(proj.loyalty.tier_display) > 0

    def test_loyalty_stamps_range_matches_target(self, customer):
        from shopman.guestman.contrib.loyalty import LoyaltyService

        LoyaltyService.enroll(customer.ref)
        proj = build_account(customer)
        assert proj.loyalty is not None
        account = proj.loyalty
        if account.stamps_target > 0:
            assert len(account.stamps_range) == account.stamps_target
            assert account.stamps_range[0] == 1
            assert account.stamps_range[-1] == account.stamps_target
        else:
            assert account.stamps_range == ()

    def test_loyalty_transactions_empty_initially(self, customer):
        from shopman.guestman.contrib.loyalty import LoyaltyService

        LoyaltyService.enroll(customer.ref)
        proj = build_account(customer)
        assert proj.loyalty is not None
        assert isinstance(proj.loyalty.transactions, tuple)

    def test_loyalty_transaction_failure_keeps_account(self, customer, monkeypatch):
        from shopman.guestman.contrib.loyalty import LoyaltyService

        from shopman.shop.services import customer_context

        LoyaltyService.enroll(customer.ref)
        debug_calls = []

        def fail_transactions(*args, **kwargs):
            raise RuntimeError("transactions unavailable")

        def record_debug(message, *args, **kwargs):
            debug_calls.append((message, kwargs))

        monkeypatch.setattr(LoyaltyService, "get_transactions", fail_transactions)
        monkeypatch.setattr(customer_context.logger, "debug", record_debug)

        proj = build_account(customer)

        assert proj.loyalty is not None
        assert proj.loyalty.transactions == ()
        assert any(
            "customer_context_loyalty_transactions_failed" in message
            and kwargs.get("exc_info") is True
            for message, kwargs in debug_calls
        )


# ──────────────────────────────────────────────────────────────────────
# Addresses
# ──────────────────────────────────────────────────────────────────────


class TestCustomerProfileAddresses:
    def test_addresses_empty_when_none(self, customer):
        proj = build_account(customer)
        assert proj.saved_addresses == ()

    def test_addresses_projected(self, customer, customer_address):
        proj = build_account(customer)
        assert len(proj.saved_addresses) == 1
        assert isinstance(proj.saved_addresses[0], SavedAddressProjection)
        assert "Rua das Flores" in proj.saved_addresses[0].formatted_address

    def test_address_default_flag(self, customer, customer_address):
        proj = build_account(customer)
        assert proj.saved_addresses[0].is_default is True

    def test_address_failure_degrades_to_empty(self, customer, monkeypatch):
        from shopman.guestman.services import address as address_service

        from shopman.shop.services import customer_context

        debug_calls = []

        def fail_addresses(*args, **kwargs):
            raise RuntimeError("addresses unavailable")

        def record_debug(message, *args, **kwargs):
            debug_calls.append((message, kwargs))

        monkeypatch.setattr(address_service, "addresses", fail_addresses)
        monkeypatch.setattr(customer_context.logger, "debug", record_debug)

        proj = build_account(customer)

        assert proj.saved_addresses == ()
        assert any(
            "customer_context_addresses_failed" in message
            and kwargs.get("exc_info") is True
            for message, kwargs in debug_calls
        )


# ──────────────────────────────────────────────────────────────────────
# Recent orders
# ──────────────────────────────────────────────────────────────────────


class TestCustomerProfileRecentOrders:
    def test_recent_orders_empty_when_no_history(self, customer):
        proj = build_account(customer)
        assert proj.recent_orders == ()

    def test_recent_orders_projected(self, customer, order):
        from shopman.orderman.models import Order

        Order.objects.filter(pk=order.pk).update(
            data={"customer_ref": customer.ref}
        )
        order.refresh_from_db()
        proj = build_account(customer)
        assert all(isinstance(o, OrderSummaryProjection) for o in proj.recent_orders)

    def test_recent_orders_share_customer_identity_contract(self, customer):
        from shopman.orderman.models import Order

        order = Order.objects.create(
            ref="ORD-ACCOUNT-PHONE",
            channel_ref="web",
            status="completed",
            total_q=1900,
            handle_type="phone",
            handle_ref=customer.phone,
            data={},
        )

        proj = build_account(customer)

        assert [o.ref for o in proj.recent_orders] == [order.ref]

    def test_order_summary_fields(self, customer, order):
        from shopman.orderman.models import Order

        Order.objects.filter(pk=order.pk).update(
            data={"customer_ref": customer.ref}
        )
        order.refresh_from_db()
        proj = build_account(customer)
        if proj.recent_orders:
            o = proj.recent_orders[0]
            assert o.ref == order.ref
            assert o.total_display.startswith("R$ ")
            assert o.status_label
            assert o.status_color


# ──────────────────────────────────────────────────────────────────────
# Notification prefs
# ──────────────────────────────────────────────────────────────────────


class TestCustomerProfileNotificationPrefs:
    def test_notification_prefs_all_channels(self, customer):
        proj = build_account(customer)
        assert len(proj.notification_prefs) == 4
        keys = {p.key for p in proj.notification_prefs}
        assert keys == {"whatsapp", "email", "sms", "push"}

    def test_notification_prefs_type(self, customer):
        proj = build_account(customer)
        assert all(isinstance(p, NotificationPrefProjection) for p in proj.notification_prefs)

    def test_notification_prefs_disabled_by_default(self, customer):
        proj = build_account(customer)
        assert all(not p.enabled for p in proj.notification_prefs)


# ──────────────────────────────────────────────────────────────────────
# Food preferences
# ──────────────────────────────────────────────────────────────────────


class TestCustomerProfileFoodPrefs:
    def test_food_prefs_all_options(self, customer):
        proj = build_account(customer)
        assert len(proj.food_pref_options) == 8

    def test_food_prefs_type(self, customer):
        proj = build_account(customer)
        assert all(isinstance(p, FoodPrefProjection) for p in proj.food_pref_options)

    def test_food_prefs_inactive_by_default(self, customer):
        proj = build_account(customer)
        assert all(not p.is_active for p in proj.food_pref_options)

    def test_food_pref_active_after_set(self, customer):
        from shopman.guestman.contrib.preferences import PreferenceService

        PreferenceService.set_preference(
            customer.ref, "alimentar", "vegano", value=True,
            preference_type="restriction", source="test",
        )
        proj = build_account(customer)
        vegano = next(p for p in proj.food_pref_options if p.key == "vegano")
        assert vegano.is_active is True
