"""Pagamento em dinheiro no checkout headless: método + troco chegam ao pedido.

Regressão do audit pré-go-live: o Nuxt coletava e enviava ``change_for``, mas o
``CheckoutSerializer`` não tinha o campo — pedido em dinheiro nascia sem
``payment.method`` e o entregador saía sem troco.
"""

from __future__ import annotations

import pytest
from shopman.orderman.models import Order

from shopman.storefront.models import DeliveryZone
from shopman.storefront.tests.api.test_storefront_surface import _seed_surface

pytestmark = pytest.mark.django_db

ADDRESS = {
    "formatted_address": "Rua das Flores, 1 - Centro",
    "postal_code": "86050-270",
    "neighborhood": "Centro",
}


def _checkout_payload(**over):
    from django.utils import timezone

    payload = {
        "name": "Ana",
        "phone": "+5543999990001",
        "fulfillment_type": "delivery",
        "delivery_address": "Rua das Flores, 1",
        "delivery_address_structured": ADDRESS,
        "delivery_date": timezone.localdate().isoformat(),
        "payment_method": "cash",
        "change_for": "100,00",
    }
    payload.update(over)
    return payload


def test_cash_checkout_records_method_and_change(client):
    from shopman.shop.models import Shop

    _seed_surface()
    DeliveryZone.objects.create(
        shop=Shop.objects.first(),
        name="Centro",
        zone_type=DeliveryZone.ZONE_TYPE_CEP_PREFIX,
        match_value="860",
        fee_q=600,
    )

    add = client.put(
        "/api/v1/cart/skus/PAO-FRANCES/",
        data={"qty": 2},
        content_type="application/json",
    )
    assert add.status_code == 200, add.content

    resp = client.post(
        "/api/v1/checkout/",
        data=_checkout_payload(),
        content_type="application/json",
    )
    assert resp.status_code == 201, resp.content

    order = Order.objects.get(ref=resp.json()["order_ref"])
    payment = order.data["payment"]
    assert payment["method"] == "cash"
    assert payment["change_for_q"] == 10000
    # E a taxa de entrega entrou na cobrança (linha + total).
    assert int(order.total_q) == 2 * 90 + 600
