"""IDOR de pedidos fechado — 404 uniforme p/ não-dono (canoniza o pentest do QA).

Complementa `test_order_access_security.py`: aquele cobre ref-guess anônimo em
tracking/payment/reorder; aqui fechamos as lacunas que o QA exercitou —
confirmation/cancel/confirm-received, e o não-dono LOGADO (não só anônimo),
provando que o 404 é idêntico ao de um ref inexistente (sem enumeração).
"""

from __future__ import annotations

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


def test_confirmation_ref_guess_returns_404(order):
    attacker = Client()
    resp = attacker.get(f"/api/v1/orders/{order.ref}/confirmation/")
    assert resp.status_code == 404


def test_cancel_ref_guess_returns_404(order):
    attacker = Client()
    resp = attacker.post(f"/api/v1/orders/{order.ref}/cancel/")
    assert resp.status_code == 404


def test_confirm_received_ref_guess_returns_404(order):
    attacker = Client()
    resp = attacker.post(f"/api/v1/orders/{order.ref}/confirm-received/")
    assert resp.status_code == 404


def test_logged_in_non_owner_gets_404_identical_to_nonexistent(order):
    """Um cliente LOGADO que não é dono do pedido recebe o MESMO 404 que um ref
    inexistente — sem oráculo de existência (anti-enumeração)."""
    stranger = Customer.objects.create(
        ref="CUS-STRANGER-01",
        first_name="Estranho",
        phone="+5543988887777",
    )
    browser = Client()
    _login_as_customer(browser, stranger)

    not_owner = browser.get(f"/api/v1/tracking/{order.ref}/")
    nonexistent = browser.get("/api/v1/tracking/ORD-DOES-NOT-EXIST/")

    assert not_owner.status_code == 404
    assert nonexistent.status_code == 404
    assert not_owner.status_code == nonexistent.status_code
