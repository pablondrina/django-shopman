"""
Testes end-to-end do fluxo completo Omniman.

Este módulo testa o fluxo completo desde a criação de uma sessão
até a finalização do order com transições de status.
"""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase

from shopman.omniman.exceptions import CommitError
from shopman.omniman.ids import generate_idempotency_key, generate_session_key
from shopman.omniman.models import Channel, Directive, Order, OrderEvent, Session
from shopman.omniman.services import CommitService, ModifyService


class EndToEndFlowTests(TestCase):
    """Testa o fluxo completo do Omniman."""

    def setUp(self) -> None:
        """Configura ambiente de teste."""
        self.channel = Channel.objects.create(
            ref="shop",
            name="Shop",
        )

    def test_complete_flow_from_session_to_completed_order(self) -> None:
        """
        Testa fluxo completo:
        1. Criar sessão com items
        2. Modificar sessão (adicionar/remover items)
        3. Commit da sessão
        4. Transições de status do order
        5. Verificar eventos de auditoria
        """
        session_key = generate_session_key()

        # 1. Criar sessão
        session = Session.objects.create(
            session_key=session_key,
            channel=self.channel,
            items=[
                {"sku": "SKU001", "qty": 2, "unit_price_q": 1000},
                {"sku": "SKU002", "qty": 1, "unit_price_q": 500},
            ],
        )
        self.assertEqual(session.session_items.count(), 2)
        self.assertEqual(session.rev, 0)

        # 2a. Adicionar item
        ModifyService.modify_session(
            session_key=session_key,
            channel_ref=self.channel.ref,
            ops=[{"op": "add_line", "sku": "SKU003", "qty": 3, "unit_price_q": 300}],
        )
        session.refresh_from_db()
        self.assertEqual(session.session_items.count(), 3)
        self.assertEqual(session.rev, 1)

        # 2b. Remover primeiro item
        first_item = session.items[0]
        ModifyService.modify_session(
            session_key=session_key,
            channel_ref=self.channel.ref,
            ops=[{"op": "remove_line", "line_id": first_item["line_id"]}],
        )
        session.refresh_from_db()
        self.assertEqual(session.session_items.count(), 2)
        self.assertEqual(session.rev, 2)

        # 2c. Alterar quantidade
        remaining_item = session.items[0]
        ModifyService.modify_session(
            session_key=session_key,
            channel_ref=self.channel.ref,
            ops=[{"op": "set_qty", "line_id": remaining_item["line_id"], "qty": 5}],
        )
        session.refresh_from_db()
        self.assertEqual(session.rev, 3)
        updated_item = session.items[0]
        self.assertEqual(updated_item["qty"], Decimal("5"))

        # 3. Commit da sessão
        idempotency_key = generate_idempotency_key()
        result = CommitService.commit(
            session_key=session_key,
            channel_ref=self.channel.ref,
            idempotency_key=idempotency_key,
        )

        self.assertIn("order_ref", result)
        order_ref = result["order_ref"]

        # Verificar que sessão foi commitada
        session.refresh_from_db()
        self.assertEqual(session.state, "committed")
        self.assertEqual(session.commit_token, idempotency_key)

        # Verificar que order foi criado
        order = Order.objects.get(ref=order_ref)
        self.assertEqual(order.channel, self.channel)
        self.assertEqual(order.session_key, session_key)
        self.assertEqual(order.status, Order.STATUS_NEW)
        self.assertEqual(order.items.count(), 2)

        # Verificar snapshot
        self.assertIn("items", order.snapshot)
        self.assertIn("rev", order.snapshot)
        self.assertEqual(order.snapshot["rev"], 3)

        # 3b. Tentar commit novamente com mesma chave (idempotência)
        result2 = CommitService.commit(
            session_key=session_key,
            channel_ref=self.channel.ref,
            idempotency_key=idempotency_key,
        )
        self.assertEqual(result2["order_ref"], order_ref)
        self.assertEqual(Order.objects.count(), 1)  # Não cria duplicado

        # 3c. Tentar commit com nova chave retorna mesmo resultado (idempotência por session)
        # Nota: CommitService usa IdempotencyKey que valida por scope+key
        # Uma vez commitada, a sessão não pode mais ser commitada
        result3 = CommitService.commit(
            session_key=session_key,
            channel_ref=self.channel.ref,
            idempotency_key=generate_idempotency_key(),
        )
        # Retorna o mesmo order_ref devido à idempotência por sessão
        self.assertEqual(result3["order_ref"], order_ref)
        self.assertEqual(Order.objects.count(), 1)

        # 4. Transições de status
        order.transition_status(Order.STATUS_CONFIRMED, actor="test_admin")
        order.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_CONFIRMED)

        order.transition_status(Order.STATUS_PREPARING, actor="test_kitchen")
        order.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_PREPARING)

        order.transition_status(Order.STATUS_READY, actor="test_kitchen")
        order.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_READY)

        order.transition_status(Order.STATUS_COMPLETED, actor="test_cashier")
        order.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_COMPLETED)

        # 5. Verificar eventos de auditoria
        events = list(order.events.all().order_by("created_at"))
        # Filtra apenas eventos de status_changed (ignora outros eventos que possam existir)
        status_events = [e for e in events if e.type == "status_changed"]
        self.assertEqual(len(status_events), 4)

        # Todos devem ter old_status e new_status
        for event in status_events:
            self.assertIn("old_status", event.payload)
            self.assertIn("new_status", event.payload)

        # Verificar transições específicas
        self.assertEqual(status_events[0].payload["old_status"], Order.STATUS_NEW)
        self.assertEqual(status_events[0].payload["new_status"], Order.STATUS_CONFIRMED)
        self.assertEqual(status_events[0].actor, "test_admin")

        self.assertEqual(status_events[-1].payload["old_status"], Order.STATUS_READY)
        self.assertEqual(status_events[-1].payload["new_status"], Order.STATUS_COMPLETED)
        self.assertEqual(status_events[-1].actor, "test_cashier")

    def test_flow_with_pricing_modifiers(self) -> None:
        """Testa fluxo com pricing policy internal (sem preços nos items)."""
        # Canal com pricing interno (requer modifiers registrados)
        internal_channel = Channel.objects.create(
            ref="internal_shop",
            name="Internal Shop",
        )

        session_key = generate_session_key()
        session = Session.objects.create(
            session_key=session_key,
            channel=internal_channel,
            items=[
                {"sku": "SKU001", "qty": 2},  # Sem unit_price_q
            ],
        )

        # Com pricing internal, modifiers devem popular os preços
        # (No teste, sem modifiers registrados, preço será 0)
        ModifyService.modify_session(
            session_key=session_key,
            channel_ref=internal_channel.ref,
            ops=[{"op": "add_line", "sku": "SKU002", "qty": 1}],
        )

        session.refresh_from_db()
        self.assertEqual(session.session_items.count(), 2)

    def test_flow_with_issues_blocks_commit(self) -> None:
        """Testa que issues bloqueantes impedem commit."""
        session_key = generate_session_key()
        session = Session.objects.create(
            session_key=session_key,
            channel=self.channel,
            items=[{"sku": "SKU001", "qty": 1, "unit_price_q": 1000}],
        )

        # Simula issue bloqueante
        session.data = {
            "issues": [
                {
                    "id": "ISS-001",
                    "source": "test",
                    "code": "test.blocking",
                    "blocking": True,
                    "message": "Teste de bloqueio",
                }
            ]
        }
        session.save()

        # Commit deve falhar
        with self.assertRaises(CommitError) as cm:
            CommitService.commit(
                session_key=session_key,
                channel_ref=self.channel.ref,
                idempotency_key=generate_idempotency_key(),
            )
        self.assertEqual(cm.exception.code, "blocking_issues")
