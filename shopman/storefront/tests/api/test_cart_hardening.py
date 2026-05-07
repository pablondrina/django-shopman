from __future__ import annotations

import json

import pytest

pytestmark = pytest.mark.django_db


def test_api_cart_rejects_absurd_qty_before_business_logic(client):
    resp = client.post(
        "/api/v1/cart/items/",
        data=json.dumps({"sku": "ANY-SKU", "qty": 1000000}),
        content_type="application/json",
    )

    assert resp.status_code == 400
    assert "qty" in resp.json()


def test_api_cart_rejects_oversized_sku_before_lookup(client):
    resp = client.post(
        "/api/v1/cart/items/",
        data=json.dumps({"sku": "X" * 1000, "qty": 1}),
        content_type="application/json",
    )

    assert resp.status_code == 400
    assert "sku" in resp.json()
