from __future__ import annotations

import json
from datetime import date

import pytest
from django.test import Client
from shopman.guestman.models import Customer

pytestmark = pytest.mark.django_db


def _login_as_customer(client: Client, customer: Customer):
    from shopman.doorman.protocols.customer import AuthCustomerInfo
    from shopman.doorman.services._user_bridge import get_or_create_user_for_customer

    info = AuthCustomerInfo(
        uuid=customer.uuid,
        name=customer.name,
        phone=customer.phone,
        email=getattr(customer, "email", None) or None,
        is_active=True,
    )
    user, _ = get_or_create_user_for_customer(info)
    client.force_login(user, backend="shopman.doorman.backends.PhoneOTPBackend")
    return user


def test_account_summary_returns_customer_memory_contract(client: Client):
    customer = Customer.objects.create(
        ref="CUS-SUMMARY-01",
        first_name="Ana",
        last_name="Silva",
        phone="+5543999990003",
        email="ana.summary@example.com",
    )
    _login_as_customer(client, customer)

    response = client.get("/api/v1/account/summary/")

    assert response.status_code == 200
    data = response.json()
    assert data["customer_first_name"] == "Ana"
    assert data["recent_order_count"] == 0
    assert data["last_order"] is None
    assert data["loyalty"] is None
    assert isinstance(data["food_preferences"], list)
    assert isinstance(data["notification_preferences"], list)


def test_account_profile_get_returns_editable_fields(client: Client):
    customer = Customer.objects.create(
        ref="CUS-PROFILE-01",
        first_name="Ana",
        last_name="Silva",
        phone="+5543999990004",
        email="ana.profile@example.com",
        birthday=date(1990, 5, 14),
    )
    _login_as_customer(client, customer)

    response = client.get("/api/v1/account/profile/")

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Ana Silva"
    assert data["first_name"] == "Ana"
    assert data["last_name"] == "Silva"
    assert data["email"] == "ana.profile@example.com"
    assert data["birthday"] == "1990-05-14"


def test_account_profile_patch_persists_before_returning_success(client: Client):
    customer = Customer.objects.create(
        ref="CUS-PROFILE-02",
        first_name="Bia",
        last_name="Lima",
        phone="+5543999990005",
        email="bia.old@example.com",
    )
    _login_as_customer(client, customer)

    response = client.patch(
        "/api/v1/account/profile/",
        data=json.dumps({
            "first_name": "Beatriz",
            "last_name": "Lima Costa",
            "email": "bia.new@example.com",
            "birthday": "1991-06-15",
        }),
        content_type="application/json",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Beatriz Lima Costa"
    assert data["first_name"] == "Beatriz"
    assert data["last_name"] == "Lima Costa"
    assert data["email"] == "bia.new@example.com"
    assert data["birthday"] == "1991-06-15"
    customer.refresh_from_db()
    assert customer.first_name == "Beatriz"
    assert customer.last_name == "Lima Costa"
    assert customer.email == "bia.new@example.com"
    assert customer.birthday == date(1991, 6, 15)


def test_account_profile_patch_enforces_csrf():
    """W2: mutação de perfil exige CSRF (SessionAuthentication). Sem token → 403."""
    customer = Customer.objects.create(
        ref="CUS-PROFILE-CSRF",
        first_name="Caio",
        phone="+5543999990006",
    )
    csrf_client = Client(enforce_csrf_checks=True)
    _login_as_customer(csrf_client, customer)

    response = csrf_client.patch(
        "/api/v1/account/profile/",
        data=json.dumps({"first_name": "Caião"}),
        content_type="application/json",
    )

    assert response.status_code == 403
    customer.refresh_from_db()
    assert customer.first_name == "Caio"  # não persistiu


def test_account_profile_patch_failure_does_not_mutate_customer(client: Client):
    customer = Customer.objects.create(
        ref="CUS-PROFILE-03",
        first_name="Clara",
        phone="+5543999990006",
        email="clara@example.com",
    )
    _login_as_customer(client, customer)

    response = client.patch(
        "/api/v1/account/profile/",
        data=json.dumps({"first_name": "", "email": "changed@example.com"}),
        content_type="application/json",
    )

    assert response.status_code == 400
    customer.refresh_from_db()
    assert customer.first_name == "Clara"
    assert customer.email == "clara@example.com"
