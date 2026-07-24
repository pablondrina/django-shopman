"""Gates de política de canal no commit — SKU fora do catálogo e lead time.

Work packages aprovados pelo dono (Pablo, 2026-07-24) — política de negócio da
padaria (fermentação natural; encomenda é contrato com o cliente):

- ``stock.allow_untracked=False``: canal de CLIENTE recusa SKU fora do
  CATÁLOGO com falha limpa (``ValidationError(unknown_sku)``, sem Order, sem
  hold). Canal permissivo (default) preserva o seam de integração/smoke —
  commita como untracked. Produto que EXISTE no catálogo mas não é rastreado
  pelo Stockman segue passando mesmo no canal gated.

- Lead time: registro de DEMANDA (encomenda para data sem fornada planejada)
  só dentro da antecedência de ``Product.metadata["lead_time_hours"]`` (ou
  ``stock.default_lead_time_hours`` do canal). Cedo demais →
  ``ValidationError(lead_time)`` com a primeira data possível, sem
  Order/hold. Encomenda com Quant planejado da data segue valendo, e venda
  imediata do estoque físico de hoje nunca é bloqueada.

Mesmos moldes (services reais, sem mock de estoque) do módulo vizinho
``test_storefront_backstage_stress.py``.
"""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

# ── Helpers (estilo do vizinho test_storefront_backstage_stress) ──


def _make_shop():
    from shopman.shop.models import Shop

    return Shop.objects.get_or_create(name="Test Shop", defaults={"brand_name": "Test"})[0]


def _make_channel(ref: str, config: dict | None = None):
    from shopman.shop.models import Channel

    return Channel.objects.get_or_create(
        ref=ref,
        defaults={"name": ref, "is_active": True, "config": config or {}},
    )[0]


def _make_product(
    sku: str,
    *,
    price_q: int = 1000,
    shelf_life_days: int | None = None,
    lead_time_hours: int | None = None,
):
    from shopman.offerman.models import Product

    product = Product.objects.create(
        sku=sku,
        name=f"Produto {sku}",
        base_price_q=price_q,
        shelf_life_days=shelf_life_days,
        is_published=True,
        is_sellable=True,
    )
    if lead_time_hours is not None:
        product.metadata = {**(product.metadata or {}), "lead_time_hours": lead_time_hours}
        product.save(update_fields=["metadata"])
    return product


def _make_position(ref: str):
    from shopman.stockman.models import Position, PositionKind

    return Position.objects.get_or_create(
        ref=ref,
        defaults={"name": ref, "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )[0]


def _receive(qty: int, sku: str, position):
    from shopman.stockman import stock

    stock.receive(Decimal(str(qty)), sku, position, reason="gate setup")


def _open_session(channel_ref: str, session_key: str, sku: str, qty: int, *, data=None):
    from shopman.orderman.models import Session

    return Session.objects.create(
        session_key=session_key,
        channel_ref=channel_ref,
        state="open",
        rev=1,
        items=[
            {
                "line_id": f"L-{session_key}",
                "sku": sku,
                "name": f"Produto {sku}",
                "qty": qty,
                "unit_price_q": 1000,
            }
        ],
        data=data or {},
    )


def _commit(session_key: str, channel_ref: str, idem_key: str):
    from shopman.orderman.services.commit import CommitService

    return CommitService.commit(
        session_key=session_key,
        channel_ref=channel_ref,
        idempotency_key=idem_key,
    )


def _active_holds(sku: str | None = None):
    from shopman.stockman import Hold, HoldStatus

    qs = Hold.objects.filter(status__in=[HoldStatus.PENDING, HoldStatus.CONFIRMED])
    if sku:
        qs = qs.filter(sku=sku)
    return qs


# ═════════════════════════════════════════════════════════════════════════════
# 1. Gate de SKU fora do catálogo (stock.allow_untracked)
# ═════════════════════════════════════════════════════════════════════════════


class UnknownSkuGateTests(TestCase):
    """Canal gated recusa SKU fora do catálogo limpo; permissivo mantém o seam."""

    SKU = "GATE-KNOWN-SKU"

    def setUp(self):
        _make_shop()
        self.gated = _make_channel(
            "gate-web", config={"stock": {"allow_untracked": False}}
        )
        self.permissive = _make_channel("gate-open")  # default: allow_untracked=True
        _make_product(self.SKU)
        _receive(5, self.SKU, _make_position("gate-vitrine"))

    def test_unknown_sku_refused_clean_on_gated_channel(self) -> None:
        from shopman.orderman.exceptions import ValidationError
        from shopman.orderman.models import IdempotencyKey, Order, Session

        _open_session(self.gated.ref, "GATE-SS-001", "GATE-GHOST-SKU", qty=1)
        with self.assertRaises(ValidationError) as ctx:
            _commit("GATE-SS-001", self.gated.ref, "GATE-KEY-001")

        self.assertEqual(ctx.exception.code, "unknown_sku")
        # Falha limpa: sem order fantasma, sem hold, sessão continua aberta.
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(_active_holds().count(), 0)
        self.assertEqual(Session.objects.get(session_key="GATE-SS-001").state, "open")
        idem = IdempotencyKey.objects.get(
            scope=f"commit:{self.gated.ref}:GATE-SS-001", key="GATE-KEY-001"
        )
        self.assertEqual(idem.status, "failed")

    def test_unknown_sku_still_commits_untracked_on_permissive_channel(self) -> None:
        from shopman.orderman.models import Order

        _open_session(self.permissive.ref, "GATE-SS-002", "GATE-GHOST-SKU", qty=1)
        with self.captureOnCommitCallbacks(execute=True):
            result = _commit("GATE-SS-002", self.permissive.ref, "GATE-KEY-002")

        order = Order.objects.get(ref=result.order_ref)
        entries = order.data.get("hold_ids", [])
        self.assertEqual(len(entries), 1)
        self.assertTrue(entries[0].get("untracked"))
        self.assertIsNone(entries[0].get("hold_id"))
        self.assertEqual(_active_holds().count(), 0)

    def test_catalog_product_untracked_by_stockman_passes_gated_channel(self) -> None:
        """O gate mira SKU FORA DO CATÁLOGO. Produto real sem rastreio de
        estoque (nenhum Quant — ex.: serviço/preparado na hora) segue vendável
        no canal gated, como untracked."""
        from shopman.orderman.models import Order

        _make_product("GATE-NO-STOCK-SKU")  # existe no catálogo, sem quants
        _open_session(self.gated.ref, "GATE-SS-003", "GATE-NO-STOCK-SKU", qty=1)
        with self.captureOnCommitCallbacks(execute=True):
            result = _commit("GATE-SS-003", self.gated.ref, "GATE-KEY-003")

        order = Order.objects.get(ref=result.order_ref)
        entries = order.data.get("hold_ids", [])
        self.assertEqual(len(entries), 1)
        self.assertTrue(entries[0].get("untracked"))

    def test_known_sku_with_stock_sells_normally_on_gated_channel(self) -> None:
        from shopman.orderman.models import Order

        _open_session(self.gated.ref, "GATE-SS-004", self.SKU, qty=2)
        with self.captureOnCommitCallbacks(execute=True):
            result = _commit("GATE-SS-004", self.gated.ref, "GATE-KEY-004")

        order = Order.objects.get(ref=result.order_ref)
        entries = [h for h in order.data.get("hold_ids", []) if h.get("hold_id")]
        self.assertEqual(len(entries), 1)


# ═════════════════════════════════════════════════════════════════════════════
# 2. Lead time no registro de DEMANDA (hold quant=None)
# ═════════════════════════════════════════════════════════════════════════════


class LeadTimeDemandGateTests(TestCase):
    """Demanda só dentro do lead time; plano da data e venda de hoje passam."""

    SKU = "LEAD-CAMPAGNE-SKU"
    LEAD_HOURS = 48

    def setUp(self):
        from datetime import timedelta

        _make_shop()
        # defaults: preorder=True → sem plano, encomenda vira registro de demanda.
        self.web = _make_channel("lead-web")
        self.product = _make_product(
            self.SKU, shelf_life_days=0, lead_time_hours=self.LEAD_HOURS
        )
        self.vitrine = _make_position("lead-vitrine")
        _receive(5, self.SKU, self.vitrine)  # fornada de HOJE (perecível D+0)
        self.tomorrow = timezone.localdate() + timedelta(days=1)

        from shopman.shop.services import lead_time

        # Com lead de 48h, earliest é sempre > amanhã (>= D+2).
        self.earliest = lead_time.earliest_allowed_date(self.SKU, self.web.ref)
        self.assertGreater(self.earliest, self.tomorrow)

    def _plan(self, qty: int, target_date):
        from shopman.stockman.service import Stock

        Stock.plan(Decimal(str(qty)), self.product, target_date)

    def test_demand_before_lead_time_refused_clean(self) -> None:
        from shopman.orderman.exceptions import ValidationError
        from shopman.orderman.models import Order

        _open_session(
            self.web.ref, "LEAD-SS-001", self.SKU, qty=2,
            data={"delivery_date": self.tomorrow.isoformat()},
        )
        with self.assertRaises(ValidationError) as ctx:
            _commit("LEAD-SS-001", self.web.ref, "LEAD-KEY-001")

        self.assertEqual(ctx.exception.code, "lead_time")
        self.assertIn(f"{self.LEAD_HOURS}h de antecedência", ctx.exception.message)
        self.assertIn(self.earliest.strftime("%d/%m"), ctx.exception.message)
        # Usa o NOME do produto, não o SKU cru sozinho.
        self.assertIn(f"Produto {self.SKU}", ctx.exception.message)
        self.assertEqual(
            ctx.exception.context.get("earliest_allowed_date"),
            self.earliest.isoformat(),
        )
        # Falha limpa: sem order, sem hold (nem de demanda).
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(_active_holds(self.SKU).count(), 0)

    def test_demand_on_earliest_allowed_date_registers(self) -> None:
        from shopman.orderman.models import Order
        from shopman.stockman import Hold

        _open_session(
            self.web.ref, "LEAD-SS-002", self.SKU, qty=2,
            data={"delivery_date": self.earliest.isoformat()},
        )
        with self.captureOnCommitCallbacks(execute=True):
            result = _commit("LEAD-SS-002", self.web.ref, "LEAD-KEY-002")

        order = Order.objects.get(ref=result.order_ref)
        entries = [h for h in order.data.get("hold_ids", []) if h.get("hold_id")]
        self.assertEqual(len(entries), 1)
        hold = Hold.objects.get(pk=int(entries[0]["hold_id"].split(":")[1]))
        self.assertIsNone(hold.quant)  # demanda registrada
        self.assertEqual(hold.target_date, self.earliest)

    def test_preorder_with_planned_quant_passes_despite_lead_time(self) -> None:
        """A fornada de amanhã JÁ está planejada — o compromisso existe; o gate
        de lead time não morde encomenda ancorada em Quant planejado."""
        from shopman.orderman.models import Order
        from shopman.stockman import Hold

        self._plan(3, self.tomorrow)
        _open_session(
            self.web.ref, "LEAD-SS-003", self.SKU, qty=2,
            data={"delivery_date": self.tomorrow.isoformat()},
        )
        with self.captureOnCommitCallbacks(execute=True):
            result = _commit("LEAD-SS-003", self.web.ref, "LEAD-KEY-003")

        order = Order.objects.get(ref=result.order_ref)
        entries = [h for h in order.data.get("hold_ids", []) if h.get("hold_id")]
        self.assertEqual(len(entries), 1)
        hold = Hold.objects.get(pk=int(entries[0]["hold_id"].split(":")[1]))
        self.assertIsNotNone(hold.quant)
        self.assertEqual(hold.quant.target_date, self.tomorrow)

    def test_immediate_sale_of_todays_stock_never_blocked(self) -> None:
        """PDV/venda imediata: estoque físico de hoje sai normalmente — lead
        time vale só para data futura/encomenda."""
        from shopman.orderman.models import Order
        from shopman.stockman import Hold

        _open_session(self.web.ref, "LEAD-SS-004", self.SKU, qty=2)
        with self.captureOnCommitCallbacks(execute=True):
            result = _commit("LEAD-SS-004", self.web.ref, "LEAD-KEY-004")

        order = Order.objects.get(ref=result.order_ref)
        entries = [h for h in order.data.get("hold_ids", []) if h.get("hold_id")]
        self.assertEqual(len(entries), 1)
        hold = Hold.objects.get(pk=int(entries[0]["hold_id"].split(":")[1]))
        self.assertIsNotNone(hold.quant)  # reserva no físico de hoje

    def test_channel_default_lead_time_applies_when_product_has_none(self) -> None:
        """Produto sem metadata herda ``stock.default_lead_time_hours`` do canal."""
        from shopman.orderman.exceptions import ValidationError
        from shopman.orderman.models import Order

        channel = _make_channel(
            "lead-default", config={"stock": {"default_lead_time_hours": 48}}
        )
        sku = "LEAD-PLAIN-SKU"
        _make_product(sku, shelf_life_days=0)
        _receive(5, sku, self.vitrine)

        _open_session(
            channel.ref, "LEAD-SS-005", sku, qty=1,
            data={"delivery_date": self.tomorrow.isoformat()},
        )
        with self.assertRaises(ValidationError) as ctx:
            _commit("LEAD-SS-005", channel.ref, "LEAD-KEY-005")
        self.assertEqual(ctx.exception.code, "lead_time")
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(_active_holds(sku).count(), 0)
