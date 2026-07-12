"""Sem oversell na corrida pelo último item (canoniza o pentest do QA).

Duas sessões independentes (cookie jars separados) disputam a última unidade:
a primeira reserva no add-to-cart (200), a segunda bate no gate de estoque e
recebe 409 com o payload rico de indisponibilidade. Versão determinística
(sequencial, SQLite) da invariante que o stress test PostgreSQL
(`test_concurrent_checkout`) exercita sob concorrência real.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest
from django.test import Client

from shopman.storefront.tests.api.test_storefront_surface import _seed_surface

pytestmark = pytest.mark.django_db


def _add_last_unit(c: Client):
    return c.put(
        "/api/v1/cart/skus/PAO-FRANCES/",
        data=json.dumps({"qty": 1}),
        content_type="application/json",
    )


def test_last_unit_race_one_succeeds_other_gets_409():
    _seed_surface(stock_qty=Decimal("1"))
    first, second = Client(), Client()

    winner = _add_last_unit(first)
    loser = _add_last_unit(second)

    assert winner.status_code == 200, winner.content
    assert loser.status_code == 409, loser.content
    body = loser.json()
    # 409 traz o contrato rico p/ o cliente reagir (sem estourar).
    assert body["items"][0]["sku"] == "PAO-FRANCES"
    assert body["items"][0]["available_qty"] == 0
