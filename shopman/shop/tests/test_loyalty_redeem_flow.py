"""Resgate de pontos: o desconto dado é o débito feito — sempre, e uma vez só.

Regressão do audit pré-go-live: ``checkout_data["loyalty"]`` não estava na lista
de propagação do ``CommitService`` → o service de resgate retornava cedo e os
pontos nunca eram debitados (desconto infinito). E o débito, se existisse, usaria
o saldo integral pedido, não o desconto efetivamente aplicado (clampado ao
subtotal pelo ``LoyaltyRedeemModifier``).
"""

from __future__ import annotations

import pytest
from shopman.guestman.contrib.loyalty.service import LoyaltyService
from shopman.guestman.models import Customer
from shopman.offerman.models import Product
from shopman.orderman.models import Directive, Order

from shopman.shop.handlers.loyalty import LoyaltyRedeemHandler
from shopman.shop.models import Channel, Shop
from shopman.shop.services import sessions

pytestmark = pytest.mark.django_db

CUSTOMER_REF = "CUST-LOYAL-1"


@pytest.fixture
def channel(db):
    Shop.objects.create(name="Test Shop")
    Product.objects.create(sku="PAO-TESTE", name="Pão", base_price_q=2500)
    return Channel.objects.create(ref="web", name="Web")


@pytest.fixture
def customer(db):
    customer = Customer.objects.create(
        ref=CUSTOMER_REF, first_name="Ana", phone="+5543999990001"
    )
    LoyaltyService.enroll(CUSTOMER_REF)
    LoyaltyService.earn_points(
        CUSTOMER_REF, points=10_000, description="seed", reference="seed"
    )
    return customer


def _commit_with_loyalty(channel, *, redeem_q: int, django_capture_on_commit_callbacks):
    session = sessions.create_session(channel.ref)
    sessions.modify_session(
        session_key=session.session_key,
        channel_ref=channel.ref,
        ops=[
            {"op": "add_line", "sku": "PAO-TESTE", "name": "Pão", "qty": 2, "unit_price_q": 2500},
            {"op": "set_data", "path": "customer", "value": {"name": "Ana", "phone": "+5543999990001", "ref": CUSTOMER_REF}},
            {"op": "set_data", "path": "customer_ref", "value": CUSTOMER_REF},
            {"op": "set_data", "path": "fulfillment_type", "value": "pickup"},
            {"op": "set_data", "path": "loyalty", "value": {"redeem_points_q": redeem_q}},
        ],
    )
    with django_capture_on_commit_callbacks(execute=True):
        result = sessions.commit_session(
            session_key=session.session_key,
            channel_ref=channel.ref,
            idempotency_key=sessions.new_idempotency_key(),
        )
    return Order.objects.get(ref=result.order_ref)


def _redeem_directive(order):
    return Directive.objects.filter(
        topic="loyalty.redeem", payload__order_ref=order.ref
    ).first()


def test_commit_propagates_loyalty_and_queues_debit(channel, customer, django_capture_on_commit_callbacks):
    order = _commit_with_loyalty(channel, redeem_q=2000, django_capture_on_commit_callbacks=django_capture_on_commit_callbacks)

    assert order.data["loyalty"]["redeem_points_q"] == 2000
    assert order.data["loyalty"]["applied_discount_q"] == 2000
    assert int(order.total_q) == 2 * 2500 - 2000

    directive = _redeem_directive(order)
    assert directive is not None
    assert directive.payload["points"] == 2000


def test_debit_is_clamped_to_applied_discount(channel, customer, django_capture_on_commit_callbacks):
    # Pede mais pontos que o subtotal: desconto aplicado = subtotal, e o
    # débito segue o desconto — nunca o saldo pedido.
    order = _commit_with_loyalty(channel, redeem_q=8000, django_capture_on_commit_callbacks=django_capture_on_commit_callbacks)

    assert int(order.total_q) == 0
    assert order.data["loyalty"]["applied_discount_q"] == 5000

    directive = _redeem_directive(order)
    assert directive is not None
    assert directive.payload["points"] == 5000


def test_redeem_handler_debits_once_even_on_retry(channel, customer, django_capture_on_commit_callbacks):
    order = _commit_with_loyalty(channel, redeem_q=2000, django_capture_on_commit_callbacks=django_capture_on_commit_callbacks)
    directive = _redeem_directive(order)

    handler = LoyaltyRedeemHandler()
    handler.handle(message=directive, ctx={})
    handler.handle(message=directive, ctx={})  # retry at-least-once

    account = LoyaltyService.get_account(CUSTOMER_REF)
    assert account.points_balance == 10_000 - 2000


def test_loyalty_remainder_goes_to_last_merch_item_not_fee_line():
    """Resíduo do rateio vai no último item de MERCADORIA, não na linha de taxa.

    Regressão do code-review: com __DELIVERY_FEE__ como último item, o
    `is_last` caía na linha de taxa (pulada) e o resíduo sumia — débito de
    pontos ficava maior que o desconto aplicado. Invariante: débito == desconto.
    """
    from types import SimpleNamespace

    from shopman.shop.modifiers import LoyaltyRedeemModifier

    items = [
        {"sku": "PAO", "name": "Pão", "qty": 1, "unit_price_q": 1000, "line_total_q": 1000, "meta": {}},
        {"sku": "CROISSANT", "name": "Croissant", "qty": 1, "unit_price_q": 700, "line_total_q": 700, "meta": {}},
        {"sku": "__DELIVERY_FEE__", "name": "Taxa", "qty": 1, "unit_price_q": 600,
         "line_total_q": 600, "meta": {"type": "delivery_fee", "non_production": True}},
    ]
    saved = {}
    session = SimpleNamespace(
        items=items,
        data={"loyalty": {"redeem_points_q": 1000}},
        pricing={},
    )
    session.update_items = lambda new: setattr(session, "items", new)
    session.save = lambda **kw: saved.update(kw)

    LoyaltyRedeemModifier().apply(channel=None, session=session, ctx={})

    applied = session.data["loyalty"]["applied_discount_q"]
    # Todo o resgate (1000) foi aplicado a mercadoria.
    assert applied == 1000
    fee = next(i for i in session.items if i["sku"] == "__DELIVERY_FEE__")
    assert fee["line_total_q"] == 600  # taxa intocada
    merch_discount = (1000 - session.items[0]["line_total_q"]) + (700 - session.items[1]["line_total_q"])
    assert merch_discount == applied  # desconto real == débito


def test_insufficient_points_at_debit_alerts_operator(channel, customer):
    """Saldo abaixo do resgate na hora do débito: terminal + alerta (desconto
    foi dado no commit, ninguém debitou — operador precisa conciliar)."""
    import pytest as _pytest
    from shopman.guestman.contrib.loyalty.service import LoyaltyService
    from shopman.orderman.exceptions import DirectiveTerminalError
    from shopman.orderman.models import Directive, Order

    from shopman.backstage.models import OperatorAlert
    from shopman.shop.handlers.loyalty import LoyaltyRedeemHandler

    # Cliente fica com só 100; o pedido pede débito de 2000 (saldo caiu na corrida).
    acct = LoyaltyService.get_account(CUSTOMER_REF)
    LoyaltyService.redeem_points(CUSTOMER_REF, points=acct.points_balance - 100, description="dreno", reference="dreno")

    order = Order.objects.create(
        ref="ORD-LOYAL-INSUF", channel_ref=channel.ref, total_q=3000,
        data={"customer_ref": CUSTOMER_REF, "loyalty": {"applied_discount_q": 2000}},
    )
    directive = Directive.objects.create(
        topic="loyalty.redeem", payload={"order_ref": order.ref, "points": 2000},
    )

    with _pytest.raises(DirectiveTerminalError):
        LoyaltyRedeemHandler().handle(message=directive, ctx={})

    alert = OperatorAlert.objects.filter(type="loyalty_redeem_uncovered").first()
    assert alert is not None
    assert order.ref in alert.message
