"""Endereço: 404 uniforme para PK de outro cliente (fecha o oráculo de enumeração).

Regressão do audit pré-staging: PATCH/DELETE/POST em ``/account/addresses/<pk>/``
devolvia 403 quando o PK existia mas era de outro cliente, e 404 quando não
existia — distinguível, um oráculo de enumeração de PK. Agora ambos os casos são
404 idênticos (``get_address`` é escopado ao cliente), alinhado ao IDOR de pedidos.
"""
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


def _other_customer_address() -> CustomerAddress:
    other = Customer.objects.create(ref="CUS-OWNER-01", first_name="Dono", phone="+5543988880001")
    return CustomerAddress.objects.create(
        customer=other, label="home", formatted_address="Rua do Dono, 1", is_default=True,
    )


def _attacker(client: Client) -> None:
    attacker = Customer.objects.create(ref="CUS-ATTACKER-01", first_name="Intruso", phone="+5543988889999")
    _login_as_customer(client, attacker)


def test_patch_other_customer_address_is_404_not_403(client: Client):
    victim_addr = _other_customer_address()
    _attacker(client)
    resp = client.patch(
        f"/api/v1/account/addresses/{victim_addr.pk}/",
        data=json.dumps({"formatted_address": "Sequestrado"}),
        content_type="application/json",
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Endereço não encontrado."


def test_delete_other_customer_address_is_404_not_403(client: Client):
    victim_addr = _other_customer_address()
    _attacker(client)
    resp = client.delete(f"/api/v1/account/addresses/{victim_addr.pk}/")
    assert resp.status_code == 404
    victim_addr.refresh_from_db()  # não foi apagado


def test_set_default_other_customer_address_is_404_not_403(client: Client):
    victim_addr = _other_customer_address()
    _attacker(client)
    resp = client.post(f"/api/v1/account/addresses/{victim_addr.pk}/?action=default")
    assert resp.status_code == 404


def test_other_customer_pk_indistinguishable_from_nonexistent(client: Client):
    """O 404 do PK de outro cliente é idêntico ao de um PK inexistente."""
    victim_addr = _other_customer_address()
    _attacker(client)
    not_owner = client.delete(f"/api/v1/account/addresses/{victim_addr.pk}/")
    nonexistent = client.delete("/api/v1/account/addresses/99999999/")
    assert not_owner.status_code == nonexistent.status_code == 404
    assert not_owner.json() == nonexistent.json()
