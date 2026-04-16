"""Unit tests for shopman.shop.projections.payment.

Uses order fixtures from conftest.py. Verifies PaymentProjection and
PaymentStatusProjection shape, PIX/card field population, expiry logic,
and terminal state detection.
"""
from __future__ import annotations

import pytest

from shopman.shop.projections.payment import (
    PaymentProjection,
    PaymentStatusProjection,
    build_payment,
    build_payment_status,
)

pytestmark = pytest.mark.django_db


# ──────────────────────────────────────────────────────────────────────
# PaymentProjection — shape
# ──────────────────────────────────────────────────────────────────────


class TestPaymentProjectionShape:
    def test_returns_payment_projection(self, order_with_payment):
        proj = build_payment(order_with_payment)
        assert isinstance(proj, PaymentProjection)

    def test_is_immutable(self, order_with_payment):
        from dataclasses import FrozenInstanceError

        proj = build_payment(order_with_payment)
        with pytest.raises(FrozenInstanceError):
            proj.method = "card"  # type: ignore[misc]

    def test_order_ref_matches(self, order_with_payment):
        proj = build_payment(order_with_payment)
        assert proj.order_ref == order_with_payment.ref

    def test_total_display_formatted(self, order_with_payment):
        proj = build_payment(order_with_payment)
        assert proj.total_display.startswith("R$ ")
        assert "25,00" in proj.total_display  # 2500q = R$ 25,00


# ──────────────────────────────────────────────────────────────────────
# PIX fields
# ──────────────────────────────────────────────────────────────────────


class TestPaymentProjectionPix:
    def test_method_is_pix(self, order_with_payment):
        proj = build_payment(order_with_payment)
        assert proj.method == "pix"

    def test_pix_copy_paste_populated(self, order_with_payment):
        proj = build_payment(order_with_payment)
        assert proj.pix_copy_paste == "00020126..."

    def test_card_fields_are_none_for_pix(self, order_with_payment):
        proj = build_payment(order_with_payment)
        assert proj.stripe_client_secret is None
        assert proj.stripe_publishable_key is None

    def test_status_url_is_correct(self, order_with_payment):
        proj = build_payment(order_with_payment)
        assert f"/{order_with_payment.ref}/" in proj.status_url
        assert "pagamento" in proj.status_url or "payment" in proj.status_url.lower()


# ──────────────────────────────────────────────────────────────────────
# Card fields
# ──────────────────────────────────────────────────────────────────────


class TestPaymentProjectionCard:
    def test_card_method_fields(self, channel):
        from shopman.orderman.models import Order

        order = Order.objects.create(
            ref="ORD-CARD-001",
            channel_ref=channel.ref,
            status="new",
            total_q=5000,
            handle_type="phone",
            handle_ref="5543000000001",
            data={
                "payment": {
                    "method": "card",
                    "client_secret": "pi_test_secret_123",
                    "status": "pending",
                },
            },
        )
        proj = build_payment(order)
        assert proj.method == "card"
        assert proj.stripe_client_secret == "pi_test_secret_123"
        assert proj.pix_qr_code is None
        assert proj.pix_copy_paste is None


# ──────────────────────────────────────────────────────────────────────
# PaymentStatusProjection
# ──────────────────────────────────────────────────────────────────────


class TestPaymentStatusProjection:
    def test_pending_order_not_terminal(self, order_with_payment):
        proj = build_payment_status(order_with_payment)
        assert isinstance(proj, PaymentStatusProjection)
        assert proj.is_paid is False
        assert proj.is_cancelled is False
        assert proj.is_expired is False
        assert proj.is_terminal is False

    def test_paid_order_is_terminal(self, order_with_payment):
        # Create and capture a PaymentIntent so Payman returns "captured".
        from shopman.payman import PaymentService

        intent = PaymentService.create_intent(
            order_ref=order_with_payment.ref,
            amount_q=order_with_payment.total_q,
            method="pix",
        )
        order_with_payment.data["payment"]["intent_ref"] = intent.ref
        order_with_payment.save(update_fields=["data"])
        PaymentService.authorize(intent.ref, gateway_id="test-gw-001")
        PaymentService.capture(intent.ref)

        proj = build_payment_status(order_with_payment)
        assert proj.is_paid is True
        assert proj.is_terminal is True

    def test_cancelled_order_is_terminal(self, order_with_payment):
        order_with_payment.status = "cancelled"
        order_with_payment.save(update_fields=["status"])

        proj = build_payment_status(order_with_payment)
        assert proj.is_cancelled is True
        assert proj.is_terminal is True

    def test_expired_pix_is_terminal(self, order_with_payment):
        from django.utils import timezone

        order_with_payment.data["payment"]["expires_at"] = (
            timezone.now().replace(microsecond=0) - timezone.timedelta(minutes=5)
        ).isoformat()
        order_with_payment.save(update_fields=["data"])

        proj = build_payment_status(order_with_payment)
        assert proj.is_expired is True
        assert proj.is_terminal is True

    def test_redirect_url_points_to_tracking(self, order_with_payment):
        proj = build_payment_status(order_with_payment)
        assert proj.redirect_url == f"/pedido/{order_with_payment.ref}/"

    def test_is_immutable(self, order_with_payment):
        from dataclasses import FrozenInstanceError

        proj = build_payment_status(order_with_payment)
        with pytest.raises(FrozenInstanceError):
            proj.is_paid = True  # type: ignore[misc]
