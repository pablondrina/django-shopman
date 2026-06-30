from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command
from shopman.orderman.models import Order

from shopman.shop.services.dispatch_handoff import (
    NotDeliverableError,
    build_dispatch_payload,
    format_dispatch_text,
)

pytestmark = pytest.mark.django_db


def _delivery_order(**data_overrides) -> Order:
    data = {
        "fulfillment_type": "delivery",
        "customer": {"name": "Ana Lima", "phone": "5543999990000"},
        "delivery_address_structured": {
            "route": "Rua das Flores",
            "street_number": "123",
            "complement": "Apto 4B",
            "neighborhood": "Centro",
            "city": "Londrina",
            "state_code": "PR",
            "postal_code": "86010-000",
            "formatted_address": "Rua das Flores 123 - Centro - Londrina",
            "delivery_instructions": "Portão azul ao lado da padaria",
            "latitude": -23.31,
            "longitude": -51.16,
        },
        "delivery_distance_km": 2.5,
        "delivery_fee_q": 800,
    }
    data.update(data_overrides)
    return Order.objects.create(
        ref="TELE-1",
        channel_ref="web",
        session_key="TELE-SESSION",
        status=Order.Status.NEW,
        snapshot={"items": []},
        data=data,
        total_q=5000,
    )


def test_build_payload_extracts_structured_delivery_fields():
    order = _delivery_order()
    payload = build_dispatch_payload(order)

    assert payload["order_ref"] == "TELE-1"
    assert payload["customer_name"] == "Ana Lima"
    assert payload["customer_phone"] == "5543999990000"
    assert payload["route"] == "Rua das Flores"
    assert payload["street_number"] == "123"
    assert payload["complement"] == "Apto 4B"
    assert payload["postal_code"] == "86010-000"
    assert payload["distance_km"] == 2.5
    assert payload["delivery_fee_q"] == 800


def test_build_payload_rejects_pickup_order():
    order = _delivery_order(fulfillment_type="pickup")
    with pytest.raises(NotDeliverableError):
        build_dispatch_payload(order)


def test_format_text_is_paste_ready():
    payload = build_dispatch_payload(_delivery_order())
    text = format_dispatch_text(payload)

    assert "Pedido TELE-1" in text
    assert "Cliente: Ana Lima" in text
    assert "Telefone: 5543999990000" in text
    assert "Endereço: Rua das Flores 123" in text
    assert "Complemento: Apto 4B" in text
    assert "Bairro/Cidade: Centro, Londrina, PR" in text
    assert "CEP: 86010-000" in text
    assert "Referência: Portão azul ao lado da padaria" in text
    assert "Distância: 2.5 km" in text
    assert "Taxa de entrega: R$ 8,00" in text


def test_format_text_falls_back_to_formatted_address_without_route():
    payload = build_dispatch_payload(
        _delivery_order(
            delivery_address_structured={
                "formatted_address": "Av. Higienópolis 1000",
            }
        )
    )
    text = format_dispatch_text(payload)
    assert "Endereço: Av. Higienópolis 1000" in text


def test_command_prints_block_without_copy():
    order = _delivery_order()
    out = StringIO()
    call_command("teleporte", order.ref, "--no-copy", stdout=out)
    output = out.getvalue()
    assert "Pedido TELE-1" in output
    assert "Cliente: Ana Lima" in output


def test_command_json_emits_structured_payload():
    order = _delivery_order()
    out = StringIO()
    call_command("teleporte", order.ref, "--json", stdout=out)
    assert '"order_ref": "TELE-1"' in out.getvalue()


def test_command_errors_on_pickup():
    order = _delivery_order(fulfillment_type="pickup")
    from django.core.management.base import CommandError

    with pytest.raises(CommandError):
        call_command("teleporte", order.ref, "--no-copy", stdout=StringIO())
