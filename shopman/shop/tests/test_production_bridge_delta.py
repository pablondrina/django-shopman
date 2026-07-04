"""Ponte craftsman→stockman aplica DELTA por WO, não SET absoluto.

Regressão P1: o Quant planejado é COMPARTILHADO por todas as WOs do mesmo
(sku, data, posição) — receive() faz get_or_create. Voidar/ajustar uma WO
setava o Quant compartilhado para a quantidade absoluta daquela WO, zerando ou
clobberando a contribuição das outras. Cenário real: a consolidação da matriz
de produção voidava WOs duplicadas → zerava o supply planejado inteiro com uma
WO ativa.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.utils import timezone
from shopman.craftsman.models import Recipe
from shopman.craftsman.service import craft
from shopman.stockman.models import Quant

pytestmark = pytest.mark.django_db

SKU = "PAO-DELTA"


@pytest.fixture
def recipe(db):
    return Recipe.objects.create(
        ref="rc-delta", name="Pão", output_sku=SKU, batch_size=Decimal("1")
    )


def _planned_qty(date) -> Decimal:
    """Soma o supply planejado (batch vazio) do sku/data, em qualquer posição."""
    total = Decimal("0")
    for q in Quant.objects.filter(sku=SKU, target_date=date, batch=""):
        total += q.quantity
    return total


def test_void_uma_wo_preserva_a_outra(recipe):
    today = timezone.localdate()
    wo_a = craft.plan(recipe, Decimal("10"), date=today)
    craft.plan(recipe, Decimal("10"), date=today)  # WO-B coexiste
    assert _planned_qty(today) == Decimal("20")

    craft.void(wo_a, reason="consolidação")

    # Antes do fix: zerava o Quant compartilhado (0). Agora subtrai só a
    # contribuição de A (−10) → sobra a supply de B.
    assert _planned_qty(today) == Decimal("10")


def test_adjust_uma_wo_aplica_delta(recipe):
    today = timezone.localdate()
    wo_a = craft.plan(recipe, Decimal("10"), date=today)
    craft.plan(recipe, Decimal("10"), date=today)  # WO-B coexiste
    assert _planned_qty(today) == Decimal("20")

    craft.adjust(wo_a, Decimal("15"), actor="test")  # delta +5

    # Antes: setava o compartilhado para 15 (clobber de B). Agora: 20 + 5 = 25.
    assert _planned_qty(today) == Decimal("25")


def test_adjust_para_baixo_aplica_delta_negativo(recipe):
    today = timezone.localdate()
    wo_a = craft.plan(recipe, Decimal("10"), date=today)
    craft.plan(recipe, Decimal("10"), date=today)
    assert _planned_qty(today) == Decimal("20")

    craft.adjust(wo_a, Decimal("4"), actor="test")  # delta -6

    assert _planned_qty(today) == Decimal("14")
