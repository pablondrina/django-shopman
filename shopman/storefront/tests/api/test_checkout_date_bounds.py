"""Bordas de data no checkout headless (`/api/v1/checkout/`).

Regressão do QA exploratório (P1): o gate autoritativo checava só ``is_open_on``
e "hoje já fechou" — data no PASSADO era commitada (pedido para ontem, 201) e
não havia teto de janela (encomenda para 2027 passava). A validação correta
morava no caminho HTMX morto (``_validate_preorder``), com falsa cobertura.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from shopman.storefront.tests.api.test_storefront_surface import _seed_surface

pytestmark = pytest.mark.django_db


def _add_item(client) -> None:
    resp = client.put(
        "/api/v1/cart/skus/PAO-FRANCES/",
        data={"qty": 2},
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.content


def _checkout(client, delivery_date: str):
    return client.post(
        "/api/v1/checkout/",
        data={
            "name": "Ana",
            "phone": "+5543999990001",
            "fulfillment_type": "pickup",
            "delivery_date": delivery_date,
            "delivery_time_slot": "08:00",
        },
        content_type="application/json",
    )


def test_past_delivery_date_is_rejected(client):
    _seed_surface()
    _add_item(client)

    yesterday = (timezone.localdate() - timedelta(days=1)).isoformat()
    resp = _checkout(client, yesterday)

    assert resp.status_code == 400, resp.content
    body = resp.json()
    assert body["field"] == "delivery_date"
    assert "passada" in body["detail"]


def test_delivery_date_beyond_preorder_window_is_rejected(client):
    _seed_surface()
    _add_item(client)

    # Default max_preorder_days == 30; 60 dias à frente estoura a janela.
    far = (timezone.localdate() + timedelta(days=60)).isoformat()
    resp = _checkout(client, far)

    assert resp.status_code == 400, resp.content
    body = resp.json()
    assert body["field"] == "delivery_date"
    assert "máxima" in body["detail"]
