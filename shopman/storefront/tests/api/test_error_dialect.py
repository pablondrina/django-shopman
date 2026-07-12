"""Dialeto canônico de erro nas APIs do storefront.

Falha de serializer no checkout precisa sair no shape que o front consome:
``{detail, field, errors}`` — `finalizar.vue` roteia pelo ``field`` para
reabrir o passo certo e mostra ``detail`` inline. Mensagem em pt-br (i18n do
Django + locale pt_BR do DRF), nunca o shape DRF cru sem ``detail``.
"""

from __future__ import annotations

import json

import pytest

pytestmark = pytest.mark.django_db


def _post_checkout(client, payload: dict):
    return client.post(
        "/api/v1/checkout/",
        data=json.dumps(payload),
        content_type="application/json",
    )


def test_checkout_missing_phone_speaks_error_dialect(client):
    resp = _post_checkout(client, {"name": "Ana"})

    assert resp.status_code == 400
    body = resp.json()
    assert body["field"] == "phone"
    assert body["detail"] == "Este campo é obrigatório."
    assert body["errors"]["phone"] == ["Este campo é obrigatório."]


def test_checkout_oversized_field_message_is_pt_br(client):
    resp = _post_checkout(client, {"name": "A" * 500, "phone": "43999990000"})

    assert resp.status_code == 400
    body = resp.json()
    assert body["field"] == "name"
    assert "120" in body["detail"]
    assert "Ensure" not in body["detail"]
