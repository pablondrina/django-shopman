"""Demanda autorizada pelo canal (``allow_demand``) e materialização com prioridade.

Encomenda para data sem plano: o caller (canal de venda que aceita encomenda)
autoriza o fallback de demanda mesmo quando a política do produto não é
``demand_ok``. Na materialização, o pool inclui os holds flutuantes de demanda
da data e ordena por ``metadata.priority`` (pedido enviado antes de sacola),
FIFO dentro da mesma classe.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from shopman.stockman.exceptions import StockError
from shopman.stockman.models import Position, PositionKind
from shopman.stockman.models.enums import HoldStatus
from shopman.stockman.models.hold import Hold
from shopman.stockman.services.holds import StockHolds
from shopman.stockman.services.movements import StockMovements
from shopman.stockman.services.planning import StockPlanning


@pytest.fixture
def producao(db):
    return Position.objects.create(ref="producao", name="Produção", kind=PositionKind.PHYSICAL, is_saleable=False)


@pytest.fixture
def vitrine(db):
    return Position.objects.create(ref="vitrine", name="Vitrine", kind=PositionKind.PHYSICAL, is_saleable=True)


@pytest.fixture
def tomorrow():
    return date.today() + timedelta(days=1)


def _get_hold(hold_id: str) -> Hold:
    return Hold.objects.get(pk=int(hold_id.split(":")[1]))


@pytest.mark.django_db
class TestAllowDemand:
    def test_without_allow_demand_no_plan_refuses(self, product, tomorrow):
        with pytest.raises(StockError) as exc:
            StockHolds.hold(Decimal("2"), product, tomorrow)
        assert exc.value.code == "INSUFFICIENT_AVAILABLE"

    def test_allow_demand_registers_floating_demand_hold(self, product, tomorrow):
        hold_id = StockHolds.hold(
            Decimal("2"), product, tomorrow,
            allow_demand=True,
            reference="order:WEB-001",
            priority=0,
        )
        hold = _get_hold(hold_id)
        assert hold.is_demand, "sem plano, a encomenda vira demanda registrada"
        assert hold.target_date == tomorrow
        assert hold.status == HoldStatus.PENDING
        assert hold.metadata["priority"] == 0

    def test_allow_demand_beyond_plan_capacity_registers_demand(
        self, product, producao, tomorrow
    ):
        StockMovements.receive(
            quantity=Decimal("1"), sku=product.sku, position=producao,
            target_date=tomorrow, reason="fornada curta",
        )
        hold_id = StockHolds.hold(Decimal("5"), product, tomorrow, allow_demand=True)
        assert _get_hold(hold_id).is_demand, "demanda além do plano não é recusa"


@pytest.mark.django_db
class TestRealizePriority:
    def test_realize_adopts_floating_demand_and_prioritizes_orders(
        self, product, producao, vitrine, tomorrow
    ):
        # Sacola reserva primeiro (FIFO jogaria a favor dela)…
        StockMovements.receive(
            quantity=Decimal("2"), sku=product.sku, position=producao,
            target_date=tomorrow, reason="fornada planejada",
        )
        cart_hold = _get_hold(
            StockHolds.hold(
                Decimal("2"), product, tomorrow,
                expires_at=None, reference="SESS-CART",
            )
        )
        # …e a encomenda ENVIADA chega depois, como demanda além do plano.
        order_hold = _get_hold(
            StockHolds.hold(
                Decimal("2"), product, tomorrow,
                allow_demand=True, reference="order:WEB-042", priority=0,
            )
        )
        assert order_hold.is_demand
        assert order_hold.created_at > cart_hold.created_at

        # Fornada rende só 2: o pedido enviado materializa primeiro.
        StockPlanning.realize(product, tomorrow, Decimal("2"), vitrine, from_position=producao)

        order_hold.refresh_from_db()
        cart_hold.refresh_from_db()
        assert order_hold.quant is not None and order_hold.quant.target_date is None, (
            "pedido enviado tem prioridade na materialização"
        )
        assert order_hold.expires_at is not None, "materializou → TTL começa a contar"
        assert cart_hold.quant is None or cart_hold.quant.target_date is not None, (
            "a sacola espera a próxima fornada quando o plano é curto"
        )
