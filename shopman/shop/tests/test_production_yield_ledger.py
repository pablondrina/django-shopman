"""Rendimento real ≠ planejado: o ledger tem que contar a verdade.

Regressões do audit pré-go-live:
- rendimento MAIOR (forno rendeu 55 de 50): o realize estourava
  INSUFFICIENT_QUANTITY, era engolido como "non-fatal" e NADA entrava na
  vitrine — com os insumos já consumidos;
- rendimento MENOR (rendeu 45 de 50): o resíduo ficava eterno no batch
  ``started`` como ``in_production`` — prometível para clientes, sem nunca
  materializar. Agora vira WASTE no ledger.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.utils import timezone
from shopman.craftsman.models import Recipe
from shopman.craftsman.service import craft
from shopman.stockman.models import Move, Position, PositionKind, Quant

pytestmark = pytest.mark.django_db

SKU = "PAO-YIELD"


@pytest.fixture
def vitrine(db):
    pos, _ = Position.objects.get_or_create(
        ref="vitrine",
        defaults={"name": "Vitrine", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )
    return pos


@pytest.fixture
def recipe(db, vitrine):
    return Recipe.objects.create(
        ref="rc-yield", name="Pão", output_sku=SKU, batch_size=Decimal("1")
    )


def _vitrine_qty(vitrine) -> Decimal:
    quant = Quant.objects.filter(sku=SKU, position=vitrine, target_date=None).first()
    return quant.quantity if quant else Decimal("0")


def _started_qty(date) -> Decimal:
    quant = Quant.objects.filter(sku=SKU, target_date=date, batch="started").first()
    return quant.quantity if quant else Decimal("0")


def test_over_yield_credits_full_actual(recipe, vitrine):
    today = timezone.localdate()
    wo = craft.plan(recipe, Decimal("50"), date=today)
    craft.start(wo, quantity=Decimal("50"), actor="test")

    craft.finish(wo, finished=Decimal("55"), actor="test")

    assert _vitrine_qty(vitrine) == Decimal("55")
    assert _started_qty(today) == Decimal("0")


def test_under_yield_writes_off_residue_as_waste(recipe, vitrine):
    today = timezone.localdate()
    wo = craft.plan(recipe, Decimal("50"), date=today)
    craft.start(wo, quantity=Decimal("50"), actor="test")

    craft.finish(wo, finished=Decimal("45"), actor="test")

    assert _vitrine_qty(vitrine) == Decimal("45")
    # Os 5 perdidos NÃO ficam prometíveis em "started": viram perda no ledger.
    assert _started_qty(today) == Decimal("0")
    waste = Move.objects.filter(kind="waste", quant__sku=SKU).first()
    assert waste is not None
    assert waste.delta == Decimal("-5")
    assert wo.ref in waste.reason
