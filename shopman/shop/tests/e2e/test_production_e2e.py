"""
WP-PE6 — E2E da cadeia de produção: suggest → plan → mise en place → start →
finish → realize → venda, com DB real e a ponte Craftsman→Stockman viva
(nenhum mock de ORM; o único backend externo é o demand, que é o real —
OrderingDemandBackend sobre pedidos concluídos).

Cenários:
  E2E-P1  cadeia canônica completa com yield parcial (perda vira write-off,
          vitrine recebe o real, low-yield alerta, venda atendida)
  E2E-P2  void de WO com pedido vinculado (unlink + planned quant cancelado)
  E2E-P3  guardrails herdados no nível do orquestrador: adjust abaixo do
          committed de pedidos falha; needs() com ciclo de BOM não trava
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe, RecipeItem, WorkOrder
from shopman.orderman.models import Directive, Order, OrderItem
from shopman.stockman import Position, stock

from shopman.backstage.models import OperatorAlert
from shopman.backstage.projections.production import build_production_mise_en_place
from shopman.shop.directives import PRODUCTION_LATE_CHECK
from shopman.shop.services.production import set_planned_quantity, suggest_for

pytestmark = pytest.mark.django_db


@pytest.fixture
def producao(db):
    """Posição de produção (default do plan; não vendável)."""
    from shopman.stockman.models import PositionKind

    return Position.objects.create(
        ref="producao", name="Produção", kind=PositionKind.PHYSICAL,
        is_saleable=False, is_default=True,
    )


@pytest.fixture
def vitrine(db, producao):
    """Primeira posição vendável — destino do realize."""
    return Position.objects.create(ref="vitrine", name="Vitrine", is_saleable=True)


@pytest.fixture
def pao_product(db):
    """Produto vendável — a decisão de disponibilidade lê a policy dele."""
    from shopman.offerman.models import Product

    return Product.objects.create(
        sku="PAO", name="Pão", unit="un", base_price_q=100,
        availability_policy="planned_ok", is_sellable=True,
    )


@pytest.fixture
def recipe(db, pao_product):
    pao = Recipe.objects.create(ref="pao", name="Pão", output_sku="PAO", batch_size=Decimal("10"))
    RecipeItem.objects.create(recipe=pao, input_sku="FARINHA", quantity="5", unit="kg")
    return pao


def _completed_order(ref: str, *, days_ago: int, sku: str = "PAO", qty: int) -> Order:
    order = Order.objects.create(
        ref=ref, channel_ref="web", status="completed", total_q=qty * 100
    )
    OrderItem.objects.create(
        order=order, line_id=f"{ref}-1", sku=sku, name=sku, qty=qty,
        unit_price_q=100, line_total_q=qty * 100,
    )
    # created_at é auto_now_add — retrodata para virar histórico de demanda.
    Order.objects.filter(pk=order.pk).update(
        created_at=timezone.now() - timedelta(days=days_ago)
    )
    return order


class TestProductionChainE2E:
    def test_full_chain_suggest_to_sale(self, recipe, vitrine, producao):
        today = date.today()
        # Histórico de demanda no MESMO dia da semana (backend real filtra).
        _completed_order("HIST-1", days_ago=7, qty=8)
        _completed_order("HIST-2", days_ago=14, qty=12)
        # Insumo em estoque para o consumo do finish.
        stock.receive(quantity=Decimal("20"), sku="FARINHA", position=producao, reason="e2e")

        # 1. SUGGEST — o backend real lê os pedidos concluídos.
        suggestions = suggest_for(today)
        line = next(s for s in suggestions if s.recipe.pk == recipe.pk)
        # avg (8+12)/2 = 10, committed 0, margem 20% → 12
        assert line.quantity == Decimal("12")
        assert line.basis["sample_size"] == 2

        # 2. PLAN — caminho da matriz; arma o heartbeat e cria o quant planejado.
        _, wo_ref, planned_qty, result = set_planned_quantity(
            recipe_id=recipe.pk,
            quantity=line.quantity,
            target_date_value=today.isoformat(),
            actor="e2e",
        )
        assert result == "created"
        assert planned_qty == Decimal("12")
        assert Directive.objects.filter(
            topic=PRODUCTION_LATE_CHECK, status__in=("queued", "running")
        ).exists()
        assert stock.available("PAO", target_date=today) == Decimal("12")

        # 3. MISE EN PLACE — a lista do dia escala o insumo pelo coeficiente.
        mise = build_production_mise_en_place(selected_date=today)
        farinha = next(line for line in mise.lines if line.sku == "FARINHA")
        assert farinha.quantity_display == "6 kg"  # 12/10 × 5kg

        # 4. START
        wo = WorkOrder.objects.get(ref=wo_ref)
        craft.start(wo, quantity=Decimal("12"), actor="e2e")

        # 5. FINISH parcial — 9 de 12 (yield 75% < 80%).
        craft.finish(order=wo, finished=Decimal("9"), actor="e2e")
        wo.refresh_from_db()
        assert wo.status == WorkOrder.Status.FINISHED

        # Vitrine recebeu o REAL (não o planejado)…
        assert stock.available("PAO", position=vitrine) == Decimal("9")
        # …e o shortfall virou write-off: nada de estoque-fantasma prometível
        # no lote started (regressão do bug de get_quant por coordenada).
        from shopman.stockman.models import Quant

        started_residual = Quant.objects.filter(sku="PAO", batch="started").first()
        assert started_residual is None or started_residual._quantity == Decimal("0")
        assert stock.available("PAO") == Decimal("9")
        # Insumo consumido do ledger.
        assert stock.available("FARINHA") < Decimal("20")
        # Alerta de yield baixo nasceu do próprio signal.
        assert OperatorAlert.objects.filter(
            type="production_low_yield", message__contains=wo.ref
        ).exists()

        # 6. VENDA — o lote realizado atende um hold de cliente.
        hold = stock.hold(Decimal("2"), "PAO")
        assert hold is not None
        assert stock.available("PAO") == Decimal("7")

    def test_void_with_linked_order_unlinks_and_releases_plan(self, recipe, vitrine, producao):
        today = date.today()
        order = Order.objects.create(
            ref="E2E-ORD-1", channel_ref="web", status="confirmed", total_q=400,
            data={"target_date": today.isoformat()},
        )
        OrderItem.objects.create(
            order=order, line_id="E2E-ORD-1-1", sku="PAO", name="Pão", qty=4,
            unit_price_q=100, line_total_q=400,
        )

        # PLAN dispara o signal; o sync vincula o pedido ativo ao lote.
        _, wo_ref, _, _ = set_planned_quantity(
            recipe_id=recipe.pk, quantity=Decimal("10"),
            target_date_value=today.isoformat(), actor="e2e",
        )
        order.refresh_from_db()
        assert order.data.get("awaiting_wo_refs") == [wo_ref]
        assert stock.available("PAO", target_date=today) == Decimal("10")

        # VOID desfaz o vínculo e cancela o planejado no estoque.
        wo = WorkOrder.objects.get(ref=wo_ref)
        craft.void(order=wo, reason="e2e", actor="e2e")

        order.refresh_from_db()
        assert "awaiting_wo_refs" not in (order.data or {})
        assert stock.available("PAO", target_date=today) == Decimal("0")

    def test_adjust_updates_planned_quant_without_duplicating(self, recipe, vitrine, producao):
        """Regressão: ajuste de WO posicionada atualizava um quant NULL-position
        duplicado (get_quant por coordenada) — o planejado da data inflava."""
        today = date.today()
        stock.receive(quantity=Decimal("20"), sku="FARINHA", position=producao, reason="e2e")
        _, wo_ref, _, _ = set_planned_quantity(
            recipe_id=recipe.pk, quantity=Decimal("10"),
            target_date_value=today.isoformat(), actor="e2e",
        )
        wo = WorkOrder.objects.get(ref=wo_ref)
        craft.adjust(wo, quantity=Decimal("6"), reason="e2e", actor="e2e")

        from shopman.stockman.models import Quant

        assert stock.available("PAO", target_date=today) == Decimal("6")
        assert Quant.objects.filter(sku="PAO", target_date=today, batch="").count() == 1

    def test_adjust_below_order_commitment_is_blocked(self, recipe, vitrine, producao):
        """Guardrail V1 do Core, vivo na config real do orquestrador (DEMAND_BACKEND)."""
        today = date.today()
        order = Order.objects.create(
            ref="E2E-ORD-2", channel_ref="web", status="confirmed", total_q=600,
            data={"target_date": today.isoformat()},
        )
        OrderItem.objects.create(
            order=order, line_id="E2E-ORD-2-1", sku="PAO", name="Pão", qty=6,
            unit_price_q=100, line_total_q=600,
        )
        # Committed via hold ativo (o backend soma Holds do Stockman).
        _, wo_ref, _, _ = set_planned_quantity(
            recipe_id=recipe.pk, quantity=Decimal("10"),
            target_date_value=today.isoformat(), actor="e2e",
        )
        stock.hold(Decimal("6"), "PAO", target_date=today)

        wo = WorkOrder.objects.get(ref=wo_ref)
        with pytest.raises(Exception, match="(?i)commit|hold|insuf"):
            craft.adjust(wo, quantity=Decimal("2"), reason="e2e", actor="e2e")

    def test_needs_with_bom_cycle_raises_explicit_error(self, vitrine):
        """Ciclo A→B→A na BOM: needs(expand=True) corta no depth com erro explícito."""
        from shopman.craftsman.exceptions import CraftError

        a = Recipe.objects.create(ref="massa-a", name="A", output_sku="MASSA-A", batch_size=1)
        b = Recipe.objects.create(ref="massa-b", name="B", output_sku="MASSA-B", batch_size=1)
        RecipeItem.objects.create(recipe=a, input_sku="MASSA-B", quantity="1", unit="kg")
        RecipeItem.objects.create(recipe=b, input_sku="MASSA-A", quantity="1", unit="kg")
        craft.plan(a, Decimal("2"), date=date.today())

        with pytest.raises(CraftError, match="BOM_CYCLE"):
            craft.needs(date.today(), expand=True)
