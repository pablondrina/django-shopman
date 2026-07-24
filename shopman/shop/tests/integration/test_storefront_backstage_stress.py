"""Stress de integração storefront ↔ backstage — pedido "liso, sem falhas, sem brechas".

Exercita o contrato completo entre a superfície do cliente (sacola/checkout →
``CommitService``) e a operação (lifecycle → holds/fulfill/release do Stockman),
sempre pelos services reais — nada de mock de estoque:

- Caminho feliz completo: reserva de sacola → commit → confirmação → cancelamento
  com devolução de estoque (canal web e canal balcão com baixa no ato).
- Estoque insuficiente no commit: falha limpa, sem Order fantasma, sem hold
  vazado, com retry pós-reposição na MESMA idempotency key.
- Corrida de oversell (PostgreSQL + threads): nunca vende acima do físico e os
  perdedores não deixam reserva presa.
- Escopo de posição D-1: canal remoto com ``stock.excluded_positions=["ontem"]``
  não enxerga nem reserva o saldo da posição "ontem"; canal balcão (sem
  exclusão) enxerga tudo.
- Encomenda/estoque planejado: data futura só com Quant ``target_date``
  correspondente; sem plano, canal com ``stock.preorder=False`` recusa limpo e
  canal com preorder registra DEMANDA (hold ``quant=None``) — seam documentado.
- Double-submit com a mesma idempotency key sob corrida: um pedido só.
- Cancelamento idempotente: cancelar 2x nunca devolve estoque em dobro.
- Sessão malformada: qty<=0 é barrado pelo constraint do Core na ESCRITA da
  sessão; sessão vazia falha com ``CommitError(empty_session)``; SKU fora do
  catálogo commita como untracked (seam deliberado — ver ``stock._sku_known_
  to_catalog``).
- Contrato Session→Order: ``_do_commit`` copia apenas as chaves da lista
  explícita (``order_notes`` etc.); preço do carrinho é selado no commit
  (repricing é aviso de storefront, não recálculo); cupom conta uso no commit
  e devolve no cancel.

Os testes de corrida exigem PostgreSQL (locking de linha real) — mesmos moldes
de ``shopman/storefront/tests/test_concurrent_checkout.py``.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta
from decimal import Decimal

import pytest
from django.conf import settings
from django.test import TestCase, TransactionTestCase

requires_postgres = pytest.mark.skipif(
    "sqlite" in settings.DATABASES["default"]["ENGINE"],
    reason="Requires PostgreSQL for real concurrency testing",
)


# ── Helpers (estilo dos vizinhos: test_concurrent_checkout / test_commit_stock_gate) ──


def _make_shop():
    from shopman.shop.models import Shop

    return Shop.objects.get_or_create(name="Test Shop", defaults={"brand_name": "Test"})[0]


def _make_channel(ref: str, config: dict | None = None):
    from shopman.shop.models import Channel

    return Channel.objects.get_or_create(
        ref=ref,
        defaults={"name": ref, "is_active": True, "config": config or {}},
    )[0]


def _make_product(sku: str, *, price_q: int = 1000, shelf_life_days: int | None = None):
    from shopman.offerman.models import Product

    return Product.objects.create(
        sku=sku,
        name=f"Produto {sku}",
        base_price_q=price_q,
        shelf_life_days=shelf_life_days,
        is_published=True,
        is_sellable=True,
    )


def _make_position(ref: str, *, saleable: bool = True):
    from shopman.stockman.models import Position, PositionKind

    return Position.objects.get_or_create(
        ref=ref,
        defaults={"name": ref, "kind": PositionKind.PHYSICAL, "is_saleable": saleable},
    )[0]


def _receive(qty: int, sku: str, position, *, target_date=None):
    from shopman.stockman import stock

    stock.receive(
        Decimal(str(qty)), sku, position,
        target_date=target_date, reason="stress setup",
    )


def _open_session(
    channel_ref: str,
    session_key: str,
    sku: str,
    qty: int,
    *,
    price_q: int = 1000,
    data: dict | None = None,
    items: list[dict] | None = None,
):
    from shopman.orderman.models import Session

    if items is None:
        items = [
            {
                "line_id": f"L-{session_key}",
                "sku": sku,
                "name": f"Produto {sku}",
                "qty": qty,
                "unit_price_q": price_q,
            }
        ]
    return Session.objects.create(
        session_key=session_key,
        channel_ref=channel_ref,
        state="open",
        rev=1,
        items=items,
        data=data or {},
    )


def _commit(session_key: str, channel_ref: str, idem_key: str):
    from shopman.orderman.services.commit import CommitService

    return CommitService.commit(
        session_key=session_key,
        channel_ref=channel_ref,
        idempotency_key=idem_key,
    )


def _available(sku: str) -> Decimal:
    """Disponível AGORA (físico válido − holds ativos), todas as posições."""
    from shopman.stockman.service import Stock

    return Stock.available(sku)


def _active_holds(sku: str | None = None):
    from shopman.stockman import Hold, HoldStatus

    qs = Hold.objects.filter(status__in=[HoldStatus.PENDING, HoldStatus.CONFIRMED])
    if sku:
        qs = qs.filter(sku=sku)
    return qs


# ═════════════════════════════════════════════════════════════════════════════
# 1. Caminho feliz completo
# ═════════════════════════════════════════════════════════════════════════════


class HappyPathWebLifecycleTests(TestCase):
    """Sacola web → commit → confirmado → cancelado, com o MESMO hold da sacola."""

    SKU = "STRESS-WEB-SKU"

    def setUp(self):
        _make_shop()
        self.channel = _make_channel("stress-web")
        _make_product(self.SKU)
        self.position = _make_position("stress-vitrine")
        _receive(5, self.SKU, self.position)

    def test_full_cycle_reserve_commit_confirm_cancel(self) -> None:
        from shopman.orderman.models import Order, Session
        from shopman.stockman import Hold, HoldStatus

        from shopman.shop.services import availability, cancellation

        # Sacola: reserva de 2 unidades atrelada à sessão.
        reserved = availability.reserve(
            self.SKU, Decimal("2"),
            session_key="STRESS-WEB-SS-001",
            channel_ref=self.channel.ref,
        )
        self.assertTrue(reserved["ok"])
        cart_hold_id = reserved["hold_id"]
        self.assertEqual(_available(self.SKU), Decimal("3"))

        _open_session(self.channel.ref, "STRESS-WEB-SS-001", self.SKU, qty=2)

        with self.captureOnCommitCallbacks(execute=True):
            result = _commit("STRESS-WEB-SS-001", self.channel.ref, "STRESS-WEB-KEY-001")

        order = Order.objects.get(ref=result.order_ref)
        self.assertEqual(result.total_q, 2000)

        # Confirmação otimista (mode=immediate nos defaults) já rodou.
        self.assertEqual(order.status, Order.Status.CONFIRMED)

        # O hold da sacola foi ADOTADO (mesmo id), não duplicado.
        hold_entries = (order.data or {}).get("hold_ids", [])
        self.assertEqual([h["hold_id"] for h in hold_entries], [cart_hold_id])
        hold = Hold.objects.get(pk=int(cart_hold_id.split(":")[1]))
        self.assertEqual(hold.metadata.get("reference"), f"order:{order.ref}")
        self.assertIn(hold.status, (HoldStatus.PENDING, HoldStatus.CONFIRMED))
        # Backstop longo (não infinito): reserva não morre com o TTL da sacola.
        self.assertIsNotNone(hold.expires_at)

        # Reserva segue descontando a disponibilidade; físico intacto.
        self.assertEqual(_available(self.SKU), Decimal("3"))
        session = Session.objects.get(session_key="STRESS-WEB-SS-001")
        self.assertEqual(session.state, "committed")

        # Cancelamento pós-confirmação devolve a reserva.
        with self.captureOnCommitCallbacks(execute=True):
            cancelled = cancellation.cancel(order, "customer_requested", actor="customer")
        self.assertTrue(cancelled)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)
        hold.refresh_from_db()
        self.assertEqual(hold.status, HoldStatus.RELEASED)
        self.assertEqual(_available(self.SKU), Decimal("5"))


class HappyPathBalcaoFulfillTests(TestCase):
    """Balcão (payment external): baixa no ato; cancel tardio devolve ao ledger."""

    SKU = "STRESS-PDV-SKU"

    def setUp(self):
        _make_shop()
        self.channel = _make_channel(
            "stress-balcao",
            config={
                "confirmation": {"mode": "immediate"},
                "payment": {"method": "cash", "timing": "external"},
            },
        )
        _make_product(self.SKU)
        self.position = _make_position("stress-vitrine")
        _receive(5, self.SKU, self.position)

    def test_commit_fulfills_stock_and_late_cancel_returns_it(self) -> None:
        from shopman.orderman.models import Order
        from shopman.stockman import Hold, HoldStatus
        from shopman.stockman.models import Quant

        from shopman.shop.services import cancellation

        _open_session(self.channel.ref, "STRESS-PDV-SS-001", self.SKU, qty=2)
        with self.captureOnCommitCallbacks(execute=True):
            result = _commit("STRESS-PDV-SS-001", self.channel.ref, "STRESS-PDV-KEY-001")

        order = Order.objects.get(ref=result.order_ref)
        self.assertEqual(order.status, Order.Status.CONFIRMED)

        # Venda de balcão baixou o físico na confirmação (hold FULFILLED).
        entries = [h for h in order.data.get("hold_ids", []) if h.get("hold_id")]
        self.assertEqual(len(entries), 1)
        hold = Hold.objects.get(pk=int(entries[0]["hold_id"].split(":")[1]))
        self.assertEqual(hold.status, HoldStatus.FULFILLED)
        quant = Quant.objects.get(sku=self.SKU, position=self.position)
        self.assertEqual(quant.quantity, Decimal("3"))
        self.assertEqual(_available(self.SKU), Decimal("3"))

        # Cancel tardio (pós-baixa): release é no-op, revert_fulfilled devolve.
        with self.captureOnCommitCallbacks(execute=True):
            self.assertTrue(cancellation.cancel(order, "operator_typo", actor="operator"))
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertEqual(_available(self.SKU), Decimal("5"))
        self.assertEqual(order.data.get("reverted_hold_ids"), [entries[0]["hold_id"]])


# ═════════════════════════════════════════════════════════════════════════════
# 2. Estoque insuficiente no commit
# ═════════════════════════════════════════════════════════════════════════════


class InsufficientStockCommitTests(TestCase):
    """Gate de commit: falha limpa, sem Order fantasma, sem hold vazado."""

    SKU = "STRESS-GATE-SKU"

    def setUp(self):
        _make_shop()
        self.channel = _make_channel("stress-gate")
        _make_product(self.SKU)
        self.position = _make_position("stress-vitrine")
        _receive(1, self.SKU, self.position)

    def test_commit_beyond_stock_fails_clean_no_order_no_hold(self) -> None:
        from shopman.orderman.exceptions import ValidationError
        from shopman.orderman.models import IdempotencyKey, Order, Session

        _open_session(self.channel.ref, "STRESS-GATE-SS-001", self.SKU, qty=3)

        with self.assertRaises(ValidationError) as ctx:
            _commit("STRESS-GATE-SS-001", self.channel.ref, "STRESS-GATE-KEY-001")

        self.assertEqual(ctx.exception.code, "insufficient_stock")
        # Transação inteira desfeita: nada de pedido órfão nem reserva vazada.
        self.assertEqual(Order.objects.filter(channel_ref=self.channel.ref).count(), 0)
        self.assertEqual(_active_holds(self.SKU).count(), 0)
        self.assertEqual(_available(self.SKU), Decimal("1"))
        self.assertEqual(
            Session.objects.get(session_key="STRESS-GATE-SS-001").state, "open"
        )
        idem = IdempotencyKey.objects.get(
            scope=f"commit:{self.channel.ref}:STRESS-GATE-SS-001",
            key="STRESS-GATE-KEY-001",
        )
        self.assertEqual(idem.status, "failed")

    def test_cart_hold_survives_failed_commit_without_leaking(self) -> None:
        """Adoção do hold de sacola dentro da transação que falha é DESFEITA:
        o hold volta intacto para a sessão (nem some, nem vira hold de pedido)."""
        from shopman.orderman.exceptions import ValidationError
        from shopman.stockman import Hold

        from shopman.shop.services import availability

        reserved = availability.reserve(
            self.SKU, Decimal("1"),
            session_key="STRESS-GATE-SS-002",
            channel_ref=self.channel.ref,
        )
        self.assertTrue(reserved["ok"])

        # Sessão pede 3 (hold cobre 1, faltam 2 sem estoque) → gate falha.
        _open_session(self.channel.ref, "STRESS-GATE-SS-002", self.SKU, qty=3)
        with self.assertRaises(ValidationError):
            _commit("STRESS-GATE-SS-002", self.channel.ref, "STRESS-GATE-KEY-002")

        hold = Hold.objects.get(pk=int(reserved["hold_id"].split(":")[1]))
        self.assertEqual(hold.metadata.get("reference"), "STRESS-GATE-SS-002")
        self.assertEqual(hold.quantity, Decimal("1"))
        self.assertEqual(_active_holds(self.SKU).count(), 1)

    def test_retry_same_idempotency_key_after_restock_succeeds(self) -> None:
        """Key marcada failed permite retry — reposição de estoque destrava."""
        from shopman.orderman.exceptions import ValidationError
        from shopman.orderman.models import Order

        _open_session(self.channel.ref, "STRESS-GATE-SS-003", self.SKU, qty=3)
        with self.assertRaises(ValidationError):
            _commit("STRESS-GATE-SS-003", self.channel.ref, "STRESS-GATE-KEY-003")

        _receive(2, self.SKU, self.position)  # repõe: total 3
        with self.captureOnCommitCallbacks(execute=True):
            result = _commit("STRESS-GATE-SS-003", self.channel.ref, "STRESS-GATE-KEY-003")

        self.assertEqual(result.status, "committed")
        self.assertEqual(Order.objects.filter(channel_ref=self.channel.ref).count(), 1)


# ═════════════════════════════════════════════════════════════════════════════
# 3. Corrida de oversell
# ═════════════════════════════════════════════════════════════════════════════


@requires_postgres
class OversellRaceTests(TransactionTestCase):
    """6 compradores concorrentes para estoque 3 — nunca vende acima do físico.

    O ``select_for_update`` de Quant no Stockman serializa os commits do mesmo
    SKU dentro da transação do ``CommitService`` (``lifecycle.secure_stock``).
    """

    SKU = "STRESS-RACE-SKU"

    def setUp(self):
        _make_shop()
        self.channel = _make_channel("stress-race")
        _make_product(self.SKU)
        _receive(3, self.SKU, _make_position("stress-vitrine"))

    def _buy(self, i: int):
        from django.db import connections

        session_key = f"STRESS-RACE-SS-{i:03d}"
        try:
            _open_session(self.channel.ref, session_key, self.SKU, qty=1)
            result = _commit(session_key, self.channel.ref, f"STRESS-RACE-KEY-{i:03d}")
            return (True, result.order_ref, None)
        except Exception as exc:
            return (False, None, exc)
        finally:
            connections.close_all()

    def test_concurrent_buyers_never_oversell_and_losers_hold_nothing(self) -> None:
        from shopman.orderman.exceptions import ValidationError
        from shopman.orderman.models import Order

        results = []
        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = [executor.submit(self._buy, i) for i in range(6)]
            for future in as_completed(futures):
                results.append(future.result())

        successes = [r for r in results if r[0]]
        failures = [r for r in results if not r[0]]
        self.assertEqual(len(successes) + len(failures), 6)

        # Física: no máximo 3 vendas; com serialização de linha, exatamente 3.
        order_count = Order.objects.filter(channel_ref=self.channel.ref).count()
        self.assertEqual(order_count, len(successes))
        self.assertEqual(order_count, 3)

        # Perdedores falharam LIMPO (insufficient_stock) — nunca erro cru de DB.
        for _, _, exc in failures:
            self.assertIsInstance(exc, ValidationError)
            self.assertEqual(exc.code, "insufficient_stock")

        # Reservas ativas pertencem SÓ aos vencedores; nada preso dos perdedores.
        active = list(_active_holds(self.SKU))
        held_qty = sum((h.quantity for h in active), Decimal("0"))
        self.assertEqual(held_qty, Decimal("3"))
        refs = {h.metadata.get("reference") for h in active}
        winner_refs = {f"order:{r[1]}" for r in successes}
        self.assertEqual(refs, winner_refs)
        self.assertEqual(_available(self.SKU), Decimal("0"))


# ═════════════════════════════════════════════════════════════════════════════
# 4. Exclusão de posição D-1 ("ontem")
# ═════════════════════════════════════════════════════════════════════════════


class D1PositionExclusionTests(TestCase):
    """Canal remoto com ``excluded_positions=["ontem"]`` não vê nem reserva D-1."""

    SKU = "STRESS-D1-SKU"

    def setUp(self):
        _make_shop()
        self.remote = _make_channel(
            "stress-remote",
            config={"stock": {"excluded_positions": ["ontem"]}},
        )
        self.balcao = _make_channel("stress-pdv-scope")  # sem exclusão: vê tudo
        _make_product(self.SKU)
        self.vitrine = _make_position("stress-vitrine")
        self.ontem = _make_position("ontem")
        _receive(4, self.SKU, self.ontem)  # só saldo D-1

    def test_remote_channel_does_not_see_ontem_balance(self) -> None:
        from shopman.shop.services import availability

        remote = availability.check(self.SKU, Decimal("1"), channel_ref=self.remote.ref)
        self.assertFalse(remote["ok"])
        self.assertEqual(remote["available_qty"], Decimal("0"))

        balcao = availability.check(self.SKU, Decimal("1"), channel_ref=self.balcao.ref)
        self.assertTrue(balcao["ok"])
        self.assertEqual(balcao["available_qty"], Decimal("4"))

    def test_remote_reserve_refuses_and_leaks_no_hold(self) -> None:
        from shopman.shop.services import availability

        result = availability.reserve(
            self.SKU, Decimal("1"),
            session_key="STRESS-D1-SS-001",
            channel_ref=self.remote.ref,
        )
        self.assertFalse(result["ok"])
        self.assertIsNone(result["hold_id"])
        self.assertEqual(_active_holds(self.SKU).count(), 0)

    def test_remote_commit_cannot_consume_ontem_but_balcao_can(self) -> None:
        from shopman.orderman.exceptions import ValidationError
        from shopman.orderman.models import Order
        from shopman.stockman import Hold

        # Canal remoto: gate transacional recusa (escopo exclui "ontem").
        _open_session(self.remote.ref, "STRESS-D1-SS-002", self.SKU, qty=1)
        with self.assertRaises(ValidationError) as ctx:
            _commit("STRESS-D1-SS-002", self.remote.ref, "STRESS-D1-KEY-002")
        self.assertEqual(ctx.exception.code, "insufficient_stock")
        self.assertEqual(Order.objects.count(), 0)

        # Balcão (sem exclusão) vende o mesmo saldo normalmente.
        _open_session(self.balcao.ref, "STRESS-D1-SS-003", self.SKU, qty=1)
        with self.captureOnCommitCallbacks(execute=True):
            result = _commit("STRESS-D1-SS-003", self.balcao.ref, "STRESS-D1-KEY-003")
        order = Order.objects.get(ref=result.order_ref)
        entries = [h for h in order.data.get("hold_ids", []) if h.get("hold_id")]
        self.assertEqual(len(entries), 1)
        hold = Hold.objects.get(pk=int(entries[0]["hold_id"].split(":")[1]))
        self.assertEqual(hold.quant.position.ref, "ontem")

    def test_remote_still_sees_vitrine_balance(self) -> None:
        """A denylist é cirúrgica: com saldo em vitrine, o remoto vende dela."""
        from shopman.shop.services import availability

        _receive(2, self.SKU, self.vitrine)
        result = availability.check(self.SKU, Decimal("2"), channel_ref=self.remote.ref)
        self.assertTrue(result["ok"])
        self.assertEqual(result["available_qty"], Decimal("2"))


# ═════════════════════════════════════════════════════════════════════════════
# 5. Encomenda / estoque planejado (Quant target_date)
# ═════════════════════════════════════════════════════════════════════════════


class PreorderPlannedStockTests(TestCase):
    """Data futura promete só o que está PLANEJADO para a data (perecível D+0)."""

    SKU = "STRESS-PRE-SKU"

    def setUp(self):
        from django.utils import timezone

        _make_shop()
        # preorder=False: sem plano para a data → recusa (nada de demanda).
        self.no_preorder = _make_channel(
            "stress-nopre", config={"stock": {"preorder": False}}
        )
        # defaults: preorder=True → sem plano vira registro de demanda.
        self.web = _make_channel("stress-pre-web")
        self.product = _make_product(self.SKU, shelf_life_days=0)  # validade D+0
        self.vitrine = _make_position("stress-vitrine")
        _receive(5, self.SKU, self.vitrine)  # fornada de HOJE (não vale amanhã)
        self.tomorrow = timezone.localdate() + timedelta(days=1)

    def _plan(self, qty: int):
        from shopman.stockman.service import Stock

        Stock.plan(Decimal(str(qty)), self.product, self.tomorrow)

    def test_future_availability_requires_matching_planned_quant(self) -> None:
        from shopman.shop.services import availability

        before = availability.check(
            self.SKU, Decimal("2"),
            channel_ref=self.web.ref, target_date=self.tomorrow,
        )
        self.assertFalse(before["ok"])  # fornada de hoje é perecível: 0 amanhã

        self._plan(3)
        after = availability.check(
            self.SKU, Decimal("2"),
            channel_ref=self.web.ref, target_date=self.tomorrow,
        )
        self.assertTrue(after["ok"])
        self.assertEqual(after["available_qty"], Decimal("3"))

    def test_preorder_commit_anchors_hold_on_planned_quant(self) -> None:
        from shopman.orderman.models import Order
        from shopman.stockman import Hold

        self._plan(3)
        _open_session(
            self.no_preorder.ref, "STRESS-PRE-SS-001", self.SKU, qty=2,
            data={"delivery_date": self.tomorrow.isoformat()},
        )
        with self.captureOnCommitCallbacks(execute=True):
            result = _commit("STRESS-PRE-SS-001", self.no_preorder.ref, "STRESS-PRE-KEY-001")

        order = Order.objects.get(ref=result.order_ref)
        self.assertTrue(order.data.get("is_preorder"))
        self.assertEqual(order.status, Order.Status.CONFIRMED)
        entries = [h for h in order.data.get("hold_ids", []) if h.get("hold_id")]
        self.assertEqual(len(entries), 1)
        hold = Hold.objects.get(pk=int(entries[0]["hold_id"].split(":")[1]))
        # Reserva ancorada no quant PLANEJADO da data — não no físico de hoje.
        self.assertIsNotNone(hold.quant)
        self.assertEqual(hold.quant.target_date, self.tomorrow)
        self.assertEqual(hold.target_date, self.tomorrow)
        # Fornada de hoje intocada (trabalho físico adiado para a data).
        self.assertEqual(_available(self.SKU), Decimal("5"))

    def test_no_plan_and_no_preorder_refuses_clean(self) -> None:
        from shopman.orderman.exceptions import ValidationError
        from shopman.orderman.models import Order

        _open_session(
            self.no_preorder.ref, "STRESS-PRE-SS-002", self.SKU, qty=2,
            data={"delivery_date": self.tomorrow.isoformat()},
        )
        with self.assertRaises(ValidationError) as ctx:
            _commit("STRESS-PRE-SS-002", self.no_preorder.ref, "STRESS-PRE-KEY-002")
        self.assertEqual(ctx.exception.code, "insufficient_stock")
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(_active_holds(self.SKU).count(), 0)

    def test_no_plan_with_preorder_registers_demand_hold(self) -> None:
        """Seam documentado: canal com ``stock.preorder=True`` (default) aceita a
        encomenda SEM plano registrando demanda — hold flutuante ``quant=None``."""
        from shopman.orderman.models import Order
        from shopman.stockman import Hold, HoldStatus

        _open_session(
            self.web.ref, "STRESS-PRE-SS-003", self.SKU, qty=2,
            data={"delivery_date": self.tomorrow.isoformat()},
        )
        with self.captureOnCommitCallbacks(execute=True):
            result = _commit("STRESS-PRE-SS-003", self.web.ref, "STRESS-PRE-KEY-003")

        order = Order.objects.get(ref=result.order_ref)
        entries = [h for h in order.data.get("hold_ids", []) if h.get("hold_id")]
        self.assertEqual(len(entries), 1)
        hold = Hold.objects.get(pk=int(entries[0]["hold_id"].split(":")[1]))
        self.assertIsNone(hold.quant)  # demanda registrada, não estoque físico
        self.assertEqual(hold.target_date, self.tomorrow)
        self.assertIn(hold.status, (HoldStatus.PENDING, HoldStatus.CONFIRMED))


# ═════════════════════════════════════════════════════════════════════════════
# 6. Double-submit sob corrida (mesma idempotency key)
# ═════════════════════════════════════════════════════════════════════════════


@requires_postgres
class DoubleSubmitRaceTests(TransactionTestCase):
    """2 threads, MESMA sessão e MESMA idempotency key → um pedido só."""

    SKU = "STRESS-IDEM-SKU"

    def setUp(self):
        _make_shop()
        self.channel = _make_channel("stress-idem")
        _make_product(self.SKU)
        _receive(3, self.SKU, _make_position("stress-vitrine"))
        _open_session(self.channel.ref, "STRESS-IDEM-SS-001", self.SKU, qty=1)

    def _submit(self):
        from django.db import connections

        try:
            result = _commit("STRESS-IDEM-SS-001", self.channel.ref, "STRESS-IDEM-KEY-001")
            return ("ok", result.order_ref)
        except Exception as exc:
            return ("error", exc)
        finally:
            connections.close_all()

    def test_double_submit_creates_exactly_one_order(self) -> None:
        from shopman.orderman.exceptions import CommitError
        from shopman.orderman.models import Order

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = [f.result() for f in [executor.submit(self._submit) for _ in range(2)]]

        oks = [r for r in results if r[0] == "ok"]
        errors = [r for r in results if r[0] == "error"]

        # Pelo menos um venceu; qualquer perdedor falhou com o dialeto conhecido
        # (in_progress) ou recebeu o MESMO pedido do cache de idempotência.
        self.assertGreaterEqual(len(oks), 1)
        order_refs = {r[1] for r in oks}
        self.assertEqual(len(order_refs), 1)
        for _, exc in errors:
            self.assertIsInstance(exc, CommitError)
            self.assertEqual(exc.code, "in_progress")

        self.assertEqual(
            Order.objects.filter(session_key="STRESS-IDEM-SS-001").count(), 1
        )
        # Uma venda de 1 unidade → uma reserva ativa de 1; nada duplicado.
        active = list(_active_holds(self.SKU))
        self.assertEqual(sum((h.quantity for h in active), Decimal("0")), Decimal("1"))
        self.assertEqual(_available(self.SKU), Decimal("2"))


# ═════════════════════════════════════════════════════════════════════════════
# 7. Cancelamento idempotente
# ═════════════════════════════════════════════════════════════════════════════


class IdempotentCancellationTests(TestCase):
    """Cancelar duas vezes nunca devolve estoque em dobro."""

    SKU = "STRESS-CANCEL-SKU"

    def setUp(self):
        _make_shop()
        self.web = _make_channel("stress-cancel-web")
        self.balcao = _make_channel(
            "stress-cancel-pdv",
            config={
                "confirmation": {"mode": "immediate"},
                "payment": {"method": "cash", "timing": "external"},
            },
        )
        _make_product(self.SKU)
        self.position = _make_position("stress-vitrine")
        _receive(5, self.SKU, self.position)

    def _committed_order(self, channel, session_key: str, idem_key: str):
        from shopman.orderman.models import Order

        _open_session(channel.ref, session_key, self.SKU, qty=2)
        with self.captureOnCommitCallbacks(execute=True):
            result = _commit(session_key, channel.ref, idem_key)
        return Order.objects.get(ref=result.order_ref)

    def test_double_cancel_web_releases_hold_once(self) -> None:
        from shopman.shop.services import cancellation

        order = self._committed_order(self.web, "STRESS-CXL-SS-001", "STRESS-CXL-KEY-001")
        with self.captureOnCommitCallbacks(execute=True):
            self.assertTrue(cancellation.cancel(order, "customer_requested"))
        self.assertEqual(_available(self.SKU), Decimal("5"))

        # Segundo cancel: estado terminal → recusado, sem novo release.
        order.refresh_from_db()
        with self.captureOnCommitCallbacks(execute=True):
            self.assertFalse(cancellation.cancel(order, "customer_requested"))
        self.assertEqual(_available(self.SKU), Decimal("5"))

    def test_double_cancel_balcao_does_not_double_credit_ledger(self) -> None:
        from shopman.shop.services import cancellation
        from shopman.shop.services import stock as stock_service

        order = self._committed_order(self.balcao, "STRESS-CXL-SS-002", "STRESS-CXL-KEY-002")
        self.assertEqual(_available(self.SKU), Decimal("3"))  # fulfilled no ato

        with self.captureOnCommitCallbacks(execute=True):
            self.assertTrue(cancellation.cancel(order, "operator_typo", actor="operator"))
        self.assertEqual(_available(self.SKU), Decimal("5"))

        order.refresh_from_db()
        with self.captureOnCommitCallbacks(execute=True):
            self.assertFalse(cancellation.cancel(order, "operator_typo", actor="operator"))
        self.assertEqual(_available(self.SKU), Decimal("5"))

        # Mesmo um re-dispatch direto do on_cancelled (sweeper/crash replay) não
        # duplica a devolução: reverted_hold_ids marca o que já voltou.
        stock_service.revert_fulfilled(order)
        self.assertEqual(_available(self.SKU), Decimal("5"))


# ═════════════════════════════════════════════════════════════════════════════
# 8. Sessão malformada: qty inválida, sessão vazia, SKU inexistente
# ═════════════════════════════════════════════════════════════════════════════


class MalformedSessionTests(TestCase):
    """Entradas inválidas nunca viram 500 sem tratamento nem pedido sujo."""

    SKU = "STRESS-BAD-SKU"

    def setUp(self):
        _make_shop()
        self.channel = _make_channel("stress-bad")
        _make_product(self.SKU)
        _receive(5, self.SKU, _make_position("stress-vitrine"))

    def test_qty_zero_line_is_blocked_by_core_constraint(self) -> None:
        """qty=0 não chega ao commit: o espelho SessionItem tem check constraint
        (``ord_session_item_qty_positive``) — a linha malformada nem persiste."""
        from django.db import IntegrityError, transaction

        with self.assertRaises(IntegrityError), transaction.atomic():
            _open_session(self.channel.ref, "STRESS-BAD-SS-001", self.SKU, qty=0)

    def test_qty_negative_line_is_blocked_by_core_constraint(self) -> None:
        from django.db import IntegrityError, transaction

        with self.assertRaises(IntegrityError), transaction.atomic():
            _open_session(self.channel.ref, "STRESS-BAD-SS-002", self.SKU, qty=-2)

    def test_empty_session_commit_fails_clean(self) -> None:
        from shopman.orderman.exceptions import CommitError
        from shopman.orderman.models import Order

        _open_session(self.channel.ref, "STRESS-BAD-SS-003", self.SKU, qty=1, items=[])
        with self.assertRaises(CommitError) as ctx:
            _commit("STRESS-BAD-SS-003", self.channel.ref, "STRESS-BAD-KEY-003")
        self.assertEqual(ctx.exception.code, "empty_session")
        self.assertEqual(Order.objects.count(), 0)

    def test_unknown_sku_commits_as_untracked_without_stock_impact(self) -> None:
        """Seam deliberado (``stock._sku_known_to_catalog``): SKU fora do catálogo
        não tem o que reservar — commita como untracked, sem hold e sem 500."""
        from shopman.orderman.models import Order

        _open_session(self.channel.ref, "STRESS-BAD-SS-004", "STRESS-GHOST-SKU", qty=1)
        with self.captureOnCommitCallbacks(execute=True):
            result = _commit("STRESS-BAD-SS-004", self.channel.ref, "STRESS-BAD-KEY-004")

        order = Order.objects.get(ref=result.order_ref)
        entries = order.data.get("hold_ids", [])
        self.assertEqual(len(entries), 1)
        self.assertTrue(entries[0].get("untracked"))
        self.assertIsNone(entries[0].get("hold_id"))
        self.assertEqual(_active_holds().count(), 0)


# ═════════════════════════════════════════════════════════════════════════════
# Extras: contrato Session→Order (order_notes), preço selado e cupom
# ═════════════════════════════════════════════════════════════════════════════


class SessionDataPropagationTests(TestCase):
    """``_do_commit`` copia a LISTA EXPLÍCITA de chaves de session.data."""

    SKU = "STRESS-DATA-SKU"

    def setUp(self):
        _make_shop()
        self.channel = _make_channel("stress-data")
        _make_product(self.SKU)
        _receive(5, self.SKU, _make_position("stress-vitrine"))

    def test_order_notes_and_known_keys_propagate_unknown_keys_do_not(self) -> None:
        from shopman.orderman.models import Order

        _open_session(
            self.channel.ref, "STRESS-DATA-SS-001", self.SKU, qty=1,
            data={
                "order_notes": "Sem cebola, por favor",
                "fulfillment_type": "pickup",
                "origin_channel": "web",
                "customer": {"ref": "cust-stress-1", "name": "Cliente Stress"},
                "internal_scratch": {"never": "propagate"},
            },
        )
        with self.captureOnCommitCallbacks(execute=True):
            result = _commit("STRESS-DATA-SS-001", self.channel.ref, "STRESS-DATA-KEY-001")

        order = Order.objects.get(ref=result.order_ref)
        self.assertEqual(order.data.get("order_notes"), "Sem cebola, por favor")
        self.assertEqual(order.data.get("fulfillment_type"), "pickup")
        self.assertEqual(order.data.get("origin_channel"), "web")
        self.assertEqual(order.data.get("customer_ref"), "cust-stress-1")
        # Chave fora da lista explícita NÃO vaza para order.data…
        self.assertNotIn("internal_scratch", order.data)
        # …mas o snapshot selado preserva a sessão inteira para auditoria.
        self.assertEqual(
            order.snapshot["data"]["internal_scratch"], {"never": "propagate"}
        )


class RepricingAndCouponTests(TestCase):
    """Preço do carrinho é selado no commit; cupom conta uso e devolve no cancel."""

    SKU = "STRESS-PRICE-SKU"

    def setUp(self):
        _make_shop()
        self.channel = _make_channel("stress-price")
        self.product = _make_product(self.SKU, price_q=1000)
        _receive(5, self.SKU, _make_position("stress-vitrine"))

    def test_commit_seals_cart_price_even_if_catalog_repriced(self) -> None:
        """Comportamento documentado: o commit NÃO reprecifica — vende pelo preço
        selado na sessão. Drift >5% entre carrinho e catálogo é responsabilidade
        do aviso não-bloqueante do storefront (``projections.checkout.
        repricing_changes``), nunca de um recálculo silencioso no commit."""
        from shopman.orderman.models import Order

        _open_session(
            self.channel.ref, "STRESS-PRICE-SS-001", self.SKU, qty=2, price_q=800
        )
        # Catálogo sobe DEPOIS do item entrar na sacola.
        self.product.base_price_q = 1200
        self.product.save(update_fields=["base_price_q"])

        with self.captureOnCommitCallbacks(execute=True):
            result = _commit("STRESS-PRICE-SS-001", self.channel.ref, "STRESS-PRICE-KEY-001")

        order = Order.objects.get(ref=result.order_ref)
        self.assertEqual(order.total_q, 1600)  # 2 × R$ 8,00 do carrinho
        item = order.items.get()
        self.assertEqual(item.unit_price_q, 800)

    def test_coupon_use_counted_on_commit_and_released_on_cancel(self) -> None:
        from django.utils import timezone
        from shopman.orderman.models import Order, Session

        from shopman.shop.services import cancellation
        from shopman.storefront.models import Coupon, Promotion

        now = timezone.now()
        promo = Promotion.objects.create(
            name="Stress Fixed",
            type=Promotion.FIXED,
            value=500,
            valid_from=now - timedelta(days=1),
            valid_until=now + timedelta(days=1),
        )
        coupon = Coupon.objects.create(code="STRESS500", promotion=promo, max_uses=1)

        session = _open_session(
            self.channel.ref, "STRESS-PRICE-SS-002", self.SKU, qty=2,
            data={"coupon_code": "STRESS500"},
        )
        Session.objects.filter(pk=session.pk).update(
            pricing={"coupon": {"code": "STRESS500", "discount_q": 500}}
        )

        with self.captureOnCommitCallbacks(execute=True):
            result = _commit("STRESS-PRICE-SS-002", self.channel.ref, "STRESS-PRICE-KEY-002")

        order = Order.objects.get(ref=result.order_ref)
        coupon.refresh_from_db()
        self.assertEqual(coupon.uses_count, 1)
        self.assertEqual(order.data.get("coupon_use_recorded"), "STRESS500")

        # Cancelamento devolve o uso — o cupom single-use volta a valer.
        with self.captureOnCommitCallbacks(execute=True):
            self.assertTrue(cancellation.cancel(order, "customer_requested"))
        coupon.refresh_from_db()
        self.assertEqual(coupon.uses_count, 0)
        order.refresh_from_db()
        self.assertNotIn("coupon_use_recorded", order.data)
