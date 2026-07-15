"""Fixtures for the storefront security suite.

Reuses the web-surface fixtures (Shop singleton, channel, products, orders,
customers, cart helpers) so the adversarial tests exercise the real API with
the same seed data the contract tests use. Adds security-specific helpers:
login-as-customer, a second (attacker) customer, and a clean attacker client.
"""
from __future__ import annotations

import pytest
from django.test import Client

# Re-export the web-surface fixtures into this directory's namespace. pytest
# registers fixtures imported into a conftest, so the security tests can request
# them by name exactly as the web tests do.
from shopman.storefront.tests.web.conftest import (  # noqa: F401
    _clear_rate_limit_cache,
    cart_session,
    cart_session_delivery,
    channel,
    collection,
    collection_inactive,
    collection_item,
    croissant,
    customer,
    customer_address,
    listing,
    listing_item,
    order,
    order_items,
    order_paid,
    order_with_payment,
    product,
    product_unavailable,
    product_unpublished,
    shop_instance,
)


def login_as_customer(client: Client, customer_obj):
    """Force-login a browser client as ``customer_obj`` via the phone-OTP backend.

    Mirrors the helper used across the web security tests so ownership checks
    that key on ``request.user`` / ``request.customer`` behave as in production.
    """
    from shopman.doorman.protocols.customer import AuthCustomerInfo
    from shopman.doorman.services._user_bridge import get_or_create_user_for_customer

    info = AuthCustomerInfo(
        uuid=customer_obj.uuid,
        name=customer_obj.name,
        phone=customer_obj.phone,
        email=getattr(customer_obj, "email", None) or None,
        is_active=True,
    )
    user, _ = get_or_create_user_for_customer(info)
    client.force_login(user, backend="shopman.doorman.backends.PhoneOTPBackend")
    return user


@pytest.fixture
def attacker():
    """A fresh client with no session grants and no login — the adversary."""
    return Client()


@pytest.fixture
def other_customer(db):
    """A second customer, distinct phone, used as the IDOR victim/attacker."""
    from shopman.guestman.models import Customer

    return Customer.objects.create(
        ref="CUST-EVE-002",
        first_name="Eve",
        last_name="Adversária",
        phone="5543988887777",
    )


@pytest.fixture
def victim_address(other_customer):
    """An address owned by ``other_customer`` — the IDOR target for addresses."""
    from shopman.guestman.models import CustomerAddress

    return CustomerAddress.objects.create(
        customer=other_customer,
        label="home",
        formatted_address="Rua Secreta 999 - Centro - Londrina",
        route="Rua Secreta",
        street_number="999",
        neighborhood="Centro",
        city="Londrina",
        is_default=True,
    )
