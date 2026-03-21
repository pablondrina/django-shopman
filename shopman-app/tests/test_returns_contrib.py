"""
Tests for contrib/returns module.

Covers:
- ReturnService.initiate_return (total, partial, invalid status, invalid items)
- ReturnService.process_refund (with/without fiscal)
- ReturnHandler (idempotency, stock reversal)
- Order model changes (COMPLETED → RETURNED transition, returned_at timestamp)
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, call

from django.test import TestCase

from shopman.payment.adapters.mock import MockPaymentBackend
from shopman.returns.handlers import ReturnHandler
from shopman.returns.service import ReturnResult, ReturnService
from shopman.stock.adapters.noop import NoopStockBackend
from shopman.ordering.exceptions import InvalidTransition
from shopman.ordering.models import Channel, Directive, Order, OrderEvent, OrderItem


class ReturnServiceTestBase(TestCase):
    """Base class with common fixtures for return tests."""

    def setUp(self) -> None:
        self.channel = Channel.objects.create(
            ref="shop",
            name="Shop",
            config={},
        )
        self.order = Order.objects.create(
            ref="ORD-RET-001",
            channel=self.channel,
            status=Order.Status.NEW,
            total_q=5000,
            data={
                "payment": {"intent_id": "mock_pi_123"},
            },
        )
        # Transicionar para DELIVERED
        self.order.transition_status(Order.Status.CONFIRMED, actor="test")
        self.order.transition_status(Order.Status.PROCESSING, actor="test")
        self.order.transition_status(Order.Status.READY, actor="test")
        self.order.transition_status(Order.Status.DISPATCHED, actor="test")
        self.order.transition_status(Order.Status.DELIVERED, actor="test")

        # Criar items
        OrderItem.objects.create(
            order=self.order,
            line_id="line-1",
            sku="SKU001",
            name="Pão Artesanal",
            qty=Decimal("2"),
            unit_price_q=1500,
            line_total_q=3000,
        )
        OrderItem.objects.create(
            order=self.order,
            line_id="line-2",
            sku="SKU002",
            name="Croissant",
            qty=Decimal("4"),
            unit_price_q=500,
            line_total_q=2000,
        )


class InitiateReturnTotalTests(ReturnServiceTestBase):
    """Tests for total return initiation."""

    def test_initiate_return_total_transitions_to_returned(self) -> None:
        """Devolução total deve transicionar para RETURNED."""
        items = [
            {"line_id": "line-1", "qty": 2},
            {"line_id": "line-2", "qty": 4},
        ]
        result = ReturnService.initiate_return(
            order=self.order, items=items, reason="Produto danificado", actor="operator_1",
        )

        self.assertTrue(result.success)
        self.assertEqual(result.return_type, "total")
        self.assertEqual(result.refund_total_q, 5000)
        self.assertEqual(len(result.items_returned), 2)
        self.assertIsNotNone(result.directive_id)

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.RETURNED)

    def test_initiate_return_total_creates_event(self) -> None:
        """Deve criar OrderEvent type=return_initiated."""
        items = [
            {"line_id": "line-1", "qty": 2},
            {"line_id": "line-2", "qty": 4},
        ]
        ReturnService.initiate_return(
            order=self.order, items=items, reason="Defeito", actor="op",
        )

        event = OrderEvent.objects.filter(
            order=self.order, type="return_initiated",
        ).first()
        self.assertIsNotNone(event)
        self.assertEqual(event.payload["return_type"], "total")
        self.assertEqual(event.payload["refund_total_q"], 5000)

    def test_initiate_return_total_creates_directive(self) -> None:
        """Deve criar Directive com topic return.process."""
        items = [
            {"line_id": "line-1", "qty": 2},
            {"line_id": "line-2", "qty": 4},
        ]
        result = ReturnService.initiate_return(
            order=self.order, items=items, reason="Defeito", actor="op",
        )

        directive = Directive.objects.get(pk=result.directive_id)
        self.assertEqual(directive.topic, "return.process")
        self.assertEqual(directive.payload["order_ref"], "ORD-RET-001")
        self.assertEqual(directive.payload["refund_total_q"], 5000)

    def test_initiate_return_total_stores_in_order_data(self) -> None:
        """Deve armazenar registro de devolução em order.data['returns']."""
        items = [
            {"line_id": "line-1", "qty": 2},
            {"line_id": "line-2", "qty": 4},
        ]
        ReturnService.initiate_return(
            order=self.order, items=items, reason="Defeito", actor="op",
        )

        self.order.refresh_from_db()
        returns = self.order.data.get("returns", [])
        self.assertEqual(len(returns), 1)
        self.assertEqual(returns[0]["type"], "total")
        self.assertFalse(returns[0]["refund_processed"])


class InitiateReturnPartialTests(ReturnServiceTestBase):
    """Tests for partial return initiation."""

    def test_initiate_return_partial_does_not_transition(self) -> None:
        """Devolução parcial NÃO deve transicionar o status."""
        items = [{"line_id": "line-1", "qty": 1}]
        result = ReturnService.initiate_return(
            order=self.order, items=items, reason="Cliente não gostou", actor="op",
        )

        self.assertTrue(result.success)
        self.assertEqual(result.return_type, "partial")
        self.assertEqual(result.refund_total_q, 1500)

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.DELIVERED)

    def test_partial_return_single_item_partial_qty(self) -> None:
        """Devolver qty < total de um item é parcial."""
        items = [{"line_id": "line-2", "qty": 2}]
        result = ReturnService.initiate_return(
            order=self.order, items=items, reason="Parcial", actor="op",
        )

        self.assertTrue(result.success)
        self.assertEqual(result.return_type, "partial")
        self.assertEqual(result.refund_total_q, 1000)


class InitiateReturnValidationTests(ReturnServiceTestBase):
    """Tests for return validation errors."""

    def test_initiate_return_invalid_status_raises(self) -> None:
        """Order em status NEW deve raise InvalidTransition."""
        new_order = Order.objects.create(
            ref="ORD-NEW-001",
            channel=self.channel,
            status=Order.Status.NEW,
            total_q=1000,
        )
        with self.assertRaises(InvalidTransition):
            ReturnService.initiate_return(
                order=new_order,
                items=[{"line_id": "x", "qty": 1}],
                reason="Test",
                actor="op",
            )

    def test_initiate_return_processing_status_raises(self) -> None:
        """Order em PROCESSING deve raise InvalidTransition."""
        order = Order.objects.create(
            ref="ORD-PROC-001",
            channel=self.channel,
            status=Order.Status.NEW,
            total_q=1000,
        )
        order.transition_status(Order.Status.CONFIRMED, actor="test")
        order.transition_status(Order.Status.PROCESSING, actor="test")

        with self.assertRaises(InvalidTransition):
            ReturnService.initiate_return(
                order=order,
                items=[{"line_id": "x", "qty": 1}],
                reason="Test",
                actor="op",
            )

    def test_initiate_return_invalid_line_id(self) -> None:
        """Line_id inexistente deve retornar erro."""
        result = ReturnService.initiate_return(
            order=self.order,
            items=[{"line_id": "nonexistent", "qty": 1}],
            reason="Test",
            actor="op",
        )

        self.assertFalse(result.success)
        self.assertIn("não encontrado", result.error)

    def test_initiate_return_qty_exceeds(self) -> None:
        """Qty maior que o pedido deve retornar erro."""
        result = ReturnService.initiate_return(
            order=self.order,
            items=[{"line_id": "line-1", "qty": 10}],
            reason="Test",
            actor="op",
        )

        self.assertFalse(result.success)
        self.assertIn("excede", result.error)


class InitiateReturnFromCompletedTests(TestCase):
    """Tests for returns from COMPLETED status."""

    def setUp(self) -> None:
        self.channel = Channel.objects.create(ref="pdv", name="PDV", config={})
        self.order = Order.objects.create(
            ref="ORD-COMP-001",
            channel=self.channel,
            status=Order.Status.NEW,
            total_q=2000,
        )
        self.order.transition_status(Order.Status.CONFIRMED, actor="test")
        self.order.transition_status(Order.Status.PROCESSING, actor="test")
        self.order.transition_status(Order.Status.READY, actor="test")
        self.order.transition_status(Order.Status.DISPATCHED, actor="test")
        self.order.transition_status(Order.Status.DELIVERED, actor="test")
        self.order.transition_status(Order.Status.COMPLETED, actor="test")

        OrderItem.objects.create(
            order=self.order,
            line_id="line-1",
            sku="SKU001",
            name="Baguette",
            qty=Decimal("2"),
            unit_price_q=1000,
            line_total_q=2000,
        )

    def test_completed_to_returned_transition_is_valid(self) -> None:
        """COMPLETED → RETURNED deve ser válido após mudança no DEFAULT_TRANSITIONS."""
        self.assertTrue(self.order.can_transition_to(Order.Status.RETURNED))

    def test_initiate_return_from_completed(self) -> None:
        """Deve funcionar a partir de COMPLETED."""
        result = ReturnService.initiate_return(
            order=self.order,
            items=[{"line_id": "line-1", "qty": 2}],
            reason="Defeito",
            actor="op",
        )

        self.assertTrue(result.success)
        self.assertEqual(result.return_type, "total")

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.RETURNED)

    def test_returned_at_timestamp_is_set(self) -> None:
        """returned_at deve ser setado na transição para RETURNED."""
        self.assertIsNone(self.order.returned_at)

        ReturnService.initiate_return(
            order=self.order,
            items=[{"line_id": "line-1", "qty": 2}],
            reason="Defeito",
            actor="op",
        )

        self.order.refresh_from_db()
        self.assertIsNotNone(self.order.returned_at)


class ProcessRefundTests(TestCase):
    """Tests for ReturnService.process_refund."""

    def setUp(self) -> None:
        self.channel = Channel.objects.create(ref="shop", name="Shop", config={})
        self.payment_backend = MockPaymentBackend()
        # Create an intent to refund
        intent = self.payment_backend.create_intent(5000, "BRL")
        self.payment_backend.capture(intent.intent_id)
        self.intent_id = intent.intent_id

        self.order = Order.objects.create(
            ref="ORD-REF-001",
            channel=self.channel,
            status=Order.Status.DELIVERED,
            total_q=5000,
            data={"payment": {"intent_id": self.intent_id}},
        )

    def test_process_refund_success(self) -> None:
        """Deve processar reembolso e criar evento."""
        result = ReturnService.process_refund(
            order=self.order,
            amount_q=5000,
            actor="return.process",
            payment_backend=self.payment_backend,
        )

        self.assertTrue(result["refund"]["success"])
        self.assertIsNotNone(result["refund"]["refund_id"])

        event = OrderEvent.objects.filter(
            order=self.order, type="refund_processed",
        ).first()
        self.assertIsNotNone(event)
        self.assertEqual(event.payload["amount_q"], 5000)

    def test_process_refund_with_fiscal(self) -> None:
        """Deve cancelar fiscal quando nfce_access_key presente."""
        self.order.data["nfce_access_key"] = "41260100000000000100650010000012341000012345"
        self.order.save(update_fields=["data"])

        mock_fiscal = MagicMock()
        mock_fiscal.cancel.return_value = MagicMock(
            success=True, protocol_number="PROT-001",
        )

        result = ReturnService.process_refund(
            order=self.order,
            amount_q=5000,
            actor="return.process",
            payment_backend=self.payment_backend,
            fiscal_backend=mock_fiscal,
        )

        self.assertTrue(result["fiscal"]["success"])
        mock_fiscal.cancel.assert_called_once_with(
            reference="ORD-REF-001",
            reason="Devolução de mercadoria",
        )

        event = OrderEvent.objects.filter(
            order=self.order, type="fiscal_cancelled",
        ).first()
        self.assertIsNotNone(event)

    def test_process_refund_without_fiscal(self) -> None:
        """Sem nfce_access_key, não deve chamar fiscal."""
        mock_fiscal = MagicMock()

        result = ReturnService.process_refund(
            order=self.order,
            amount_q=5000,
            actor="return.process",
            payment_backend=self.payment_backend,
            fiscal_backend=mock_fiscal,
        )

        mock_fiscal.cancel.assert_not_called()
        self.assertIsNone(result["fiscal"])


class ReturnHandlerTests(ReturnServiceTestBase):
    """Tests for ReturnHandler directive handler."""

    def _make_handler(self, stock_backend=None, payment_backend=None, fiscal_backend=None):
        return ReturnHandler(
            stock_backend=stock_backend or NoopStockBackend(),
            payment_backend=payment_backend or MockPaymentBackend(),
            fiscal_backend=fiscal_backend,
        )

    def _make_directive(self, order, items_detail, refund_total_q, return_index=0):
        return Directive.objects.create(
            topic="return.process",
            payload={
                "order_ref": order.ref,
                "items": items_detail,
                "reason": "Test return",
                "refund_total_q": refund_total_q,
                "return_index": return_index,
            },
        )

    def test_handler_processes_return(self) -> None:
        """Handler deve processar devolução completa."""
        # First initiate return to set up order.data
        result = ReturnService.initiate_return(
            order=self.order,
            items=[{"line_id": "line-1", "qty": 2}, {"line_id": "line-2", "qty": 4}],
            reason="Defeito",
            actor="op",
        )
        directive = Directive.objects.get(pk=result.directive_id)

        handler = self._make_handler()
        handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")

        # Check refund_processed flag
        self.order.refresh_from_db()
        returns = self.order.data["returns"]
        self.assertTrue(returns[0]["refund_processed"])

    def test_handler_idempotent(self) -> None:
        """Handler chamado 2x deve processar apenas 1x."""
        result = ReturnService.initiate_return(
            order=self.order,
            items=[{"line_id": "line-1", "qty": 2}, {"line_id": "line-2", "qty": 4}],
            reason="Defeito",
            actor="op",
        )

        handler = self._make_handler()

        # First call
        directive = Directive.objects.get(pk=result.directive_id)
        handler.handle(message=directive, ctx={})
        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")

        # Second call — should be idempotent
        directive2 = Directive.objects.create(
            topic="return.process",
            payload=directive.payload,
        )
        handler.handle(message=directive2, ctx={})
        directive2.refresh_from_db()
        self.assertEqual(directive2.status, "done")

    def test_handler_calls_stock_receive_return(self) -> None:
        """Handler deve chamar receive_return para cada item."""
        mock_stock = MagicMock()

        result = ReturnService.initiate_return(
            order=self.order,
            items=[{"line_id": "line-1", "qty": 2}, {"line_id": "line-2", "qty": 4}],
            reason="Defeito",
            actor="op",
        )
        directive = Directive.objects.get(pk=result.directive_id)

        handler = self._make_handler(stock_backend=mock_stock)
        handler.handle(message=directive, ctx={})

        self.assertEqual(mock_stock.receive_return.call_count, 2)
        mock_stock.receive_return.assert_any_call(
            sku="SKU001",
            quantity=Decimal("2"),
            reference="ORD-RET-001",
            reason="Devolução pedido ORD-RET-001",
        )
        mock_stock.receive_return.assert_any_call(
            sku="SKU002",
            quantity=Decimal("4"),
            reference="ORD-RET-001",
            reason="Devolução pedido ORD-RET-001",
        )

    def test_handler_order_not_found(self) -> None:
        """Handler com order inexistente deve falhar."""
        directive = Directive.objects.create(
            topic="return.process",
            payload={
                "order_ref": "NONEXISTENT",
                "items": [],
                "reason": "Test",
                "refund_total_q": 0,
                "return_index": 0,
            },
        )

        handler = self._make_handler()
        handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "failed")
        self.assertIn("not found", directive.last_error)
