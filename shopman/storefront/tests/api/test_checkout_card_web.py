"""Checkout com cartão no canal `web` (payment.timing=post_commit).

Regressão: para `card` no `post_commit`, o dispatch de on_commit inicia o
pagamento (``_should_initiate_payment_on_commit`` → True) DENTRO da instância
selada do pedido recém-criado. O snapshot selado aliasava o mesmo objeto que
``order.data`` (ambos vinham de ``session.data``), então gravar
``idempotency_key`` em ``order.data["payment"]`` vazava para o snapshot em
memória e o sealed check derrubava o save com ``sealed_field_modified``,
retornando HTTP 400 e deixando um pedido órfão em ``new``.

PIX escapava porque inicia depois, a partir de um pedido recarregado do banco
(``data`` e ``snapshot`` decodificados em objetos distintos).

Precisa de ``transaction=True``: o dispatch de on_commit roda via
``transaction.on_commit`` e só dispara quando a transação realmente commita.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from shopman.orderman.models import Order

from shopman.storefront.models import DeliveryZone
from shopman.storefront.tests.api.test_storefront_surface import _seed_surface

ADDRESS = {
    "formatted_address": "Rua das Flores, 1 - Centro",
    "postal_code": "86050-270",
    "neighborhood": "Centro",
}


@pytest.mark.django_db(transaction=True)
def test_card_checkout_on_web_commits_and_initiates_payment(client):
    from django.utils import timezone
    from shopman.payman import PaymentService

    from shopman.shop.models import Shop

    _seed_surface(stock_qty=Decimal("10"))
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
        data={
            "name": "Ana",
            "phone": "+5543999990001",
            "fulfillment_type": "delivery",
            "delivery_address": "Rua das Flores, 1",
            "delivery_address_structured": ADDRESS,
            "delivery_date": timezone.localdate().isoformat(),
            "payment_method": "card",
        },
        content_type="application/json",
    )
    assert resp.status_code == 201, resp.content

    order = Order.objects.get(ref=resp.json()["order_ref"])
    assert order.data["payment"]["method"] == "card"
    # O intent de cartão foi iniciado no on_commit (post_commit + card).
    assert order.data["payment"].get("intent_ref")
    assert list(PaymentService.get_by_order(order.ref)), "esperava um intent de cartão"

    # O snapshot selado NÃO pode carregar o idempotency_key gravado em order.data:
    # se carregar, o alias voltou e o sealed check quebra de novo.
    snapshot_payment = (order.snapshot.get("data") or {}).get("payment") or {}
    assert "idempotency_key" not in snapshot_payment
