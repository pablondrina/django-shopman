"""
Stripe Payment Backend — Integração com Stripe (card + 3D Secure).

Persiste via PaymentService (DB) + comunica com Stripe API.

SKELETON: Estrutura pronta para implementação. Métodos levantam
NotImplementedError até que a integração com stripe-python seja completada.

Configuração via settings:
    SHOPMAN_PAYMENT_BACKEND = "channels.backends.payment_stripe.StripeBackend"
    STRIPE_SECRET_KEY = os.environ["STRIPE_SECRET_KEY"]
    STRIPE_WEBHOOK_SECRET = os.environ["STRIPE_WEBHOOK_SECRET"]
"""

from __future__ import annotations

import logging

from shopman.payments.protocols import (
    CaptureResult,
    GatewayIntent,
    PaymentStatus,
    RefundResult,
)

logger = logging.getLogger(__name__)


class StripeBackend:
    """
    Backend para pagamentos via Stripe.

    Suporta:
    - Card payments via Stripe PaymentIntent
    - 3D Secure (automatic via Stripe)
    - Capture (manual ou automático)
    - Refunds (parcial ou total)

    Requer: pip install stripe

    Uso:
        backend = StripeBackend(
            secret_key="sk_test_xxx",
            webhook_secret="whsec_xxx",
        )
    """

    def __init__(
        self,
        secret_key: str | None = None,
        webhook_secret: str | None = None,
        capture_method: str = "manual",
    ):
        self.secret_key = secret_key
        self.webhook_secret = webhook_secret
        self.capture_method = capture_method  # "manual" or "automatic"

    def _get_stripe(self):
        """Lazy import do stripe SDK."""
        try:
            import stripe
        except ImportError as err:
            raise ImportError(
                "stripe package is required. Install with: pip install stripe"
            ) from err
        stripe.api_key = self.secret_key
        return stripe

    def create_intent(
        self,
        amount_q: int,
        currency: str,
        *,
        reference: str | None = None,
        metadata: dict | None = None,
    ) -> GatewayIntent:
        """
        Cria Stripe PaymentIntent com persistência via PaymentService.

        O client_secret retornado é usado pelo frontend (Stripe Elements/Checkout)
        para confirmar o pagamento com o card do cliente.
        """
        from shopman.payments import PaymentService

        # 1. Persist via PaymentService
        db_intent = PaymentService.create_intent(
            order_ref=reference or "",
            amount_q=amount_q,
            method="card",
            gateway="stripe",
            gateway_data=metadata or {},
        )

        # 2. Create Stripe PaymentIntent
        stripe = self._get_stripe()
        stripe_intent = stripe.PaymentIntent.create(
            amount=amount_q,
            currency=currency.lower(),
            capture_method=self.capture_method,
            metadata={
                "shopman_ref": db_intent.ref,
                "order_ref": reference or "",
                **(metadata or {}),
            },
        )

        # 3. Store gateway data
        db_intent.gateway_id = stripe_intent.id
        db_intent.gateway_data = {
            **(metadata or {}),
            "stripe_status": stripe_intent.status,
        }
        db_intent.save(update_fields=["gateway_id", "gateway_data"])

        status = "pending"
        if stripe_intent.status == "requires_payment_method":
            status = "pending"
        elif stripe_intent.status == "requires_action":
            status = "requires_action"

        return GatewayIntent(
            intent_id=db_intent.ref,
            status=status,
            amount_q=amount_q,
            currency=currency,
            client_secret=stripe_intent.client_secret,
            metadata=metadata,
        )

    def authorize(
        self,
        intent_id: str,
        *,
        payment_method: str | None = None,
    ) -> CaptureResult:
        """
        Verifica autorização do Stripe PaymentIntent.

        Em Stripe, a autorização acontece no frontend (Stripe.js).
        Este método verifica se o PaymentIntent foi autorizado.
        """
        from shopman.payments import PaymentError, PaymentService

        try:
            intent = PaymentService.get(intent_id)
        except PaymentError as e:
            return CaptureResult(success=False, error_code=e.code, message=e.message)

        stripe = self._get_stripe()
        stripe_intent = stripe.PaymentIntent.retrieve(intent.gateway_id)

        if stripe_intent.status in ("requires_capture", "succeeded"):
            try:
                PaymentService.authorize(intent_id, gateway_id=stripe_intent.id)
            except PaymentError:
                pass  # May already be authorized
            return CaptureResult(
                success=True,
                transaction_id=stripe_intent.id,
                amount_q=stripe_intent.amount,
            )

        return CaptureResult(
            success=False,
            error_code=stripe_intent.status,
            message=f"Stripe status: {stripe_intent.status}",
        )

    def capture(
        self,
        intent_id: str,
        *,
        amount_q: int | None = None,
        reference: str | None = None,
    ) -> CaptureResult:
        """
        Captura Stripe PaymentIntent autorizado.

        Para capture_method="automatic", o pagamento já foi capturado.
        Para capture_method="manual", chama stripe.PaymentIntent.capture().
        """
        from shopman.payments import PaymentError, PaymentService

        try:
            intent = PaymentService.get(intent_id)
        except PaymentError as e:
            return CaptureResult(success=False, error_code=e.code, message=e.message)

        stripe = self._get_stripe()

        try:
            capture_params = {}
            if amount_q is not None:
                capture_params["amount_to_capture"] = amount_q

            stripe_intent = stripe.PaymentIntent.capture(
                intent.gateway_id,
                **capture_params,
            )

            # Persist via PaymentService
            txn = PaymentService.capture(
                intent_id,
                amount_q=amount_q,
                gateway_id=stripe_intent.id,
            )

            return CaptureResult(
                success=True,
                transaction_id=stripe_intent.latest_charge,
                amount_q=txn.amount_q,
            )

        except Exception as e:
            logger.exception("Stripe capture error for %s", intent_id)
            return CaptureResult(
                success=False,
                error_code="stripe_error",
                message=str(e),
            )

    def refund(
        self,
        intent_id: str,
        *,
        amount_q: int | None = None,
        reason: str | None = None,
    ) -> RefundResult:
        """Processa reembolso via Stripe + PaymentService."""
        from shopman.payments import PaymentError, PaymentService

        try:
            intent = PaymentService.get(intent_id)
        except PaymentError as e:
            return RefundResult(success=False, error_code=e.code, message=e.message)

        stripe = self._get_stripe()

        try:
            refund_params = {"payment_intent": intent.gateway_id}
            if amount_q is not None:
                refund_params["amount"] = amount_q
            if reason:
                refund_params["reason"] = "requested_by_customer"

            stripe_refund = stripe.Refund.create(**refund_params)

            # Persist via PaymentService
            refund_amount = stripe_refund.amount
            try:
                PaymentService.refund(
                    intent_id,
                    amount_q=refund_amount,
                    reason=reason or "",
                    gateway_id=stripe_refund.id,
                )
            except PaymentError:
                pass

            return RefundResult(
                success=True,
                refund_id=stripe_refund.id,
                amount_q=refund_amount,
            )

        except Exception as e:
            logger.exception("Stripe refund error for %s", intent_id)
            return RefundResult(
                success=False,
                error_code="stripe_error",
                message=str(e),
            )

    def cancel(self, intent_id: str) -> bool:
        """Cancela Stripe PaymentIntent + PaymentService."""
        from shopman.payments import PaymentError, PaymentService

        try:
            intent = PaymentService.get(intent_id)
        except PaymentError:
            return False

        stripe = self._get_stripe()

        try:
            stripe.PaymentIntent.cancel(intent.gateway_id)

            try:
                PaymentService.cancel(intent_id)
            except PaymentError:
                pass

            return True
        except Exception:
            logger.warning("Stripe cancel failed for %s", intent_id, exc_info=True)
            return False

    def get_status(self, intent_id: str) -> PaymentStatus:
        """Consulta status via PaymentService."""
        from shopman.payments import PaymentError, PaymentService

        try:
            intent = PaymentService.get(intent_id)
            captured_q = PaymentService.captured_total(intent_id)
            refunded_q = PaymentService.refunded_total(intent_id)

            return PaymentStatus(
                intent_id=intent_id,
                status=intent.status,
                amount_q=intent.amount_q,
                captured_q=captured_q,
                refunded_q=refunded_q,
                currency=intent.currency,
            )
        except PaymentError:
            return PaymentStatus(
                intent_id=intent_id,
                status="not_found",
                amount_q=0,
                captured_q=0,
                refunded_q=0,
                currency="",
            )

    def handle_webhook(self, payload: bytes, sig_header: str) -> dict:
        """
        Processa webhook do Stripe.

        Chamado pela view de webhook. Verifica assinatura e processa evento.

        Returns:
            dict com {"event_type": str, "intent_ref": str | None}
        """
        from shopman.payments import PaymentError, PaymentService

        stripe = self._get_stripe()
        event = stripe.Webhook.construct_event(
            payload, sig_header, self.webhook_secret,
        )

        intent_ref = None

        if event.type == "payment_intent.succeeded":
            stripe_intent = event.data.object
            shopman_ref = stripe_intent.metadata.get("shopman_ref")
            if shopman_ref:
                intent_ref = shopman_ref
                try:
                    PaymentService.authorize(shopman_ref, gateway_id=stripe_intent.id)
                except PaymentError:
                    pass
                try:
                    PaymentService.capture(shopman_ref, gateway_id=stripe_intent.id)
                except PaymentError:
                    pass

        elif event.type == "payment_intent.payment_failed":
            stripe_intent = event.data.object
            shopman_ref = stripe_intent.metadata.get("shopman_ref")
            if shopman_ref:
                intent_ref = shopman_ref
                last_error = stripe_intent.last_payment_error
                try:
                    PaymentService.fail(
                        shopman_ref,
                        error_code=last_error.code if last_error else "unknown",
                        message=last_error.message if last_error else "",
                    )
                except PaymentError:
                    pass

        elif event.type == "charge.refunded":
            charge = event.data.object
            stripe_intent_id = charge.payment_intent
            if stripe_intent_id:
                db_intent = PaymentService.get_by_gateway_id(stripe_intent_id)
                if db_intent:
                    intent_ref = db_intent.ref
                    refund_amount_q = charge.amount_refunded
                    try:
                        PaymentService.refund(
                            db_intent.ref,
                            amount_q=refund_amount_q,
                            gateway_id=charge.id,
                        )
                    except PaymentError:
                        pass

        return {"event_type": event.type, "intent_ref": intent_ref}
