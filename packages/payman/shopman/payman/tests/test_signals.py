"""Tests for Payment signals — verify each signal fires with correct kwargs."""
from __future__ import annotations

from unittest.mock import MagicMock

from django.test import TestCase

from shopman.payman.models import PaymentIntent, PaymentTransaction
from shopman.payman.service import PaymentService
from shopman.payman.signals import (
    payment_authorized,
    payment_cancelled,
    payment_captured,
    payment_failed,
    payment_refunded,
)


class PaymentSignalTests(TestCase):
    def test_payment_authorized_signal(self) -> None:
        handler = MagicMock()
        payment_authorized.connect(handler)
        try:
            intent = PaymentService.create_intent("ORD-SIG-A", 5000, "pix")
            PaymentService.authorize(intent.ref)

            handler.assert_called_once()
            kwargs = handler.call_args[1]
            self.assertEqual(kwargs["order_ref"], "ORD-SIG-A")
            self.assertEqual(kwargs["amount_q"], 5000)
            self.assertEqual(kwargs["method"], "pix")
            self.assertIsInstance(kwargs["intent"], PaymentIntent)
        finally:
            payment_authorized.disconnect(handler)

    def test_payment_captured_signal(self) -> None:
        handler = MagicMock()
        payment_captured.connect(handler)
        try:
            intent = PaymentService.create_intent("ORD-SIG-C", 8000, "card")
            PaymentService.authorize(intent.ref)
            PaymentService.capture(intent.ref, amount_q=8000)

            handler.assert_called_once()
            kwargs = handler.call_args[1]
            self.assertEqual(kwargs["order_ref"], "ORD-SIG-C")
            self.assertEqual(kwargs["amount_q"], 8000)
            self.assertIsInstance(kwargs["transaction"], PaymentTransaction)
        finally:
            payment_captured.disconnect(handler)

    def test_payment_refunded_signal(self) -> None:
        handler = MagicMock()
        payment_refunded.connect(handler)
        try:
            intent = PaymentService.create_intent("ORD-SIG-R", 10000, "pix")
            PaymentService.authorize(intent.ref)
            PaymentService.capture(intent.ref)
            PaymentService.refund(intent.ref, amount_q=4000)

            handler.assert_called_once()
            kwargs = handler.call_args[1]
            self.assertEqual(kwargs["order_ref"], "ORD-SIG-R")
            self.assertEqual(kwargs["amount_q"], 4000)
            self.assertIsInstance(kwargs["transaction"], PaymentTransaction)
        finally:
            payment_refunded.disconnect(handler)

    def test_payment_cancelled_signal(self) -> None:
        handler = MagicMock()
        payment_cancelled.connect(handler)
        try:
            intent = PaymentService.create_intent("ORD-SIG-X", 5000, "pix")
            PaymentService.cancel(intent.ref)

            handler.assert_called_once()
            kwargs = handler.call_args[1]
            self.assertEqual(kwargs["order_ref"], "ORD-SIG-X")
            self.assertIsInstance(kwargs["intent"], PaymentIntent)
        finally:
            payment_cancelled.disconnect(handler)

    def test_payment_failed_signal(self) -> None:
        handler = MagicMock()
        payment_failed.connect(handler)
        try:
            intent = PaymentService.create_intent("ORD-SIG-F", 5000, "card")
            PaymentService.fail(intent.ref, error_code="declined", message="Insufficient funds")

            handler.assert_called_once()
            kwargs = handler.call_args[1]
            self.assertEqual(kwargs["order_ref"], "ORD-SIG-F")
            self.assertEqual(kwargs["error_code"], "declined")
            self.assertEqual(kwargs["message"], "Insufficient funds")
        finally:
            payment_failed.disconnect(handler)

    def test_multiple_refund_signals(self) -> None:
        """Each partial refund emits its own signal."""
        handler = MagicMock()
        payment_refunded.connect(handler)
        try:
            intent = PaymentService.create_intent("ORD-SIG-MR", 10000, "pix")
            PaymentService.authorize(intent.ref)
            PaymentService.capture(intent.ref)

            PaymentService.refund(intent.ref, amount_q=3000)
            PaymentService.refund(intent.ref, amount_q=7000)

            self.assertEqual(handler.call_count, 2)
            amounts = [call[1]["amount_q"] for call in handler.call_args_list]
            self.assertEqual(sorted(amounts), [3000, 7000])
        finally:
            payment_refunded.disconnect(handler)
