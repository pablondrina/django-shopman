"""Hardening do endpoint canônico de carrinho (`PUT /api/v1/cart/skus/<sku>/`).

A quantidade é validada pelo serializer ANTES de qualquer lógica de negócio
(`SetSkuQtySerializer.qty` ∈ [0, 99]), então um valor absurdo é rejeitado com 400
sem tocar no catálogo/estoque — e a resposta fala o dialeto canônico de erro
(`{detail, field, errors}`, ver shopman/shop/api_errors.py), nunca o shape DRF
cru `{"qty": [...]}` que o front não lê.
"""

from __future__ import annotations

import json

import pytest

pytestmark = pytest.mark.django_db


def test_api_cart_rejects_absurd_qty_before_business_logic(client):
    resp = client.put(
        "/api/v1/cart/skus/ANY-SKU/",
        data=json.dumps({"qty": 1000000}),
        content_type="application/json",
    )

    assert resp.status_code == 400
    body = resp.json()
    assert body["field"] == "qty"
    assert body["detail"]
    assert body["errors"]["qty"]
