"""Move.kind — typed economic event (make/buy/sell/adjust/transfer/return).

The kind is the queryable category; reason stays the free-text detail. Callers
emit their kind at the entry points; unspecified falls to ADJUST (honest).
"""

from decimal import Decimal

import pytest
from shopman.stockman.models.move import Move
from shopman.stockman.services.movements import StockMovements as stock

pytestmark = pytest.mark.django_db


def test_receive_records_kind(product, vitrine):
    stock.receive(quantity=Decimal("5"), sku=product.sku, position=vitrine, kind=Move.Kind.BUY)
    assert Move.objects.latest("timestamp").kind == Move.Kind.BUY


def test_receive_defaults_to_adjust(product, vitrine):
    stock.receive(quantity=Decimal("3"), sku=product.sku, position=vitrine)
    assert Move.objects.latest("timestamp").kind == Move.Kind.ADJUST


def test_issue_records_kind(product, vitrine):
    quant = stock.receive(quantity=Decimal("5"), sku=product.sku, position=vitrine)
    stock.issue(quantity=Decimal("2"), quant=quant, kind=Move.Kind.SELL)
    assert Move.objects.latest("timestamp").kind == Move.Kind.SELL


def test_adjust_is_always_adjust(product, vitrine):
    quant = stock.receive(quantity=Decimal("5"), sku=product.sku, position=vitrine)
    stock.adjust(quant=quant, new_quantity=Decimal("4"), reason="contagem")
    assert Move.objects.latest("timestamp").kind == Move.Kind.ADJUST


def test_transfer_relocates_between_positions_with_transfer_kind(product, vitrine):
    from shopman.stockman.models import Position, PositionKind, Quant

    src = Position.objects.create(ref="dep-test", name="Depósito", kind=PositionKind.PHYSICAL)
    stock.receive(quantity=Decimal("10"), sku=product.sku, position=src, kind=Move.Kind.BUY)

    stock.transfer(quantity=Decimal("4"), sku=product.sku, from_position=src, to_position=vitrine)

    assert Quant.objects.get(sku=product.sku, position=src, target_date=None, batch="")._quantity == Decimal("6")
    assert Quant.objects.get(sku=product.sku, position=vitrine, target_date=None, batch="")._quantity == Decimal("4")
    # both legs (issue from source + receive into dest) are TRANSFER
    assert Move.objects.filter(kind=Move.Kind.TRANSFER).count() == 2
