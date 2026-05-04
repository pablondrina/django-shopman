"""PIX confirmation parity for the local mock payment gateway."""

from __future__ import annotations

import base64
import json
from unittest.mock import patch

from django.test import TestCase
from shopman.orderman.exceptions import DirectiveTerminalError
from shopman.orderman.models import Directive, Order
from shopman.payman import PaymentService

from shopman.shop.adapters import payment_mock
from shopman.shop.handlers.mock_pix import MOCK_PIX_CONFIRM, MockPixConfirmHandler


class MockPixConfirmationTests(TestCase):
    def test_mock_pix_intent_does_not_auto_schedule_confirmation_by_default(self) -> None:
        order = Order.objects.create(
            ref="PIX-MOCK-MANUAL",
            channel_ref="web",
            status="confirmed",
            total_q=1500,
            data={"payment": {"method": "pix"}},
        )

        intent = payment_mock.create_intent(
            order_ref=order.ref,
            amount_q=order.total_q,
            method="pix",
        )

        self.assertEqual(PaymentService.get(intent.intent_ref).status, "authorized")
        self.assertFalse(
            Directive.objects.filter(
                topic=MOCK_PIX_CONFIRM,
                payload__order_ref=order.ref,
            ).exists()
        )

    def test_scheduled_mock_pix_does_not_capture_before_available_at(self) -> None:
        order = Order.objects.create(
            ref="PIX-MOCK-SCHEDULED",
            channel_ref="web",
            status="new",
            total_q=1500,
            data={"payment": {"method": "pix"}},
        )

        with self.captureOnCommitCallbacks(execute=True):
            intent = payment_mock.create_intent(
                order_ref=order.ref,
                amount_q=order.total_q,
                method="pix",
                mock_pix_auto_confirm=True,
                mock_pix_confirm_delay_seconds=30,
            )

        directive = Directive.objects.filter(topic=MOCK_PIX_CONFIRM).latest("id")

        self.assertEqual(PaymentService.get(intent.intent_ref).status, "authorized")
        self.assertEqual(directive.status, "queued")
        self.assertEqual(directive.attempts, 0)

    def test_mock_pix_intent_returns_real_png_qr_image(self) -> None:
        order = Order.objects.create(
            ref="PIX-MOCK-QR",
            channel_ref="web",
            status="confirmed",
            total_q=1500,
            data={"payment": {"method": "pix"}},
        )

        intent = payment_mock.create_intent(
            order_ref=order.ref,
            amount_q=order.total_q,
            method="pix",
            mock_pix_auto_confirm=True,
            mock_pix_confirm_delay_seconds=30,
        )

        qr_image = intent.metadata["imagemQrcode"]
        self.assertTrue(qr_image.startswith("data:image/png;base64,"))
        png_bytes = base64.b64decode(qr_image.split(",", 1)[1])
        self.assertEqual(png_bytes[:8], b"\x89PNG\r\n\x1a\n")
        self.assertNotIn("svg+xml", qr_image)

        payload = json.loads(intent.client_secret)
        self.assertEqual(payload["qrcode"], payload["brcode"])
        self.assertEqual(payload["imagemQrcode"], qr_image)

    def test_mock_pix_directive_captures_mock_gateway_intent(self) -> None:
        from shopman.backstage.models import OperatorAlert

        order = Order.objects.create(
            ref="PIX-MOCK-001",
            channel_ref="web",
            status="new",
            total_q=1500,
            data={"payment": {"method": "pix"}},
        )
        alert = OperatorAlert.objects.create(
            type="payment_failed",
            severity="error",
            order_ref=order.ref,
            message=f"Falha ao gerar pagamento PIX do pedido {order.ref}.",
        )
        intent = payment_mock.create_intent(
            order_ref=order.ref,
            amount_q=order.total_q,
            method="pix",
            mock_pix_auto_confirm=True,
            mock_pix_confirm_delay_seconds=0,
        )
        stale_intent = PaymentService.create_intent(
            order_ref=order.ref,
            amount_q=order.total_q,
            method="pix",
        )
        order.data["payment"]["intent_ref"] = intent.intent_ref
        order.save(update_fields=["data", "updated_at"])

        directive = Directive.objects.filter(topic=MOCK_PIX_CONFIRM).latest("id")

        with patch("shopman.shop.lifecycle.dispatch") as mock_dispatch:
            MockPixConfirmHandler().handle(message=directive, ctx={})

        self.assertEqual(PaymentService.get(intent.intent_ref).status, "captured")
        self.assertEqual(PaymentService.get(stale_intent.ref).status, "cancelled")
        order.refresh_from_db()
        self.assertEqual(order.data["payment"]["e2e_id"], directive.payload["e2e_id"])
        alert.refresh_from_db()
        self.assertTrue(alert.acknowledged)
        mock_dispatch.assert_called_once_with(order, "on_paid")

    def test_legacy_mock_pix_directive_without_opt_in_does_not_capture(self) -> None:
        order = Order.objects.create(
            ref="PIX-MOCK-LEGACY",
            channel_ref="web",
            status="confirmed",
            total_q=1500,
            data={"payment": {"method": "pix"}},
        )
        intent = payment_mock.create_intent(
            order_ref=order.ref,
            amount_q=order.total_q,
            method="pix",
        )
        order.data["payment"]["intent_ref"] = intent.intent_ref
        order.save(update_fields=["data", "updated_at"])
        directive = Directive.objects.create(
            topic=MOCK_PIX_CONFIRM,
            payload={
                "order_ref": order.ref,
                "txid": intent.gateway_id,
                "e2e_id": "E2ELEGACY",
                "valor": "15.00",
            },
        )

        with self.assertRaises(DirectiveTerminalError):
            MockPixConfirmHandler().handle(message=directive, ctx={})

        self.assertEqual(PaymentService.get(intent.intent_ref).status, "authorized")
