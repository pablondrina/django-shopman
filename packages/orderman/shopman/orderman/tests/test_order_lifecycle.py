"""
Testes abrangentes para Order lifecycle, status transitions e timestamps.
Cobre cenários realistas de iFood, E-commerce e PDV.
"""
from __future__ import annotations
import types

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from shopman.orderman.exceptions import InvalidTransition
from shopman.orderman.models import Order, OrderEvent, OrderItem, Session


class OrderTimestampTests(TestCase):
    """Testes para timestamps de lifecycle do Order."""

    def setUp(self) -> None:
        self.channel = types.SimpleNamespace(ref="shop", name="Shop")
        self.order = Order.objects.create(
            ref="ORD-TS-001",
            channel_ref=self.channel.ref,
            status=Order.STATUS_NEW,
            total_q=10000,
        )

    def test_created_at_is_set_on_creation(self) -> None:
        """created_at é definido automaticamente na criação."""
        self.assertIsNotNone(self.order.created_at)

    def test_confirmed_at_is_set_on_transition(self) -> None:
        """confirmed_at é definido ao transicionar para confirmed."""
        self.assertIsNone(self.order.confirmed_at)
        self.order.transition_status(Order.STATUS_CONFIRMED, actor="test")
        self.order.refresh_from_db()
        self.assertIsNotNone(self.order.confirmed_at)

    def test_preparing_at_is_set_on_transition(self) -> None:
        """preparing_at é definido ao transicionar para preparing."""
        self.order.transition_status(Order.STATUS_CONFIRMED, actor="test")
        self.assertIsNone(self.order.preparing_at)
        self.order.transition_status(Order.STATUS_PREPARING, actor="test")
        self.order.refresh_from_db()
        self.assertIsNotNone(self.order.preparing_at)

    def test_ready_at_is_set_on_transition(self) -> None:
        """ready_at é definido ao transicionar para ready."""
        self.order.transition_status(Order.STATUS_CONFIRMED, actor="test")
        self.order.transition_status(Order.STATUS_PREPARING, actor="test")
        self.assertIsNone(self.order.ready_at)
        self.order.transition_status(Order.STATUS_READY, actor="test")
        self.order.refresh_from_db()
        self.assertIsNotNone(self.order.ready_at)

    def test_dispatched_at_is_set_on_transition(self) -> None:
        """dispatched_at é definido ao transicionar para dispatched."""
        self.order.transition_status(Order.STATUS_CONFIRMED, actor="test")
        self.order.transition_status(Order.STATUS_PREPARING, actor="test")
        self.order.transition_status(Order.STATUS_READY, actor="test")
        self.assertIsNone(self.order.dispatched_at)
        self.order.transition_status(Order.STATUS_DISPATCHED, actor="test")
        self.order.refresh_from_db()
        self.assertIsNotNone(self.order.dispatched_at)

    def test_delivered_at_is_set_on_transition(self) -> None:
        """delivered_at é definido ao transicionar para delivered."""
        self.order.transition_status(Order.STATUS_CONFIRMED, actor="test")
        self.order.transition_status(Order.STATUS_PREPARING, actor="test")
        self.order.transition_status(Order.STATUS_READY, actor="test")
        self.order.transition_status(Order.STATUS_DISPATCHED, actor="test")
        self.assertIsNone(self.order.delivered_at)
        self.order.transition_status(Order.STATUS_DELIVERED, actor="test")
        self.order.refresh_from_db()
        self.assertIsNotNone(self.order.delivered_at)

    def test_completed_at_is_set_on_transition(self) -> None:
        """completed_at é definido ao transicionar para completed."""
        self.order.transition_status(Order.STATUS_CONFIRMED, actor="test")
        self.order.transition_status(Order.STATUS_PREPARING, actor="test")
        self.order.transition_status(Order.STATUS_READY, actor="test")
        self.assertIsNone(self.order.completed_at)
        self.order.transition_status(Order.STATUS_COMPLETED, actor="test")
        self.order.refresh_from_db()
        self.assertIsNotNone(self.order.completed_at)

    def test_cancelled_at_is_set_on_cancellation(self) -> None:
        """cancelled_at é definido ao cancelar."""
        self.assertIsNone(self.order.cancelled_at)
        self.order.transition_status(Order.STATUS_CANCELLED, actor="test")
        self.order.refresh_from_db()
        self.assertIsNotNone(self.order.cancelled_at)

    def test_timestamp_not_overwritten_on_repeat_transition(self) -> None:
        """Timestamp não é sobrescrito se já existe (edge case)."""
        # Força o timestamp
        original_time = timezone.now() - timedelta(hours=1)
        self.order.confirmed_at = original_time
        self.order.status = Order.STATUS_NEW
        self.order.save()

        # Transiciona novamente
        self.order.transition_status(Order.STATUS_CONFIRMED, actor="test")
        self.order.refresh_from_db()

        # Deve manter o timestamp original
        self.assertEqual(self.order.confirmed_at, original_time)

    def test_timestamps_allow_duration_calculation(self) -> None:
        """Timestamps permitem calcular duração entre estados."""
        # Transiciona normalmente
        self.order.transition_status(Order.STATUS_CONFIRMED, actor="test")
        self.order.transition_status(Order.STATUS_PREPARING, actor="test")
        self.order.transition_status(Order.STATUS_READY, actor="test")

        self.order.refresh_from_db()

        # Verifica que podemos calcular a duração
        prep_time = self.order.ready_at - self.order.preparing_at
        # A duração deve ser >= 0 (quase instantânea no teste)
        self.assertGreaterEqual(prep_time.total_seconds(), 0)


class IFoodChannelFlowTests(TestCase):
    """Testes de fluxo realista para canal iFood."""

    def setUp(self) -> None:
        self.channel = types.SimpleNamespace(
            ref="ifood",
            name="iFood",
        )

    def test_ifood_happy_path_delivery(self) -> None:
        """Fluxo completo de delivery iFood."""
        order = Order.objects.create(
            ref="IFOOD-001",
            channel_ref=self.channel.ref,
            status=Order.STATUS_NEW,
            total_q=5000,
            external_ref="ifood-abc123",
        )

        # Pedido chega do iFood → auto-confirm
        order.transition_status(Order.STATUS_CONFIRMED, actor="ifood-webhook")
        self.assertEqual(order.status, Order.STATUS_CONFIRMED)

        # Cozinha aceita
        order.transition_status(Order.STATUS_PREPARING, actor="kitchen")
        self.assertEqual(order.status, Order.STATUS_PREPARING)

        # Pronto
        order.transition_status(Order.STATUS_READY, actor="kitchen")
        self.assertEqual(order.status, Order.STATUS_READY)

        # Motoboy pegou
        order.transition_status(Order.STATUS_DISPATCHED, actor="motoboy")
        self.assertEqual(order.status, Order.STATUS_DISPATCHED)

        # Entregue
        order.transition_status(Order.STATUS_DELIVERED, actor="motoboy")
        self.assertEqual(order.status, Order.STATUS_DELIVERED)

        # Finalizado
        order.transition_status(Order.STATUS_COMPLETED, actor="system")
        self.assertEqual(order.status, Order.STATUS_COMPLETED)

        # Verifica todos os timestamps
        order.refresh_from_db()
        self.assertIsNotNone(order.confirmed_at)
        self.assertIsNotNone(order.preparing_at)
        self.assertIsNotNone(order.ready_at)
        self.assertIsNotNone(order.dispatched_at)
        self.assertIsNotNone(order.delivered_at)
        self.assertIsNotNone(order.completed_at)

    def test_ifood_cancellation_from_new(self) -> None:
        """Cancelamento antes de aceitar."""
        order = Order.objects.create(
            ref="IFOOD-002",
            channel_ref=self.channel.ref,
            status=Order.STATUS_NEW,
            total_q=3000,
        )

        order.transition_status(Order.STATUS_CANCELLED, actor="customer")
        self.assertEqual(order.status, Order.STATUS_CANCELLED)
        self.assertIsNotNone(order.cancelled_at)

    def test_ifood_cancellation_during_prep(self) -> None:
        """Cancelamento durante preparo."""
        order = Order.objects.create(
            ref="IFOOD-003",
            channel_ref=self.channel.ref,
            status=Order.STATUS_NEW,
            total_q=4500,
        )

        order.transition_status(Order.STATUS_CONFIRMED, actor="ifood-webhook")
        order.transition_status(Order.STATUS_PREPARING, actor="kitchen")
        order.transition_status(Order.STATUS_CANCELLED, actor="ifood-webhook")

        self.assertEqual(order.status, Order.STATUS_CANCELLED)
        self.assertIsNotNone(order.cancelled_at)

    def test_ifood_return_after_delivery(self) -> None:
        """Devolução após entrega — returned é terminal."""
        order = Order.objects.create(
            ref="IFOOD-004",
            channel_ref=self.channel.ref,
            status=Order.STATUS_NEW,
            total_q=8000,
        )

        # Fluxo até entrega
        order.transition_status(Order.STATUS_CONFIRMED, actor="ifood-webhook")
        order.transition_status(Order.STATUS_PREPARING, actor="kitchen")
        order.transition_status(Order.STATUS_READY, actor="kitchen")
        order.transition_status(Order.STATUS_DISPATCHED, actor="motoboy")
        order.transition_status(Order.STATUS_DELIVERED, actor="motoboy")

        # Devolução
        order.transition_status(Order.STATUS_RETURNED, actor="customer-support")
        self.assertEqual(order.status, Order.STATUS_RETURNED)

        # returned é terminal — não pode transicionar para completed
        with self.assertRaises(InvalidTransition):
            order.transition_status(Order.STATUS_COMPLETED, actor="finance")

    def test_ifood_cannot_skip_states(self) -> None:
        """iFood não pode pular estados intermediários."""
        order = Order.objects.create(
            ref="IFOOD-005",
            channel_ref=self.channel.ref,
            status=Order.STATUS_NEW,
            total_q=2500,
        )

        # Não pode ir direto para ready
        with self.assertRaises(InvalidTransition):
            order.transition_status(Order.STATUS_READY, actor="test")

        # Não pode ir direto para dispatched
        with self.assertRaises(InvalidTransition):
            order.transition_status(Order.STATUS_DISPATCHED, actor="test")


class EcommerceChannelFlowTests(TestCase):
    """Testes de fluxo realista para canal E-commerce."""

    def setUp(self) -> None:
        self.channel = types.SimpleNamespace(
            ref="ecommerce",
            name="Loja Virtual",
        )

    def test_ecommerce_delivery_flow(self) -> None:
        """E-commerce com entrega."""
        order = Order.objects.create(
            ref="ECOM-001",
            channel_ref=self.channel.ref,
            status=Order.STATUS_NEW,
            total_q=15000,
        )

        # Cliente finaliza compra → pagamento OK → confirmed
        order.transition_status(Order.STATUS_CONFIRMED, actor="payment-webhook")
        order.transition_status(Order.STATUS_PREPARING, actor="warehouse")
        order.transition_status(Order.STATUS_READY, actor="warehouse")
        order.transition_status(Order.STATUS_DISPATCHED, actor="correios")
        order.transition_status(Order.STATUS_DELIVERED, actor="correios")
        order.transition_status(Order.STATUS_COMPLETED, actor="system")

        self.assertEqual(order.status, Order.STATUS_COMPLETED)

    def test_ecommerce_pickup_flow(self) -> None:
        """E-commerce com retirada na loja (sem dispatched)."""
        order = Order.objects.create(
            ref="ECOM-002",
            channel_ref=self.channel.ref,
            status=Order.STATUS_NEW,
            total_q=8000,
        )

        order.transition_status(Order.STATUS_CONFIRMED, actor="payment-webhook")
        order.transition_status(Order.STATUS_PREPARING, actor="store")
        order.transition_status(Order.STATUS_READY, actor="store")
        # Cliente retira → direto para completed (sem dispatched)
        order.transition_status(Order.STATUS_COMPLETED, actor="store-clerk")

        self.assertEqual(order.status, Order.STATUS_COMPLETED)
        self.assertIsNone(order.dispatched_at)

    def test_ecommerce_payment_timeout_cancellation(self) -> None:
        """Cancelamento por timeout de pagamento."""
        order = Order.objects.create(
            ref="ECOM-003",
            channel_ref=self.channel.ref,
            status=Order.STATUS_NEW,
            total_q=12000,
        )

        # Pagamento não confirmado → cancela
        order.transition_status(Order.STATUS_CANCELLED, actor="payment-timeout")
        self.assertEqual(order.status, Order.STATUS_CANCELLED)


class PDVChannelFlowTests(TestCase):
    """Testes de fluxo realista para canal PDV (balcão).

    PDV usa fluxo simplificado: new → confirmed → completed (sem delivery states).
    Lifecycle config é baked no order.snapshot["lifecycle"] no momento do commit
    (via ChannelConfig.flow.transitions no framework). Aqui usamos diretamente.
    """

    _PDV_TRANSITIONS = {
        Order.STATUS_NEW: [Order.STATUS_CONFIRMED, Order.STATUS_CANCELLED],
        Order.STATUS_CONFIRMED: [Order.STATUS_COMPLETED, Order.STATUS_CANCELLED],
        Order.STATUS_COMPLETED: [],
        Order.STATUS_CANCELLED: [],
    }

    def setUp(self) -> None:
        self.channel = types.SimpleNamespace(
            ref="pdv",
            name="Balcão",
        )

    def _mk_order(self, ref, total_q):
        return Order.objects.create(
            ref=ref,
            channel_ref=self.channel.ref,
            status=Order.STATUS_NEW,
            total_q=total_q,
            snapshot={"lifecycle": {"transitions": self._PDV_TRANSITIONS}},
        )

    def test_pdv_quick_sale(self) -> None:
        """Venda rápida no balcão: new → confirmed → completed."""
        order = self._mk_order("PDV-001", 2500)

        order.transition_status(Order.STATUS_CONFIRMED, actor="cashier")
        order.transition_status(Order.STATUS_COMPLETED, actor="cashier")

        self.assertEqual(order.status, Order.STATUS_COMPLETED)
        self.assertIsNotNone(order.confirmed_at)
        self.assertIsNotNone(order.completed_at)

    def test_pdv_cancelled_sale(self) -> None:
        """Venda cancelada no balcão."""
        order = self._mk_order("PDV-002", 1500)

        order.transition_status(Order.STATUS_CANCELLED, actor="cashier")
        self.assertEqual(order.status, Order.STATUS_CANCELLED)

    def test_pdv_cannot_access_delivery_states(self) -> None:
        """PDV não tem acesso a estados de delivery."""
        order = self._mk_order("PDV-003", 3000)
        order.transition_status(Order.STATUS_CONFIRMED, actor="cashier")

        # Não pode ir para preparing — PDV tem fluxo simplificado
        with self.assertRaises(InvalidTransition):
            order.transition_status(Order.STATUS_PREPARING, actor="test")


class OrderEventAuditTests(TestCase):
    """Testes para auditoria de eventos do Order."""

    def setUp(self) -> None:
        self.channel = types.SimpleNamespace(ref="test", name="Test")
        self.order = Order.objects.create(
            ref="AUDIT-001",
            channel_ref=self.channel.ref,
            status=Order.STATUS_NEW,
            total_q=5000,
        )

    def test_transition_creates_status_changed_event(self) -> None:
        """Transição cria evento status_changed."""
        self.order.transition_status(Order.STATUS_CONFIRMED, actor="admin")

        event = OrderEvent.objects.get(order=self.order)
        self.assertEqual(event.type, "status_changed")
        self.assertEqual(event.actor, "admin")
        self.assertEqual(event.payload["old_status"], "new")
        self.assertEqual(event.payload["new_status"], "confirmed")

    def test_multiple_transitions_create_multiple_events(self) -> None:
        """Múltiplas transições criam múltiplos eventos."""
        self.order.transition_status(Order.STATUS_CONFIRMED, actor="admin")
        self.order.transition_status(Order.STATUS_CANCELLED, actor="customer")

        events = OrderEvent.objects.filter(order=self.order).order_by("created_at")
        self.assertEqual(events.count(), 2)

        self.assertEqual(events[0].payload["new_status"], "confirmed")
        self.assertEqual(events[1].payload["new_status"], "cancelled")

    def test_emit_event_creates_custom_event(self) -> None:
        """emit_event cria evento customizado."""
        event = self.order.emit_event(
            event_type="note_added",
            actor="support",
            payload={"note": "Cliente solicitou entrega rápida"},
        )

        self.assertEqual(event.type, "note_added")
        self.assertEqual(event.actor, "support")
        self.assertEqual(event.payload["note"], "Cliente solicitou entrega rápida")

    def test_events_maintain_chronological_order(self) -> None:
        """Eventos mantêm ordem cronológica."""
        self.order.emit_event("event_1", actor="a", payload={})
        self.order.emit_event("event_2", actor="b", payload={})
        self.order.emit_event("event_3", actor="c", payload={})

        events = list(
            OrderEvent.objects.filter(order=self.order).values_list("type", flat=True)
        )
        self.assertEqual(events, ["event_1", "event_2", "event_3"])


class OrderItemTests(TestCase):
    """Testes para OrderItem."""

    def setUp(self) -> None:
        self.channel = types.SimpleNamespace(ref="test", name="Test")
        self.order = Order.objects.create(
            ref="ITEM-001",
            channel_ref=self.channel.ref,
            status=Order.STATUS_NEW,
            total_q=10000,
        )

    def test_create_order_item(self) -> None:
        """Cria item de pedido."""
        item = OrderItem.objects.create(
            order=self.order,
            line_id="L-1",
            sku="CROISSANT",
            name="Croissant Simples",
            qty=Decimal("2"),
            unit_price_q=500,
            line_total_q=1000,
        )

        self.assertEqual(item.sku, "CROISSANT")
        self.assertEqual(item.qty, Decimal("2"))
        self.assertEqual(item.line_total_q, 1000)

    def test_order_items_relationship(self) -> None:
        """Relacionamento order.items funciona."""
        OrderItem.objects.create(
            order=self.order,
            line_id="L-1",
            sku="ITEM1",
            qty=Decimal("1"),
            unit_price_q=1000,
            line_total_q=1000,
        )
        OrderItem.objects.create(
            order=self.order,
            line_id="L-2",
            sku="ITEM2",
            qty=Decimal("2"),
            unit_price_q=500,
            line_total_q=1000,
        )

        self.assertEqual(self.order.items.count(), 2)

    def test_order_item_with_meta(self) -> None:
        """Item com metadados extras."""
        item = OrderItem.objects.create(
            order=self.order,
            line_id="L-1",
            sku="PIZZA",
            name="Pizza Margherita",
            qty=Decimal("1"),
            unit_price_q=4500,
            line_total_q=4500,
            meta={
                "extras": ["queijo extra", "sem cebola"],
                "observations": "Bem assada",
            },
        )

        self.assertEqual(item.meta["extras"], ["queijo extra", "sem cebola"])


class EdgeCaseTests(TestCase):
    """Testes para casos de borda e cenários extremos."""

    def setUp(self) -> None:
        self.channel = types.SimpleNamespace(ref="test", name="Test")

    def test_order_with_zero_total(self) -> None:
        """Order com total zero (promoção 100% off)."""
        order = Order.objects.create(
            ref="EDGE-001",
            channel_ref=self.channel.ref,
            status=Order.STATUS_NEW,
            total_q=0,
        )

        order.transition_status(Order.STATUS_CONFIRMED, actor="promo")
        self.assertEqual(order.status, Order.STATUS_CONFIRMED)

    def test_order_with_large_total(self) -> None:
        """Order com valor muito alto."""
        order = Order.objects.create(
            ref="EDGE-002",
            channel_ref=self.channel.ref,
            status=Order.STATUS_NEW,
            total_q=99999999999,  # ~R$ 999 milhões
        )

        self.assertEqual(order.total_q, 99999999999)

    def test_order_with_long_external_ref(self) -> None:
        """Order com referência externa longa."""
        order = Order.objects.create(
            ref="EDGE-003",
            channel_ref=self.channel.ref,
            status=Order.STATUS_NEW,
            total_q=1000,
            external_ref="x" * 128,  # max length
        )

        self.assertEqual(len(order.external_ref), 128)

    def test_order_with_special_characters_in_handle(self) -> None:
        """Order com caracteres especiais no handle."""
        order = Order.objects.create(
            ref="EDGE-004",
            channel_ref=self.channel.ref,
            status=Order.STATUS_NEW,
            total_q=1000,
            handle_type="mesa",
            handle_ref="Mesa #12 - João & Maria",
        )

        self.assertIn("João & Maria", str(order))

    def test_concurrent_status_transitions(self) -> None:
        """Simula transições quase simultâneas."""
        order = Order.objects.create(
            ref="EDGE-005",
            channel_ref=self.channel.ref,
            status=Order.STATUS_NEW,
            total_q=5000,
        )

        # Primeira transição
        order.transition_status(Order.STATUS_CONFIRMED, actor="user1")

        # Segunda transição do mesmo status (outro processo)
        order2 = Order.objects.get(pk=order.pk)
        order2.transition_status(Order.STATUS_PREPARING, actor="user2")

        # Ambas devem ter funcionado
        order.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_PREPARING)

    def test_empty_channel_config(self) -> None:
        """Canal sem config usa defaults."""
        empty_channel = types.SimpleNamespace(
            ref="empty",
            name="Empty Config",
        )
        order = Order.objects.create(
            ref="EDGE-006",
            channel_ref=empty_channel.ref,
            status=Order.STATUS_NEW,
            total_q=1000,
        )

        # Deve usar DEFAULT_TRANSITIONS
        self.assertTrue(order.can_transition_to(Order.STATUS_CONFIRMED))
        self.assertTrue(order.can_transition_to(Order.STATUS_CANCELLED))

    def test_empty_channel_config_with_get_transitions(self) -> None:
        """Canal com config vazio usa defaults (config={} é o default)."""
        empty_config_channel = types.SimpleNamespace(
            ref="empty_config",
            name="Empty Config",
        )

        order = Order.objects.create(
            ref="EDGE-007",
            channel_ref=empty_config_channel.ref,
            status=Order.STATUS_NEW,
            total_q=1000,
        )

        # Deve usar DEFAULT_TRANSITIONS sem erro
        transitions = order.get_transitions()
        self.assertIsInstance(transitions, dict)
        # Mesmo com config vazio, pode transicionar para confirmed/cancelled
        self.assertTrue(order.can_transition_to(Order.STATUS_CONFIRMED))
        self.assertTrue(order.can_transition_to(Order.STATUS_CANCELLED))


class SessionToOrderFlowTests(TestCase):
    """Testes de fluxo Session → Order."""

    def setUp(self) -> None:
        self.channel = types.SimpleNamespace(ref="flow", name="Flow Test")

    def test_session_items_preserved_in_order_snapshot(self) -> None:
        """Items da Session são preservados no snapshot do Order."""
        session = Session.objects.create(
            session_key="SESS-001",
            channel_ref=self.channel.ref,
            items=[
                {"line_id": "L-1", "sku": "A", "qty": 2, "unit_price_q": 1000},
                {"line_id": "L-2", "sku": "B", "qty": 1, "unit_price_q": 500},
            ],
        )

        order = Order.objects.create(
            ref="FLOW-001",
            channel_ref=self.channel.ref,
            session_key=session.session_key,
            status=Order.STATUS_NEW,
            total_q=2500,
            snapshot={"items": session.items},
        )

        self.assertEqual(len(order.snapshot["items"]), 2)
        self.assertEqual(order.snapshot["items"][0]["sku"], "A")

    def test_session_handle_copied_to_order(self) -> None:
        """Handle da Session é copiado para Order."""
        session = Session.objects.create(
            session_key="SESS-002",
            channel_ref=self.channel.ref,
            handle_type="comanda",
            handle_ref="42",
        )

        order = Order.objects.create(
            ref="FLOW-002",
            channel_ref=self.channel.ref,
            session_key=session.session_key,
            handle_type=session.handle_type,
            handle_ref=session.handle_ref,
            status=Order.STATUS_NEW,
            total_q=1000,
        )

        self.assertEqual(order.handle_type, "comanda")
        self.assertEqual(order.handle_ref, "42")
        self.assertIn("Comanda: 42", str(order))


class OrderSaveIntegrityTests(TestCase):
    """WP-H1: Testes de integridade garantida pelo save()."""

    def setUp(self) -> None:
        self.channel = types.SimpleNamespace(ref="h1-test", name="H1 Test")
        self.order = Order.objects.create(
            ref="H1-001",
            channel_ref=self.channel.ref,
            status=Order.STATUS_NEW,
            total_q=5000,
        )

    def test_direct_save_status_change_creates_event(self) -> None:
        """Mudança de status via save() direto cria OrderEvent."""
        self.order.status = Order.STATUS_CONFIRMED
        self.order.save()

        event = OrderEvent.objects.get(order=self.order)
        self.assertEqual(event.type, "status_changed")
        self.assertEqual(event.payload["old_status"], "new")
        self.assertEqual(event.payload["new_status"], "confirmed")

    def test_direct_save_status_change_sets_timestamp(self) -> None:
        """Mudança de status via save() direto seta timestamp mecânico."""
        self.assertIsNone(self.order.confirmed_at)
        self.order.status = Order.STATUS_CONFIRMED
        self.order.save()

        self.order.refresh_from_db()
        self.assertIsNotNone(self.order.confirmed_at)

    def test_direct_save_status_change_sends_signal(self) -> None:
        """Mudança de status via save() direto emite signal order_changed."""
        from shopman.orderman.signals import order_changed

        received = []

        def handler(sender, order, event_type, actor, **kwargs):
            received.append({"order": order, "event_type": event_type, "actor": actor})

        order_changed.connect(handler)
        try:
            self.order.status = Order.STATUS_CONFIRMED
            self.order.save()

            self.assertEqual(len(received), 1)
            self.assertEqual(received[0]["event_type"], "status_changed")
            self.assertEqual(received[0]["order"].pk, self.order.pk)
        finally:
            order_changed.disconnect(handler)

    def test_direct_save_status_change_actor_is_direct(self) -> None:
        """Mudança de status via save() direto usa actor 'direct'."""
        self.order.status = Order.STATUS_CONFIRMED
        self.order.save()

        event = OrderEvent.objects.get(order=self.order)
        self.assertEqual(event.actor, "direct")

    def test_transition_status_actor_is_preserved(self) -> None:
        """transition_status() preserva o actor informado."""
        self.order.transition_status(Order.STATUS_CONFIRMED, actor="admin-panel")

        event = OrderEvent.objects.get(order=self.order)
        self.assertEqual(event.actor, "admin-panel")

    def test_save_without_status_change_no_side_effects(self) -> None:
        """save() sem mudança de status não cria evento nem emite signal."""
        from shopman.orderman.signals import order_changed

        received = []

        def handler(sender, **kwargs):
            received.append(True)

        order_changed.connect(handler)
        try:
            self.order.total_q = 9999
            self.order.save()

            self.assertEqual(OrderEvent.objects.filter(order=self.order).count(), 0)
            self.assertEqual(len(received), 0)
        finally:
            order_changed.disconnect(handler)

    def test_invalid_transition_via_direct_save_raises(self) -> None:
        """Transição inválida via save() direto levanta InvalidTransition."""
        self.order.status = Order.STATUS_READY  # new → ready não é permitido
        with self.assertRaises(InvalidTransition):
            self.order.save()


class DispatchedDeliveryGuardTests(TestCase):
    """WP-ST2: Guard — dispatched is exclusive to delivery orders."""

    def setUp(self) -> None:
        self.channel = types.SimpleNamespace(ref="guard-test", name="Guard Test")

    def test_pickup_order_cannot_reach_dispatched(self) -> None:
        """Pickup order tentando ready→dispatched levanta InvalidTransition."""
        order = Order.objects.create(
            ref="GUARD-001",
            channel_ref=self.channel.ref,
            status=Order.STATUS_NEW,
            total_q=1000,
            data={"fulfillment_type": "pickup"},
        )
        order.transition_status(Order.STATUS_CONFIRMED, actor="test")
        order.transition_status(Order.STATUS_PREPARING, actor="test")
        order.transition_status(Order.STATUS_READY, actor="test")

        with self.assertRaises(InvalidTransition) as ctx:
            order.transition_status(Order.STATUS_DISPATCHED, actor="test")

        self.assertEqual(ctx.exception.code, "dispatched_requires_delivery")

    def test_delivery_order_can_reach_dispatched(self) -> None:
        """Delivery order pode transicionar ready→dispatched normalmente."""
        order = Order.objects.create(
            ref="GUARD-002",
            channel_ref=self.channel.ref,
            status=Order.STATUS_NEW,
            total_q=1000,
            data={"fulfillment_type": "delivery"},
        )
        order.transition_status(Order.STATUS_CONFIRMED, actor="test")
        order.transition_status(Order.STATUS_PREPARING, actor="test")
        order.transition_status(Order.STATUS_READY, actor="test")
        order.transition_status(Order.STATUS_DISPATCHED, actor="test")

        self.assertEqual(order.status, Order.STATUS_DISPATCHED)

    def test_order_without_fulfillment_type_can_reach_dispatched(self) -> None:
        """Order sem fulfillment_type (legado) não é bloqueado pelo guard."""
        order = Order.objects.create(
            ref="GUARD-003",
            channel_ref=self.channel.ref,
            status=Order.STATUS_NEW,
            total_q=1000,
            data={},  # sem fulfillment_type
        )
        order.transition_status(Order.STATUS_CONFIRMED, actor="test")
        order.transition_status(Order.STATUS_PREPARING, actor="test")
        order.transition_status(Order.STATUS_READY, actor="test")
        order.transition_status(Order.STATUS_DISPATCHED, actor="test")

        self.assertEqual(order.status, Order.STATUS_DISPATCHED)

    def test_legacy_delivery_method_key_is_accepted(self) -> None:
        """Order com chave legada delivery_method='delivery' pode ir para dispatched."""
        order = Order.objects.create(
            ref="GUARD-004",
            channel_ref=self.channel.ref,
            status=Order.STATUS_NEW,
            total_q=1000,
            data={"delivery_method": "delivery"},
        )
        order.transition_status(Order.STATUS_CONFIRMED, actor="test")
        order.transition_status(Order.STATUS_PREPARING, actor="test")
        order.transition_status(Order.STATUS_READY, actor="test")
        order.transition_status(Order.STATUS_DISPATCHED, actor="test")

        self.assertEqual(order.status, Order.STATUS_DISPATCHED)
