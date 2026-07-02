"""``StockHolds.extend`` — redefinir expiração de hold adotado por pedido."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.utils import timezone
from shopman.stockman import HoldStatus, StockHolds, stock
from shopman.stockman.models import Hold, Position, PositionKind, Quant

pytestmark = pytest.mark.django_db

SKU = "EXT-PAO"


@pytest.fixture
def hold_id(db):
    pos, _ = Position.objects.get_or_create(
        ref="ext-vitrine",
        defaults={"name": "Vitrine", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )
    Quant.objects.create(sku=SKU, position=pos, _quantity=Decimal("10"))
    product = SimpleNamespace(sku=SKU, name="Pão", shelf_life_days=None)
    return stock.hold(
        Decimal("2"), product, expires_at=timezone.now() + timedelta(minutes=30)
    )


def test_extend_clears_expiry(hold_id):
    assert StockHolds.extend(hold_id, expires_at=None) is True
    hold = Hold.objects.get(pk=int(hold_id.split(":")[1]))
    assert hold.expires_at is None
    assert Hold.objects.active().filter(pk=hold.pk).exists()


def test_extend_sets_new_deadline(hold_id):
    deadline = timezone.now() + timedelta(hours=4)
    assert StockHolds.extend(hold_id, expires_at=deadline) is True
    hold = Hold.objects.get(pk=int(hold_id.split(":")[1]))
    assert hold.expires_at == deadline


def test_extend_refuses_terminal_hold(hold_id):
    stock.release(hold_id, reason="teste")
    assert StockHolds.extend(hold_id, expires_at=None) is False
    hold = Hold.objects.get(pk=int(hold_id.split(":")[1]))
    assert hold.status == HoldStatus.RELEASED
