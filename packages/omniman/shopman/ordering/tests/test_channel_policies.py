"""
Testes de Políticas de Canal — Garante que cada canal respeita suas políticas
e que operadores recebem mensagens elegantes quando tentam ações proibidas.

CONTEXTO IMPORTANTE:
- Cada canal tem políticas próprias (edit_policy, pricing_policy)
- iFood: Pedidos chegam prontos, NÃO podem ser editados (edit_policy=locked)
- PDV: Pedidos são criados localmente, PODEM ser editados (edit_policy=open)
- O operador deve receber mensagens claras e amigáveis, nunca erros técnicos
"""

from __future__ import annotations

from decimal import Decimal
from django.test import TestCase

from shopman.ordering.models import Channel, Session, Order
from shopman.ordering.services import ModifyService
from shopman.ordering.exceptions import SessionError


class IFoodPolicyTests(TestCase):
    """
    Testes de política do canal iFood.

    O iFood envia pedidos prontos via webhook. Esses pedidos:
    - Chegam com itens, preços e totais definidos pela plataforma
    - NÃO podem ser alterados pelo operador local
    - Devem exibir mensagem elegante se operador tentar editar
    """

    def setUp(self) -> None:
        self.channel = Channel.objects.create(
            ref="ifood",
            name="iFood",
            pricing_policy="external",
            edit_policy="locked",  # Política: NÃO EDITÁVEL
            config={
                "order_flow": {
                    "transitions": {
                        "new": ["confirmed", "cancelled"],
                        "confirmed": ["processing", "cancelled"],
                        "processing": ["ready", "cancelled"],
                        "ready": ["dispatched"],
                        "dispatched": ["delivered"],
                        "delivered": ["completed"],
                    },
                },
                "source": "ifood",
            },
        )

    def test_ifood_session_cannot_be_edited(self) -> None:
        """Operador não pode editar sessão do iFood (mensagem elegante)."""
        # Simula sessão que chegou do iFood
        session = Session.objects.create(
            session_key="ifood_abc123",
            channel=self.channel,
            handle_type="ifood_order",
            handle_ref="abc123",
            pricing_policy="external",
            edit_policy="locked",
            items=[
                {
                    "line_id": "L-001",
                    "sku": "PIZZA-G",
                    "name": "Pizza Grande",
                    "qty": Decimal("1"),
                    "unit_price_q": 4500,
                }
            ],
        )

        # Operador tenta adicionar item
        with self.assertRaises(SessionError) as ctx:
            ModifyService.modify_session(
                session_key=session.session_key,
                channel_ref=self.channel.ref,
                ops=[{"op": "add_line", "sku": "REFRI", "qty": 1, "unit_price_q": 500}],
            )

        # Verifica código do erro (para tratamento programático)
        self.assertEqual(ctx.exception.code, "locked")

        # Verifica mensagem elegante para o operador
        self.assertIn("iFood", ctx.exception.message)
        self.assertIn("não podem ser editados", ctx.exception.message)
        self.assertIn("plataforma externa", ctx.exception.message)

        # Verifica que contexto contém informações úteis
        self.assertEqual(ctx.exception.context["channel"], "iFood")
        self.assertEqual(ctx.exception.context["edit_policy"], "locked")

    def test_ifood_session_cannot_remove_items(self) -> None:
        """Operador não pode remover itens do iFood."""
        session = Session.objects.create(
            session_key="ifood_def456",
            channel=self.channel,
            edit_policy="locked",
            items=[
                {
                    "line_id": "L-001",
                    "sku": "HAMBURGUER",
                    "name": "X-Tudo",
                    "qty": Decimal("2"),
                    "unit_price_q": 2500,
                }
            ],
        )

        with self.assertRaises(SessionError) as ctx:
            ModifyService.modify_session(
                session_key=session.session_key,
                channel_ref=self.channel.ref,
                ops=[{"op": "remove_line", "line_id": "L-001"}],
            )

        self.assertEqual(ctx.exception.code, "locked")
        # Mensagem deve explicar claramente porque não pode editar
        self.assertIn("não podem ser editados", ctx.exception.message)

    def test_ifood_session_cannot_change_quantities(self) -> None:
        """Operador não pode alterar quantidades do iFood."""
        session = Session.objects.create(
            session_key="ifood_ghi789",
            channel=self.channel,
            edit_policy="locked",
            items=[
                {
                    "line_id": "L-001",
                    "sku": "SUSHI",
                    "name": "Combinado 30 peças",
                    "qty": Decimal("1"),
                    "unit_price_q": 8900,
                }
            ],
        )

        with self.assertRaises(SessionError) as ctx:
            ModifyService.modify_session(
                session_key=session.session_key,
                channel_ref=self.channel.ref,
                ops=[{"op": "set_qty", "line_id": "L-001", "qty": 2}],
            )

        self.assertEqual(ctx.exception.code, "locked")

    def test_ifood_order_can_transition_status(self) -> None:
        """Mesmo bloqueado para edição, iFood pode transicionar status."""
        order = Order.objects.create(
            ref="IFOOD-POLICY-001",
            channel=self.channel,
            status=Order.STATUS_NEW,
            total_q=4500,
            external_ref="ifood-xyz",
        )

        # Status pode mudar normalmente
        order.transition_status(Order.STATUS_CONFIRMED, actor="webhook")
        self.assertEqual(order.status, Order.STATUS_CONFIRMED)

        order.transition_status(Order.STATUS_PROCESSING, actor="kitchen")
        self.assertEqual(order.status, Order.STATUS_PROCESSING)


class PDVPolicyTests(TestCase):
    """
    Testes de política do canal PDV.

    PDV é o ponto de venda local. Pedidos:
    - São criados pelo próprio operador
    - PODEM ser editados (adicionar/remover itens)
    - Usam preços internos do catálogo
    """

    def setUp(self) -> None:
        self.channel = Channel.objects.create(
            ref="pdv",
            name="Balcão",
            pricing_policy="internal",
            edit_policy="open",  # Política: EDITÁVEL
            config={
                "order_flow": {
                    "transitions": {
                        "new": ["confirmed", "cancelled"],
                        "confirmed": ["processing", "cancelled"],
                        "processing": ["ready", "completed", "cancelled"],
                        "ready": ["completed"],
                    },
                },
            },
        )

    def test_pdv_session_can_be_edited(self) -> None:
        """Operador pode editar sessão do PDV normalmente."""
        session = Session.objects.create(
            session_key="pdv_001",
            channel=self.channel,
            edit_policy="open",
            items=[
                {
                    "line_id": "L-001",
                    "sku": "CAFE",
                    "name": "Café Expresso",
                    "qty": Decimal("1"),
                    "unit_price_q": 500,
                }
            ],
        )

        # Operador pode adicionar item
        ModifyService.modify_session(
            session_key=session.session_key,
            channel_ref=self.channel.ref,
            ops=[
                {
                    "op": "add_line",
                    "sku": "CROISSANT",
                    "qty": 1,
                    "unit_price_q": 800,
                    "name": "Croissant",
                }
            ],
        )

        session.refresh_from_db()
        self.assertEqual(len(session.items), 2)

    def test_pdv_session_can_remove_items(self) -> None:
        """Operador pode remover itens do PDV."""
        session = Session.objects.create(
            session_key="pdv_002",
            channel=self.channel,
            edit_policy="open",
            items=[
                {
                    "line_id": "L-001",
                    "sku": "SUCO",
                    "name": "Suco Natural",
                    "qty": Decimal("1"),
                    "unit_price_q": 700,
                },
                {
                    "line_id": "L-002",
                    "sku": "TORTA",
                    "name": "Torta de Limão",
                    "qty": Decimal("1"),
                    "unit_price_q": 1200,
                },
            ],
        )

        # Operador pode remover item
        ModifyService.modify_session(
            session_key=session.session_key,
            channel_ref=self.channel.ref,
            ops=[{"op": "remove_line", "line_id": "L-002"}],
        )

        session.refresh_from_db()
        self.assertEqual(len(session.items), 1)
        self.assertEqual(session.items[0]["sku"], "SUCO")

    def test_pdv_session_can_update_quantities(self) -> None:
        """Operador pode alterar quantidades no PDV."""
        session = Session.objects.create(
            session_key="pdv_003",
            channel=self.channel,
            edit_policy="open",
            items=[
                {
                    "line_id": "L-001",
                    "sku": "PAO",
                    "name": "Pão Francês",
                    "qty": Decimal("5"),
                    "unit_price_q": 50,
                }
            ],
        )

        # Cliente quer mais pães (usa set_qty, a operação correta)
        ModifyService.modify_session(
            session_key=session.session_key,
            channel_ref=self.channel.ref,
            ops=[{"op": "set_qty", "line_id": "L-001", "qty": 10}],
        )

        session.refresh_from_db()
        self.assertEqual(session.items[0]["qty"], Decimal("10"))


class SessionStateErrorTests(TestCase):
    """
    Testes de erros de estado da sessão.

    Independente do canal, sessões finalizadas ou abandonadas
    NÃO podem ser editadas. Mensagens devem ser claras.
    """

    def setUp(self) -> None:
        self.channel = Channel.objects.create(
            ref="test",
            name="Teste",
            edit_policy="open",
        )

    def test_committed_session_cannot_be_edited(self) -> None:
        """Sessão já finalizada não pode ser editada (mensagem clara)."""
        session = Session.objects.create(
            session_key="committed_001",
            channel=self.channel,
            state="committed",  # Já foi fechada!
            items=[],
        )

        with self.assertRaises(SessionError) as ctx:
            ModifyService.modify_session(
                session_key=session.session_key,
                channel_ref=self.channel.ref,
                ops=[{"op": "add_line", "sku": "X", "qty": 1, "unit_price_q": 100}],
            )

        self.assertEqual(ctx.exception.code, "already_committed")
        self.assertIn("finalizada", ctx.exception.message)
        self.assertIn("não pode mais ser alterada", ctx.exception.message)

    def test_abandoned_session_cannot_be_edited(self) -> None:
        """Sessão abandonada não pode ser editada (mensagem clara)."""
        session = Session.objects.create(
            session_key="abandoned_001",
            channel=self.channel,
            state="abandoned",  # Foi abandonada!
            items=[],
        )

        with self.assertRaises(SessionError) as ctx:
            ModifyService.modify_session(
                session_key=session.session_key,
                channel_ref=self.channel.ref,
                ops=[{"op": "add_line", "sku": "X", "qty": 1, "unit_price_q": 100}],
            )

        self.assertEqual(ctx.exception.code, "already_abandoned")
        self.assertIn("abandonada", ctx.exception.message)
        self.assertIn("não pode mais ser alterada", ctx.exception.message)


class ErrorMessageQualityTests(TestCase):
    """
    Testes de qualidade das mensagens de erro.

    Todas as mensagens de erro devem:
    1. Ser em português claro
    2. Explicar O QUE aconteceu
    3. Explicar POR QUE não é permitido
    4. Quando possível, sugerir alternativas
    """

    def setUp(self) -> None:
        self.ifood_channel = Channel.objects.create(
            ref="ifood",
            name="iFood",
            edit_policy="locked",
        )

    def test_error_messages_are_in_portuguese(self) -> None:
        """Mensagens de erro são em português."""
        session = Session.objects.create(
            session_key="pt_001",
            channel=self.ifood_channel,
            edit_policy="locked",
            items=[],
        )

        with self.assertRaises(SessionError) as ctx:
            ModifyService.modify_session(
                session_key=session.session_key,
                channel_ref=self.ifood_channel.ref,
                ops=[{"op": "add_line", "sku": "X", "qty": 1, "unit_price_q": 100}],
            )

        # Não deve ter termos técnicos em inglês na mensagem
        msg = ctx.exception.message.lower()
        self.assertNotIn("locked", msg)
        self.assertNotIn("policy", msg)
        self.assertNotIn("session", msg)
        self.assertNotIn("error", msg)

    def test_error_messages_include_channel_name(self) -> None:
        """Mensagens incluem nome do canal para contexto."""
        session = Session.objects.create(
            session_key="ctx_001",
            channel=self.ifood_channel,
            edit_policy="locked",
            items=[],
        )

        with self.assertRaises(SessionError) as ctx:
            ModifyService.modify_session(
                session_key=session.session_key,
                channel_ref=self.ifood_channel.ref,
                ops=[{"op": "add_line", "sku": "X", "qty": 1, "unit_price_q": 100}],
            )

        # Deve mencionar o canal pelo nome
        self.assertIn("iFood", ctx.exception.message)

    def test_error_context_provides_debugging_info(self) -> None:
        """Contexto do erro fornece info para debugging."""
        session = Session.objects.create(
            session_key="debug_001",
            channel=self.ifood_channel,
            edit_policy="locked",
            items=[],
        )

        with self.assertRaises(SessionError) as ctx:
            ModifyService.modify_session(
                session_key=session.session_key,
                channel_ref=self.ifood_channel.ref,
                ops=[{"op": "add_line", "sku": "X", "qty": 1, "unit_price_q": 100}],
            )

        # Contexto deve ter informações técnicas para logs/debugging
        self.assertIn("session_key", ctx.exception.context)
        self.assertIn("channel", ctx.exception.context)
        self.assertIn("edit_policy", ctx.exception.context)
