"""P0 [CANONIZAR]: encomenda (loja fechada) fecha contra estoque PLANEJADO datado.

Regressão do QA exploratório: à noite/domingo a loja oferecia encomenda para o
próximo dia útil e habilitava o checkout, mas TODO commit com data futura falhava
no gate de estoque — a disponibilidade era calculada com o estoque presente, e o
commit exigia produção futura-datada que o seed não materializava. O fix
(`e6f75769`) foi nos DADOS do seed; o backend (gate de commit/hold + availability
planejada) sempre esteve correto.

Este teste exercita o gate REAL de commit/hold (`CommitService.commit` →
`lifecycle.secure_stock` → `stock.hold(target_date=futuro)`), sem depender do
seed: planta estoque planejado datado direto no ledger e comita contra ele.

Invariante canonizada:
- há Quant planejado para a data alvo → o pedido futuro FECHA (com hold datado);
- não há produção planejada para a data alvo → o gate REPROVA (`insufficient_stock`)
  e nenhum pedido nasce (o caso "segunda sem produção" do relatório).

É a versão determinística (sequencial, SQLite) do gate; irmã de
`test_commit_stock_gate.py`, mas no eixo de DATA (encomenda), não de quantidade.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone


SKU = "PREORDER-MINI-BAGUETE"


def _make_shop_channel_product():
    from shopman.offerman.models import AvailabilityPolicy, Product
    from shopman.shop.models import Channel, Shop
    from shopman.stockman.models import Position, PositionKind

    Shop.objects.get_or_create(name="Test Shop", defaults={"brand_name": "Test"})
    channel = Channel.objects.get_or_create(
        ref="preorder-web", defaults={"name": "web", "is_active": True, "config": {}}
    )[0]
    Product.objects.create(
        sku=SKU,
        name="Mini Baguete",
        base_price_q=1000,
        is_published=True,
        is_sellable=True,
        # planned_ok: disponibilidade GATED por estoque (não demand_ok, que passaria
        # com hold flutuante mesmo sem estoque e mascararia o gate).
        availability_policy=AvailabilityPolicy.PLANNED_OK,
        # 0 = validade no mesmo dia: o físico de HOJE é inválido p/ data futura,
        # então só o planejado datado pode cobrir a encomenda (cenário do P0).
        shelf_life_days=0,
    )
    position = Position.objects.get_or_create(
        ref="preorder-producao",
        defaults={"name": "Produção", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )[0]
    return channel, position


def _plan_dated_stock(position, target_date, qty: int):
    """Materializa um Quant PLANEJADO (datado) — o que a produção futura cria."""
    from shopman.stockman import stock
    from shopman.stockman.models import Move

    stock.receive(
        Decimal(str(qty)),
        SKU,
        position,
        target_date=target_date,
        reason=f"produção planejada {target_date.isoformat()}",
        kind=Move.Kind.MAKE,
    )


def _open_session(channel_ref: str, session_key: str, delivery_date, qty: int):
    from shopman.orderman.models import Session

    return Session.objects.create(
        session_key=session_key,
        channel_ref=channel_ref,
        state="open",
        rev=1,
        items=[
            {
                "line_id": f"L-{session_key}",
                "sku": SKU,
                "name": "Mini Baguete",
                "qty": qty,
                "unit_price_q": 1000,
            }
        ],
        data={"delivery_date": delivery_date.isoformat()},
    )


def _commit(session_key: str, channel_ref: str, idem_key: str):
    from shopman.orderman.services.commit import CommitService

    return CommitService.commit(
        session_key=session_key,
        channel_ref=channel_ref,
        idempotency_key=idem_key,
    )


class PreorderClosedStoreCommitTests(TestCase):
    def setUp(self):
        self.channel, self.position = _make_shop_channel_product()
        today = timezone.localdate()
        # Datas distintas: o dia SEM produção é ANTES do dia COM produção, senão o
        # planejado do dia posterior (target_date <= alvo) cobriria os dois.
        self.day_without_production = today + timedelta(days=1)
        self.day_with_production = today + timedelta(days=2)

    def test_preorder_against_planned_stock_commits(self) -> None:
        """Dia com produção planejada: a encomenda futura fecha com hold datado."""
        from shopman.orderman.models import Order

        _plan_dated_stock(self.position, self.day_with_production, qty=50)
        _open_session(self.channel.ref, "PRE-OK", self.day_with_production, qty=5)

        result = _commit("PRE-OK", self.channel.ref, "PRE-KEY-OK")

        order = Order.objects.get(ref=result.order_ref)
        self.assertEqual(order.data.get("delivery_date"), self.day_with_production.isoformat())
        hold_ids = (order.data or {}).get("hold_ids", [])
        self.assertEqual(len(hold_ids), 1)
        self.assertTrue(hold_ids[0].get("hold_id"))
        self.assertEqual(hold_ids[0].get("sku"), SKU)

    def test_preorder_for_day_without_production_is_rejected(self) -> None:
        """Dia sem produção planejada ("segunda"): o gate reprova, nenhum pedido nasce."""
        from shopman.orderman.exceptions import ValidationError
        from shopman.orderman.models import Order, Session

        # Produção existe só para o dia POSTERIOR — nada para o dia alvo.
        _plan_dated_stock(self.position, self.day_with_production, qty=50)
        _open_session(self.channel.ref, "PRE-REJ", self.day_without_production, qty=5)

        with self.assertRaises(ValidationError) as ctx:
            _commit("PRE-REJ", self.channel.ref, "PRE-KEY-REJ")

        self.assertEqual(ctx.exception.code, "insufficient_stock")
        self.assertEqual(ctx.exception.context.get("sku"), SKU)
        self.assertEqual(Order.objects.filter(channel_ref=self.channel.ref).count(), 0)
        self.assertEqual(Session.objects.get(session_key="PRE-REJ").state, "open")
