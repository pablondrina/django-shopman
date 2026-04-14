"""
Invariant: order.data["payment"] must NOT contain a "status" key.

Payment status is canonical in Payman (PaymentService). Storing it in
order.data creates stale duplicates and was the root cause of C14.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def _make_order(**overrides):
    order = MagicMock()
    order.ref = overrides.get("ref", "ORD-INV-001")
    order.total_q = overrides.get("total_q", 5000)
    order.status = overrides.get("status", "new")
    order.data = overrides.get("data", {})
    order.snapshot = overrides.get("snapshot", {"items": [], "data": {}})
    channel = MagicMock()
    channel.ref = "web"
    order.channel_ref = channel.ref
    return order


class TestPaymentDataInvariant:
    """order.data['payment'] must never contain 'status'."""

    def test_payment_service_does_not_write_status(self):
        """After payment.initiate, order.data['payment'] has no 'status' key."""
        from shopman.shop.adapters.payment_types import PaymentIntent
        from shopman.shop.services import payment as payment_svc

        order = _make_order(data={"payment": {"method": "pix"}})

        mock_intent = PaymentIntent(
            intent_ref="INT-001",
            amount_q=5000,
            currency="BRL",
            status="pending",
            client_secret='{"qrcode": "data"}',
        )
        with patch("shopman.shop.services.payment.get_adapter") as mock_get:
            mock_adapter = MagicMock()
            mock_adapter.create_intent.return_value = mock_intent
            mock_get.return_value = mock_adapter

            payment_svc.initiate(order)

        payment_data = order.data.get("payment", {})
        assert "status" not in payment_data, (
            f"order.data['payment'] must not contain 'status', found: {payment_data}"
        )

    def test_order_data_payment_contract(self):
        """Allowed keys in order.data['payment'] are strictly defined."""
        allowed_keys = {
            "intent_ref", "amount_q", "method",
            "qr_code", "copy_paste", "client_secret", "expires_at",
            "error", "transaction_id",
        }
        from shopman.shop.adapters.payment_types import PaymentIntent
        from shopman.shop.services import payment as payment_svc

        order = _make_order(data={"payment": {"method": "pix"}})

        mock_intent = PaymentIntent(
            intent_ref="INT-002",
            amount_q=5000,
            currency="BRL",
            status="pending",
            client_secret='{"qrcode": "data", "brcode": "pix-code"}',
        )
        with patch("shopman.shop.services.payment.get_adapter") as mock_get:
            mock_adapter = MagicMock()
            mock_adapter.create_intent.return_value = mock_intent
            mock_get.return_value = mock_adapter

            payment_svc.initiate(order)

        payment_data = order.data.get("payment", {})
        extra_keys = set(payment_data.keys()) - allowed_keys
        assert not extra_keys, (
            f"order.data['payment'] has unexpected keys: {extra_keys}"
        )
