"""A taxa de entrega é COBRADA: vira linha do pedido e entra em ``Order.total_q``.

Regressão do audit pré-go-live: a taxa vivia só em ``session.data["delivery_fee_q"]``
e ``Order.total_q`` é a soma das linhas — PIX/cartão/fiscal cobravam o total SEM a
taxa, enquanto o checkout exibia o total COM a taxa. O ``DeliveryFeeModifier`` agora
mantém a linha ``__DELIVERY_FEE__`` (escritor único, ``meta.source``) em sincronia
com a taxa resolvida; a linha manual do POS nunca é tocada.
"""

from __future__ import annotations

import pytest
from shopman.offerman.models import Product
from shopman.orderman.models import Order

from shopman.shop.models import Channel, Shop
from shopman.shop.projections.cart import build_cart
from shopman.shop.services import sessions
from shopman.storefront.models import DeliveryZone

pytestmark = pytest.mark.django_db

FEE_Q = 600
ADDRESS = {"postal_code": "86050-270", "neighborhood": "Centro"}


@pytest.fixture
def channel(db):
    shop = Shop.objects.create(name="Test Shop")
    Product.objects.create(sku="PAO-TESTE", name="Pão", base_price_q=2500)
    DeliveryZone.objects.create(
        shop=shop,
        name="Londrina Norte",
        zone_type=DeliveryZone.ZONE_TYPE_CEP_PREFIX,
        match_value="860",
        fee_q=FEE_Q,
    )
    return Channel.objects.create(ref="web", name="Web")


def _modify(session, ops):
    return sessions.modify_session(
        session_key=session.session_key,
        channel_ref=session.channel_ref,
        ops=ops,
    )


def _session_with_delivery_cart(channel, *, address=ADDRESS):
    session = sessions.create_session(channel.ref)
    _modify(session, [
        {"op": "add_line", "sku": "PAO-TESTE", "name": "Pão", "qty": 2, "unit_price_q": 2500},
        {"op": "set_data", "path": "customer", "value": {"name": "Ana", "phone": "+5543999990001"}},
        {"op": "set_data", "path": "fulfillment_type", "value": "delivery"},
        {"op": "set_data", "path": "delivery_address", "value": "Rua das Flores, 1"},
        {"op": "set_data", "path": "delivery_address_structured", "value": address},
    ])
    session.refresh_from_db()
    return session


def _fee_lines(items):
    return [i for i in items if i.get("sku") == "__DELIVERY_FEE__"]


def test_delivery_fee_becomes_order_line_and_enters_total(channel):
    session = _session_with_delivery_cart(channel)

    assert session.data["delivery_fee_q"] == FEE_Q
    assert len(_fee_lines(session.items)) == 1

    result = sessions.commit_session(
        session_key=session.session_key,
        channel_ref=channel.ref,
        idempotency_key=sessions.new_idempotency_key(),
    )
    order = Order.objects.get(ref=result.order_ref)

    fee_items = [i for i in order.items.all() if i.sku == "__DELIVERY_FEE__"]
    assert len(fee_items) == 1
    assert int(fee_items[0].line_total_q) == FEE_Q
    # O que o pagamento/fiscal cobram (total_q) = o que o checkout exibiu.
    assert int(order.total_q) == 2 * 2500 + FEE_Q
    assert order.data["delivery_fee_q"] == FEE_Q


def test_fee_line_is_idempotent_across_modify_passes(channel):
    session = _session_with_delivery_cart(channel)
    _modify(session, [{"op": "set_data", "path": "order_notes", "value": "sem cebola"}])
    session.refresh_from_db()
    assert len(_fee_lines(session.items)) == 1


def test_switching_to_pickup_removes_fee_line_and_data(channel):
    session = _session_with_delivery_cart(channel)
    _modify(session, [{"op": "set_data", "path": "fulfillment_type", "value": "pickup"}])
    session.refresh_from_db()

    assert _fee_lines(session.items) == []
    assert "delivery_fee_q" not in (session.data or {})


def test_excluded_zone_has_no_fee_line(channel):
    # Bloqueio LEGÍTIMO: zona de exclusão explícita (não entregamos ali) → sem linha de taxa.
    # (Sem coordenada e sem zona NÃO bloqueia mais — ver test_no_zone_no_coords_fails_open.)
    shop = Shop.objects.first()
    DeliveryZone.objects.create(
        shop=shop,
        name="Fora da área",
        zone_type=DeliveryZone.ZONE_TYPE_CEP_PREFIX,
        match_value="870",
        mode=DeliveryZone.MODE_EXCLUDE,
    )
    session = _session_with_delivery_cart(
        channel, address={"postal_code": "87000-000", "neighborhood": "Outra Cidade"}
    )
    assert session.data.get("delivery_zone_error") is True
    assert _fee_lines(session.items) == []


def test_manual_pos_fee_line_is_never_touched(channel):
    session = sessions.create_session(channel.ref)
    _modify(session, [
        {"op": "add_line", "sku": "PAO-TESTE", "name": "Pão", "qty": 1, "unit_price_q": 2500},
        {
            "op": "add_line",
            "sku": "__DELIVERY_FEE__",
            "name": "Taxa de entrega",
            "qty": 1,
            "unit_price_q": 1200,
            "meta": {"type": "delivery_fee", "non_production": True},
        },
        {"op": "set_data", "path": "fulfillment_type", "value": "delivery"},
        {"op": "set_data", "path": "delivery_address_structured", "value": ADDRESS},
    ])
    session.refresh_from_db()

    fee_lines = _fee_lines(session.items)
    assert len(fee_lines) == 1
    # A linha manual (POS) vence: o modifier não cria uma segunda nem reprecifica.
    assert fee_lines[0]["unit_price_q"] == 1200


def test_fee_line_removed_when_cart_has_no_merchandise(channel):
    session = _session_with_delivery_cart(channel)
    line_id = next(
        i["line_id"] for i in session.items if i["sku"] == "PAO-TESTE"
    )
    _modify(session, [{"op": "remove_line", "line_id": line_id}])
    session.refresh_from_db()

    # Sem mercadoria não há o que entregar: a taxa não pode virar pedido sozinha.
    assert _fee_lines(session.items) == []


def test_cart_projection_does_not_double_count_fee(channel):
    session = _session_with_delivery_cart(channel)
    cart = build_cart(session.session_key, channel.ref)

    assert all(line.sku != "__DELIVERY_FEE__" for line in cart.lines)
    assert cart.subtotal_q == 2 * 2500
    assert cart.delivery_fee_q == FEE_Q
    assert cart.grand_total_q == 2 * 2500 + FEE_Q


def test_delivery_without_verified_zone_cannot_commit(channel):
    from shopman.orderman.exceptions import ValidationError as OrderingValidationError

    session = sessions.create_session(channel.ref)
    _modify(session, [
        {"op": "add_line", "sku": "PAO-TESTE", "name": "Pão", "qty": 1, "unit_price_q": 2500},
        {"op": "set_data", "path": "customer", "value": {"name": "Ana", "phone": "+5543999990001"}},
        {"op": "set_data", "path": "fulfillment_type", "value": "delivery"},
        # Endereço só-texto, sem CEP/bairro/coordenada: zona nunca verificada.
        {"op": "set_data", "path": "delivery_address", "value": "Rua Qualquer, 123"},
    ])
    with pytest.raises(OrderingValidationError) as exc_info:
        sessions.commit_session(
            session_key=session.session_key,
            channel_ref=channel.ref,
            idempotency_key=sessions.new_idempotency_key(),
        )
    assert exc_info.value.code == "delivery_zone_unverified"


def test_commit_rejects_when_total_drifted_from_display(channel):
    from shopman.orderman.exceptions import ValidationError as OrderingValidationError

    from shopman.shop.services import checkout as checkout_service

    session = _session_with_delivery_cart(channel)
    shown_total_q = 2 * 2500 + FEE_Q

    with pytest.raises(OrderingValidationError) as exc_info:
        checkout_service.process_ops(
            session_key=session.session_key,
            channel_ref=channel.ref,
            ops=[],
            idempotency_key=sessions.new_idempotency_key(),
            expected_total_q=shown_total_q - 500,  # cliente viu outro valor
        )
    assert exc_info.value.code == "total_changed"

    # Com o total certo, o commit passa.
    result = checkout_service.process_ops(
        session_key=session.session_key,
        channel_ref=channel.ref,
        ops=[],
        idempotency_key=sessions.new_idempotency_key(),
        expected_total_q=shown_total_q,
    )
    assert result.total_q == shown_total_q


def test_spoofed_coordinates_blocked_at_commit(channel, monkeypatch):
    """Antifraude: lat/lng "perto da loja" com CEP de outra cidade não commita.

    A taxa por distância confia na coordenada do browser; o servidor agora
    reverte a coordenada (geocode server-side) e exige coerência com o CEP/
    cidade alegados.
    """
    from types import SimpleNamespace

    from shopman.orderman.exceptions import ValidationError as OrderingValidationError

    from shopman.shop.rules import validation as validation_module

    monkeypatch.setattr(
        "shopman.shop.services.geocoding.reverse_geocode",
        lambda lat, lng: SimpleNamespace(postal_code="86010-000", city="Londrina"),
    )

    session_data = {
        "fulfillment_type": "delivery",
        "delivery_fee_q": 100,  # menor taxa, "conquistada" com coordenada forjada
        "delivery_address_structured": {
            "postal_code": "01310-100",  # alegou Av. Paulista, SP
            "city": "São Paulo",
            "latitude": -23.31, "longitude": -51.16,  # mas a coordenada é Londrina
        },
    }
    session = SimpleNamespace(data=session_data, items=[], pricing={})

    with pytest.raises(OrderingValidationError) as exc_info:
        validation_module.DeliveryZoneRule().validate(channel=None, session=session, ctx={})
    assert exc_info.value.code == "delivery_address_mismatch"


def test_coherent_coordinates_pass(channel, monkeypatch):
    from types import SimpleNamespace

    from shopman.shop.rules import validation as validation_module

    monkeypatch.setattr(
        "shopman.shop.services.geocoding.reverse_geocode",
        lambda lat, lng: SimpleNamespace(postal_code="86050-270", city="Londrina"),
    )
    session_data = {
        "fulfillment_type": "delivery",
        "delivery_fee_q": 600,
        "delivery_address_structured": {
            "postal_code": "86050-999",  # mesmo prefixo de 5 dígitos
            "city": "Londrina",
            "latitude": -23.31, "longitude": -51.16,
        },
    }
    session = SimpleNamespace(data=session_data, items=[], pricing={})
    validation_module.DeliveryZoneRule().validate(channel=None, session=session, ctx={})


def test_city_accent_difference_does_not_block(channel, monkeypatch):
    from types import SimpleNamespace

    from shopman.shop.rules import validation as validation_module

    # Google resolve "São Paulo" (com acento); o cliente digitou "Sao Paulo".
    monkeypatch.setattr(
        "shopman.shop.services.geocoding.reverse_geocode",
        lambda lat, lng: SimpleNamespace(postal_code="01310-100", city="São Paulo"),
    )
    session_data = {
        "fulfillment_type": "delivery",
        "delivery_fee_q": 600,
        "delivery_address_structured": {
            "postal_code": "99999-000",  # CEP diverge de propósito
            "city": "Sao Paulo",         # sem acento
            "latitude": -23.56, "longitude": -46.65,
        },
    }
    session = SimpleNamespace(data=session_data, items=[], pricing={})
    # Não levanta: a cidade casa após normalizar acento.
    validation_module.DeliveryZoneRule().validate(channel=None, session=session, ctx={})
