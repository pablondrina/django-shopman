"""Gate duro de estoque no commit — ``lifecycle.secure_stock``.

O CommitService emite ``order_changed`` (created) DENTRO da transação do
``_do_commit``; o shop conecta ``secure_stock`` síncrono nesse signal. Para
canais que vendem estoque gerido pelo Shopman (``payment.timing`` diferente de
``external`` e sem ``stock.check_on_commit``), a reserva precisa ser garantida
na própria transação: falha de hold desfaz o commit inteiro e NENHUM pedido
nasce. É a versão determinística (sequencial, SQLite) da invariante que o
stress test de PostgreSQL (``test_concurrent_checkout``) exercita sob
concorrência real.
"""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase


def _make_shop():
    from shopman.shop.models import Shop

    return Shop.objects.get_or_create(name="Test Shop", defaults={"brand_name": "Test"})[0]


def _make_channel(ref: str, config: dict | None = None):
    from shopman.shop.models import Channel

    return Channel.objects.get_or_create(
        ref=ref,
        defaults={"name": ref, "is_active": True, "config": config or {}},
    )[0]


def _make_tracked_product(sku: str, qty: int):
    from shopman.offerman.models import Product
    from shopman.stockman import stock as stockman_stock
    from shopman.stockman.models import Position, PositionKind

    product = Product.objects.create(
        sku=sku,
        name=f"Produto {sku}",
        base_price_q=1000,
        is_published=True,
        is_sellable=True,
    )
    position, _ = Position.objects.get_or_create(
        ref="gate-vitrine",
        defaults={"name": "Gate Vitrine", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )
    if qty:
        stockman_stock.receive(Decimal(str(qty)), sku, position, reason="commit gate test setup")
    return product


def _open_session(channel_ref: str, session_key: str, sku: str, qty: int):
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
        data={},
    )


def _commit(session_key: str, channel_ref: str, idem_key: str):
    from shopman.orderman.services.commit import CommitService

    return CommitService.commit(
        session_key=session_key,
        channel_ref=channel_ref,
        idempotency_key=idem_key,
    )


class CommitStockGateTests(TestCase):
    """Canal default (payment post_commit): estoque garantido ou o commit falha."""

    SKU = "GATE-SKU-001"

    def setUp(self):
        _make_shop()
        self.channel = _make_channel("gate-web")
        _make_tracked_product(self.SKU, qty=3)

    def test_commit_without_stock_fails_and_creates_no_order(self) -> None:
        from shopman.orderman.exceptions import ValidationError
        from shopman.orderman.models import Order, Session

        _open_session(self.channel.ref, "GATE-SS-001", self.SKU, qty=5)

        with self.assertRaises(ValidationError) as ctx:
            _commit("GATE-SS-001", self.channel.ref, "GATE-KEY-001")

        self.assertEqual(ctx.exception.code, "insufficient_stock")
        self.assertEqual(ctx.exception.context.get("sku"), self.SKU)
        # A transação inteira desfez: nenhum pedido órfão, sessão continua aberta.
        self.assertEqual(Order.objects.filter(channel_ref=self.channel.ref).count(), 0)
        session = Session.objects.get(session_key="GATE-SS-001")
        self.assertEqual(session.state, "open")

    def test_failed_commit_marks_idempotency_key_failed(self) -> None:
        from shopman.orderman.exceptions import ValidationError
        from shopman.orderman.models import IdempotencyKey

        _open_session(self.channel.ref, "GATE-SS-002", self.SKU, qty=5)

        with self.assertRaises(ValidationError):
            _commit("GATE-SS-002", self.channel.ref, "GATE-KEY-002")

        idem = IdempotencyKey.objects.get(
            scope=f"commit:{self.channel.ref}:GATE-SS-002", key="GATE-KEY-002"
        )
        self.assertEqual(idem.status, "failed")

    def test_sequential_commits_stop_exactly_at_stock(self) -> None:
        """Estoque 3, cinco checkouts de 1: exatamente 3 pedidos nascem."""
        from shopman.orderman.exceptions import ValidationError
        from shopman.orderman.models import Order

        results: list[bool] = []
        for i in range(5):
            _open_session(self.channel.ref, f"GATE-SEQ-{i:03d}", self.SKU, qty=1)
            try:
                _commit(f"GATE-SEQ-{i:03d}", self.channel.ref, f"GATE-SEQ-KEY-{i:03d}")
                results.append(True)
            except ValidationError as exc:
                self.assertEqual(exc.code, "insufficient_stock")
                results.append(False)

        self.assertEqual(results, [True, True, True, False, False])
        self.assertEqual(Order.objects.filter(channel_ref=self.channel.ref).count(), 3)

    def test_successful_commit_persists_holds_in_transaction(self) -> None:
        """Os holds nascem NA transação do commit — pedido e reserva são atômicos."""
        from shopman.orderman.models import Order

        _open_session(self.channel.ref, "GATE-SS-003", self.SKU, qty=2)
        result = _commit("GATE-SS-003", self.channel.ref, "GATE-KEY-003")

        order = Order.objects.get(ref=result.order_ref)
        hold_ids = (order.data or {}).get("hold_ids", [])
        self.assertEqual(len(hold_ids), 1)
        self.assertTrue(hold_ids[0].get("hold_id"))
        self.assertEqual(hold_ids[0].get("sku"), self.SKU)

    def test_gate_adopts_session_holds_from_cart(self) -> None:
        """Reserva de carrinho (reference=session_key) cobre o gate sem estoque novo.

        Com estoque total 3 e um hold de sessão de 3, um hold FRESCO de 3 seria
        impossível (o próprio hold de sessão consome a disponibilidade) — o
        commit só passa porque o gate adota a reserva existente do carrinho.
        """
        from shopman.orderman.models import Order

        from shopman.shop.adapters import get_adapter

        _open_session(self.channel.ref, "GATE-SS-004", self.SKU, qty=3)
        adapter = get_adapter("stock")
        reserved = adapter.create_hold(
            sku=self.SKU,
            qty=Decimal("3"),
            reference="GATE-SS-004",
            channel_ref=self.channel.ref,
        )
        self.assertTrue(reserved.get("success"))

        result = _commit("GATE-SS-004", self.channel.ref, "GATE-KEY-004")

        order = Order.objects.get(ref=result.order_ref)
        hold_ids = (order.data or {}).get("hold_ids", [])
        self.assertEqual([h.get("hold_id") for h in hold_ids], [reserved["hold_id"]])

    def test_untracked_sku_commits_without_hold(self) -> None:
        """SKU fora do Stockman (sem Quants) não exige reserva — commit passa."""
        from shopman.orderman.models import Order

        _open_session(self.channel.ref, "GATE-SS-005", "GATE-UNTRACKED-SKU", qty=2)
        result = _commit("GATE-SS-005", self.channel.ref, "GATE-KEY-005")

        order = Order.objects.get(ref=result.order_ref)
        hold_ids = (order.data or {}).get("hold_ids", [])
        self.assertEqual(len(hold_ids), 1)
        self.assertTrue(hold_ids[0].get("untracked"))


class CommitStockGateExternalChannelTests(TestCase):
    """Canais external (PDV, marketplace) mantêm o caminho otimista intacto."""

    SKU = "GATE-SKU-EXT"

    def setUp(self):
        _make_shop()
        self.channel = _make_channel(
            "gate-ext",
            config={"payment": {"method": "cash", "timing": "external"}},
        )
        _make_tracked_product(self.SKU, qty=1)

    def test_external_channel_commits_even_without_stock(self) -> None:
        """Pedido já consumado no mundo externo: aceitar sempre, alertar depois."""
        from shopman.orderman.models import Order

        # Estoque 1, pedido de 2: num canal não-external o gate rejeitaria.
        _open_session(self.channel.ref, "GATE-EXT-001", self.SKU, qty=2)

        with self.captureOnCommitCallbacks(execute=True):
            result = _commit("GATE-EXT-001", self.channel.ref, "GATE-EXT-KEY-001")

        order = Order.objects.get(ref=result.order_ref)
        # Reserva best-effort falhou (sem estoque), mas o pedido existe e o
        # operador foi alertado do gap — comportamento otimista preservado.
        held = [h for h in (order.data or {}).get("hold_ids", []) if h.get("hold_id")]
        self.assertEqual(held, [])

        from shopman.backstage.models import OperatorAlert

        self.assertTrue(
            OperatorAlert.objects.filter(type="stock_hold_gap", order_ref=order.ref).exists()
        )


class CommitStockGateCheckOnCommitTests(TestCase):
    """Canais com stock.check_on_commit usam o gate próprio do dispatch (não o do commit)."""

    SKU = "GATE-SKU-COC"

    def setUp(self):
        _make_shop()
        self.channel = _make_channel(
            "gate-coc",
            config={"stock": {"check_on_commit": True}},
        )
        _make_tracked_product(self.SKU, qty=0)

    def test_check_on_commit_channel_skips_transactional_gate(self) -> None:
        """O commit passa; a rejeição fica a cargo do fluxo check→hold→verify."""
        from shopman.orderman.models import Order

        _open_session(self.channel.ref, "GATE-COC-001", self.SKU, qty=1)
        result = _commit("GATE-COC-001", self.channel.ref, "GATE-COC-KEY-001")

        # O pedido nasce (gate transacional não se aplica) e o dispatch
        # assume a decisão de disponibilidade na fase on_commit.
        self.assertTrue(Order.objects.filter(ref=result.order_ref).exists())
