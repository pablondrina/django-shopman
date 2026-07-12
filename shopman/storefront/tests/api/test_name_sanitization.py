"""Sanitização de nomes: strip de controle/bidi + limite de comprimento.

Regressão do audit pré-staging: ``first_name``/``last_name`` chegavam ao perfil
(e daí ao ticket do KDS/pedido) sem limite de tamanho nem strip de caracteres de
controle/bidi Unicode — vetor de spoofing (Trojan Source) e de nome gigante no
ticket. ``clean_name`` fecha os dois.
"""
from __future__ import annotations

import json

import pytest
from django.test import Client
from shopman.guestman.models import Customer

from shopman.storefront.api import clean_name, clean_text

pytestmark = pytest.mark.django_db


# ── unit: clean_name ──────────────────────────────────────────────────


def test_clean_name_strips_bidi_override():
    # U+202E RIGHT-TO-LEFT OVERRIDE no meio do nome
    assert clean_name("Jo‮ao") == "Joao"


def test_clean_name_strips_control_chars_and_collapses_whitespace():
    assert clean_name("Ana\tMaria\nSilva") == "Ana Maria Silva"
    assert clean_name("Ana\x00\x07Bia") == "Ana Bia"


def test_clean_name_caps_length():
    assert len(clean_name("x" * 250)) == 100
    assert len(clean_name("x" * 250, max_length=120)) == 120


def test_clean_name_non_string_is_empty():
    assert clean_name(42) == ""
    assert clean_name(None) == ""


def test_clean_text_strips_zero_width_but_keeps_newlines():
    # zero-width space removido, mas \n preservado (campos multi-linha)
    assert clean_text("a​b") == "ab"
    assert clean_text("linha1\nlinha2") == "linha1\nlinha2"


# ── integration: profile PATCH persiste o nome sanitizado ─────────────


def _login_as_customer(client: Client, customer: Customer):
    from shopman.doorman.protocols.customer import AuthCustomerInfo
    from shopman.doorman.services._user_bridge import get_or_create_user_for_customer

    info = AuthCustomerInfo(
        uuid=customer.uuid, name=customer.name, phone=customer.phone,
        email=getattr(customer, "email", None) or None, is_active=True,
    )
    user, _ = get_or_create_user_for_customer(info)
    client.force_login(user, backend="shopman.doorman.backends.PhoneOTPBackend")


def test_profile_patch_sanitizes_and_caps_name(client: Client):
    customer = Customer.objects.create(
        ref="CUS-NAME-01", first_name="Antigo", phone="+5543988885555"
    )
    _login_as_customer(client, customer)

    resp = client.patch(
        "/api/v1/account/profile/",
        data=json.dumps({"first_name": "Jo‮ao", "last_name": "y" * 250}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    customer.refresh_from_db()
    assert "‮" not in customer.first_name
    assert customer.first_name == "Joao"
    assert len(customer.last_name) == 100
