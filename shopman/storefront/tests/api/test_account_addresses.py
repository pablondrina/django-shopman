from __future__ import annotations

import json

import pytest
from django.test import Client
from shopman.guestman.models import Customer, CustomerAddress

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


def test_account_address_create_accepts_manual_address_without_place_id(client: Client):
    customer = Customer.objects.create(
        ref="CUS-ADDR-API-01",
        first_name="Ana",
        phone="+5543999991010",
    )
    _login_as_customer(client, customer)

    response = client.post(
        "/api/v1/account/addresses/",
        data=json.dumps({
            "label": "home",
            "formatted_address": "Rua Manual, 123 - Centro, Londrina - PR",
            "place_id": None,
            "is_default": True,
        }),
        content_type="application/json",
    )

    assert response.status_code == 201
    data = response.json()
    assert data["formatted_address"] == "Rua Manual, 123 - Centro, Londrina - PR"
    assert data["place_id"] == ""
    address = CustomerAddress.objects.get(customer=customer)
    assert address.place_id == ""


def test_account_address_list_exposes_display_and_edit_labels(client: Client):
    customer = Customer.objects.create(
        ref="CUS-ADDR-API-LABEL",
        first_name="Alice",
        phone="+5543999991099",
    )
    CustomerAddress.objects.create(
        customer=customer,
        label="other",
        label_custom="Casa da mãe",
        formatted_address="Rua Familia, 45",
        is_default=True,
    )
    _login_as_customer(client, customer)

    response = client.get("/api/v1/account/addresses/")

    assert response.status_code == 200
    data = response.json()
    assert data[0]["label"] == "Casa da mãe"
    assert data[0]["label_key"] == "other"
    assert data[0]["label_custom"] == "Casa da mãe"


def test_account_address_update_accepts_manual_address_without_place_id(client: Client):
    customer = Customer.objects.create(
        ref="CUS-ADDR-API-02",
        first_name="Bia",
        phone="+5543999991011",
    )
    address = CustomerAddress.objects.create(
        customer=customer,
        label="home",
        formatted_address="Rua Antiga, 10",
        place_id="ChIJ-old",
        is_default=True,
    )
    _login_as_customer(client, customer)

    response = client.patch(
        f"/api/v1/account/addresses/{address.pk}/",
        data=json.dumps({
            "label": "home",
            "formatted_address": "Rua Manual Atualizada, 456",
            "place_id": None,
        }),
        content_type="application/json",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["formatted_address"] == "Rua Manual Atualizada, 456"
    assert data["place_id"] == ""
    address.refresh_from_db()
    assert address.place_id == ""


def test_account_address_update_can_set_default(client: Client):
    customer = Customer.objects.create(
        ref="CUS-ADDR-API-03",
        first_name="Caio",
        phone="+5543999991012",
    )
    previous_default = CustomerAddress.objects.create(
        customer=customer,
        label="home",
        formatted_address="Rua Principal, 1",
        place_id="ChIJ-default",
        is_default=True,
    )
    address = CustomerAddress.objects.create(
        customer=customer,
        label="work",
        formatted_address="Rua Trabalho, 20",
        place_id="ChIJ-work",
        is_default=False,
    )
    _login_as_customer(client, customer)

    response = client.patch(
        f"/api/v1/account/addresses/{address.pk}/",
        data=json.dumps({
            "label": "work",
            "formatted_address": "Rua Trabalho, 20",
            "place_id": "ChIJ-work",
            "is_default": True,
        }),
        content_type="application/json",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["is_default"] is True
    address.refresh_from_db()
    previous_default.refresh_from_db()
    assert address.is_default is True
    assert previous_default.is_default is False


def test_account_address_update_manual_replacement_clears_old_coordinates(client: Client):
    customer = Customer.objects.create(
        ref="CUS-ADDR-API-04",
        first_name="Dora",
        phone="+5543999991013",
    )
    address = CustomerAddress.objects.create(
        customer=customer,
        label="home",
        formatted_address="Rua Autocomplete, 10",
        place_id="ChIJ-old-coords",
        latitude=-23.3000000,
        longitude=-51.1700000,
        is_verified=True,
        is_default=True,
    )
    _login_as_customer(client, customer)

    response = client.patch(
        f"/api/v1/account/addresses/{address.pk}/",
        data=json.dumps({
            "label": "home",
            "formatted_address": "Rua Manual Sem Place, 77",
            "place_id": None,
        }),
        content_type="application/json",
    )

    assert response.status_code == 200
    data = response.json()
    assert data["place_id"] == ""
    assert data["latitude"] is None
    assert data["longitude"] is None
    address.refresh_from_db()
    assert address.place_id == ""
    assert address.latitude is None
    assert address.longitude is None
    assert address.is_verified is False
