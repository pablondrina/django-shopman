"""
Stripe Payment Backend — Integração com Stripe.

Requer: pip install stripe
"""

from __future__ import annotations

import logging
from typing import Any

from shopman.payment.protocols import (
    CaptureResult,
    PaymentIntent,
    PaymentStatus,
    RefundResult,
)

logger = logging.getLogger(__name__)


class StripeBackend:
    """
    Backend para pagamentos via Stripe.

    Args:
        api_key: Stripe Secret Key (sk_test_xxx ou sk_live_xxx)
        webhook_secret: Webhook signing secret (whsec_xxx) para validação

    Example:
        backend = StripeBackend(
            api_key="sk_test_xxx",
            webhook_secret="whsec_xxx",
        )

    Configuração via settings:
        SHOPMAN_PAYMENT = {
            "backend": "stripe",
            "stripe": {
                "api_key": os.environ["STRIPE_SECRET_KEY"],
                "webhook_secret": os.environ["STRIPE_WEBHOOK_SECRET"],
            },
        }

    Para testes locais, use Stripe CLI:
        stripe listen --forward-to localhost:8000/webhooks/stripe/
    """

    def __init__(
        self,
        api_key: str,
        webhook_secret: str | None = None,
    ):
        try:
            import stripe
        except ImportError:
            raise ImportError(
                "Stripe não instalado. Execute: pip install stripe"
            )

        self.stripe = stripe
        self.stripe.api_key = api_key
        self.webhook_secret = webhook_secret

    def create_intent(
        self,
        amount_q: int,
        currency: str,
        *,
        reference: str | None = None,
        metadata: dict | None = None,
    ) -> PaymentIntent:
        """Cria PaymentIntent no Stripe."""
        meta = metadata or {}
        if reference:
            meta["shopman_reference"] = reference

        try:
            intent = self.stripe.PaymentIntent.create(
                amount=amount_q,
                currency=currency.lower(),
                metadata=meta,
                automatic_payment_methods={"enabled": True},
            )

            return PaymentIntent(
                intent_id=intent.id,
                status=self._map_status(intent.status),
                amount_q=intent.amount,
                currency=intent.currency.upper(),
                client_secret=intent.client_secret,
                metadata=dict(intent.metadata),
            )

        except self.stripe.error.StripeError as e:
            logger.error(f"Stripe create_intent error: {e}")
            raise

    def authorize(
        self,
        intent_id: str,
        *,
        payment_method: str | None = None,
    ) -> CaptureResult:
        """
        Confirma/autoriza PaymentIntent.

        Nota: Na maioria dos casos, a confirmação é feita pelo frontend
        via Stripe.js. Este método é para casos server-side.
        """
        try:
            params = {}
            if payment_method:
                params["payment_method"] = payment_method

            intent = self.stripe.PaymentIntent.confirm(intent_id, **params)

            if intent.status in ("succeeded", "requires_capture"):
                return CaptureResult(
                    success=True,
                    transaction_id=intent.id,
                    amount_q=intent.amount,
                )
            else:
                return CaptureResult(
                    success=False,
                    error_code=intent.status,
                    message=f"Status: {intent.status}",
                )

        except self.stripe.error.CardError as e:
            return CaptureResult(
                success=False,
                error_code=e.code,
                message=e.user_message,
            )
        except self.stripe.error.StripeError as e:
            return CaptureResult(
                success=False,
                error_code="stripe_error",
                message=str(e),
            )

    def capture(
        self,
        intent_id: str,
        *,
        amount_q: int | None = None,
        reference: str | None = None,
    ) -> CaptureResult:
        """Captura PaymentIntent autorizado."""
        try:
            params = {}
            if amount_q:
                params["amount_to_capture"] = amount_q
            if reference:
                params["metadata"] = {"order_ref": reference}

            intent = self.stripe.PaymentIntent.capture(intent_id, **params)

            return CaptureResult(
                success=True,
                transaction_id=intent.latest_charge,
                amount_q=intent.amount_received,
            )

        except self.stripe.error.StripeError as e:
            logger.error(f"Stripe capture error: {e}")
            return CaptureResult(
                success=False,
                error_code="capture_failed",
                message=str(e),
            )

    def refund(
        self,
        intent_id: str,
        *,
        amount_q: int | None = None,
        reason: str | None = None,
    ) -> RefundResult:
        """Processa reembolso."""
        try:
            params = {"payment_intent": intent_id}
            if amount_q:
                params["amount"] = amount_q
            if reason:
                # Stripe aceita: duplicate, fraudulent, requested_by_customer
                params["reason"] = "requested_by_customer"
                params["metadata"] = {"shopman_reason": reason}

            refund = self.stripe.Refund.create(**params)

            return RefundResult(
                success=True,
                refund_id=refund.id,
                amount_q=refund.amount,
            )

        except self.stripe.error.StripeError as e:
            logger.error(f"Stripe refund error: {e}")
            return RefundResult(
                success=False,
                error_code="refund_failed",
                message=str(e),
            )

    def cancel(self, intent_id: str) -> bool:
        """Cancela PaymentIntent."""
        try:
            self.stripe.PaymentIntent.cancel(intent_id)
            return True
        except self.stripe.error.StripeError:
            return False

    def get_status(self, intent_id: str) -> PaymentStatus:
        """Consulta status do PaymentIntent."""
        try:
            intent = self.stripe.PaymentIntent.retrieve(intent_id)

            # Calcula valores
            captured = intent.amount_received or 0
            refunded = 0

            # Soma refunds se existirem
            if intent.latest_charge:
                try:
                    charge = self.stripe.Charge.retrieve(intent.latest_charge)
                    refunded = charge.amount_refunded
                except self.stripe.error.StripeError as e:
                    logger.warning(f"Failed to retrieve charge for refund amount: {e}")

            return PaymentStatus(
                intent_id=intent.id,
                status=self._map_status(intent.status),
                amount_q=intent.amount,
                captured_q=captured,
                refunded_q=refunded,
                currency=intent.currency.upper(),
                metadata=dict(intent.metadata),
            )

        except self.stripe.error.StripeError as e:
            return PaymentStatus(
                intent_id=intent_id,
                status="error",
                amount_q=0,
                captured_q=0,
                refunded_q=0,
                currency="",
                metadata={"error": str(e)},
            )

    def _map_status(self, stripe_status: str) -> str:
        """Mapeia status Stripe para status Shopman."""
        mapping = {
            "requires_payment_method": "pending",
            "requires_confirmation": "pending",
            "requires_action": "pending",
            "processing": "pending",
            "requires_capture": "authorized",
            "succeeded": "captured",
            "canceled": "cancelled",
        }
        return mapping.get(stripe_status, stripe_status)

    def verify_webhook(self, payload: bytes, signature: str) -> dict | None:
        """
        Verifica e decodifica webhook do Stripe.

        Args:
            payload: Body raw do request
            signature: Header Stripe-Signature

        Returns:
            Event data ou None se inválido
        """
        if not self.webhook_secret:
            logger.warning("Stripe webhook_secret não configurado")
            return None

        try:
            event = self.stripe.Webhook.construct_event(
                payload, signature, self.webhook_secret
            )
            return event
        except (ValueError, self.stripe.error.SignatureVerificationError) as e:
            logger.error(f"Stripe webhook verification failed: {e}")
            return None
