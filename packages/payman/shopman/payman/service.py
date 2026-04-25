"""
Payment Service — The single public interface for all payment operations.

Usage:
    from shopman.payman import PaymentService, PaymentError

    intent = PaymentService.create_intent("ORD-001", 1500, "pix")
    PaymentService.authorize(intent.ref, gateway_id="efi_txid_123")
    tx = PaymentService.capture(intent.ref)
    PaymentService.refund(intent.ref, amount_q=500, reason="item danificado")

Lifecycle:
    create_intent → authorize → capture → (refund)
                  → cancel
                  → fail

5 verbs: create_intent, authorize, capture, refund, cancel.
2 queries: get, get_by_order.
1 helper: get_active_intent.

Domain Contracts:

    Capture:
        - Payman allows a SINGLE capture per intent.
        - ``amount_q < authorized`` means partial capture; the uncaptured
          balance is abandoned (no second capture is allowed).
        - Full capture: omit ``amount_q`` (defaults to ``intent.amount_q``).

    Refund:
        - ``REFUNDED`` status means "at least one refund exists".
        - ``refunded_total(ref)`` is the financial source of truth for how
          much has actually been returned to the customer.
        - Multiple partial refunds are allowed as long as
          ``captured_total - refunded_total > 0``.

    Mutation Surface:
        - ``PaymentService`` is the canonical mutation surface. All status
          transitions, transaction creation, and signal emission happen here.
        - ``intent.transition_status()`` is an internal helper used only by
          the model's own ``save()`` concurrency guard; external code must
          always go through ``PaymentService`` methods.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone
from shopman.payman.exceptions import PaymentError
from shopman.payman.models.intent import PaymentIntent
from shopman.payman.models.transaction import PaymentTransaction
from shopman.payman.signals import (
    payment_authorized,
    payment_cancelled,
    payment_captured,
    payment_failed,
    payment_refunded,
)

if TYPE_CHECKING:
    from django.db.models import QuerySet

logger = logging.getLogger("shopman.payman")


class PaymentService:
    """
    Interface pública para operações de pagamento.

    Todas as operações state-changing usam @transaction.atomic + select_for_update().
    Toda transição emite o signal correspondente.
    O core é AGNÓSTICO — não sabe nada sobre gateways (Efi, Stripe, etc.).
    """

    # ================================================================
    # Create
    # ================================================================

    @classmethod
    def create_intent(
        cls,
        order_ref: str,
        amount_q: int,
        method: str,
        *,
        currency: str = "BRL",
        gateway: str = "",
        gateway_id: str = "",
        gateway_data: dict | None = None,
        expires_at=None,
        ref: str | None = None,
    ) -> PaymentIntent:
        """
        Cria intenção de pagamento.

        Args:
            order_ref: Referência do pedido (string, sem FK)
            amount_q: Valor em centavos
            method: Método de pagamento (pix, card, cash, external)
            currency: Código ISO 4217
            gateway: Nome do gateway (ex: "efi", "stripe")
            gateway_id: ID da transação no gateway
            gateway_data: Dados extras do gateway (JSON)
            expires_at: Datetime de expiração
            ref: Referência customizada (auto-gerada se None)

        Returns:
            PaymentIntent criado com status PENDING
        """
        if amount_q <= 0:
            raise PaymentError(
                code="invalid_amount",
                message="Valor deve ser positivo",
                context={"amount_q": amount_q},
            )

        intent = PaymentIntent.objects.create(
            ref=ref or cls._generate_ref(),
            order_ref=order_ref,
            method=method,
            amount_q=amount_q,
            currency=currency,
            gateway=gateway,
            gateway_id=gateway_id,
            gateway_data=gateway_data or {},
            expires_at=expires_at,
        )

        logger.info(
            "Intent created",
            extra={"ref": intent.ref, "order_ref": order_ref, "amount_q": amount_q, "method": method},
        )

        return intent

    # ================================================================
    # Authorize
    # ================================================================

    @classmethod
    @transaction.atomic
    def authorize(
        cls,
        ref: str,
        *,
        gateway_id: str = "",
        gateway_data: dict | None = None,
    ) -> PaymentIntent:
        """
        Autoriza pagamento (pending → authorized).

        O gateway externo já confirmou que os fundos estão disponíveis.
        O backend do App chama este método após receber confirmação do gateway.

        Args:
            ref: Referência do intent
            gateway_id: ID da transação no gateway
            gateway_data: Dados extras do gateway

        Returns:
            PaymentIntent atualizado

        Raises:
            PaymentError: INTENT_NOT_FOUND, INVALID_TRANSITION, INTENT_EXPIRED
        """
        intent = cls._get_for_update(ref)

        cls._require_status(intent, PaymentIntent.Status.PENDING, "authorize")
        cls._check_not_expired(intent)

        intent.status = PaymentIntent.Status.AUTHORIZED
        if gateway_id:
            intent.gateway_id = gateway_id
        if gateway_data:
            intent.gateway_data = {**intent.gateway_data, **gateway_data}
        intent.save()

        payment_authorized.send(
            sender=PaymentService,
            intent=intent,
            order_ref=intent.order_ref,
            amount_q=intent.amount_q,
            method=intent.method,
        )

        logger.info("Intent authorized", extra={"ref": ref, "order_ref": intent.order_ref})

        return intent

    # ================================================================
    # Capture
    # ================================================================

    @classmethod
    @transaction.atomic
    def capture(
        cls,
        ref: str,
        *,
        amount_q: int | None = None,
        gateway_id: str = "",
    ) -> PaymentTransaction:
        """
        Captura pagamento autorizado (authorized → captured).

        Contract: a single capture per intent. If ``amount_q < intent.amount_q``,
        this is a partial capture and the uncaptured balance is abandoned.
        No second capture is possible once the intent transitions to CAPTURED.

        Args:
            ref: Referência do intent
            amount_q: Valor a capturar (None = total autorizado).
                      Partial capture: pass a value < intent.amount_q.
            gateway_id: ID da captura no gateway

        Returns:
            PaymentTransaction de captura criada

        Raises:
            PaymentError: INTENT_NOT_FOUND, INVALID_TRANSITION, CAPTURE_EXCEEDS_AUTHORIZED
        """
        intent = cls._get_for_update(ref)

        cls._require_status(intent, PaymentIntent.Status.AUTHORIZED, "capture")

        capture_amount = amount_q if amount_q is not None else intent.amount_q

        if capture_amount <= 0:
            raise PaymentError(
                code="invalid_amount",
                message=f"Valor de captura deve ser positivo, recebido: {capture_amount}q",
                context={"capture_amount": capture_amount},
            )

        if capture_amount > intent.amount_q:
            raise PaymentError(
                code="capture_exceeds_authorized",
                message=f"Captura ({capture_amount}q) excede autorizado ({intent.amount_q}q)",
                context={"capture_amount": capture_amount, "authorized_amount": intent.amount_q},
            )

        intent.status = PaymentIntent.Status.CAPTURED
        intent.save()

        txn = PaymentTransaction.objects.create(
            intent=intent,
            type=PaymentTransaction.Type.CAPTURE,
            amount_q=capture_amount,
            gateway_id=gateway_id,
        )

        payment_captured.send(
            sender=PaymentService,
            intent=intent,
            order_ref=intent.order_ref,
            amount_q=capture_amount,
            transaction=txn,
        )

        logger.info(
            "Intent captured",
            extra={"ref": ref, "order_ref": intent.order_ref, "amount_q": capture_amount},
        )

        return txn

    # ================================================================
    # Refund
    # ================================================================

    @classmethod
    @transaction.atomic
    def refund(
        cls,
        ref: str,
        *,
        amount_q: int | None = None,
        reason: str = "",
        gateway_id: str = "",
    ) -> PaymentTransaction:
        """
        Processa reembolso (parcial ou total).

        Contract: multiple partial refunds are allowed while
        ``captured_total - refunded_total > 0``. The intent transitions to
        REFUNDED on the first refund and stays there for subsequent ones.
        ``refunded_total(ref)`` is the financial source of truth, not the
        status field alone.

        Args:
            ref: Referência do intent
            amount_q: Valor a reembolsar (None = total capturado - já reembolsado)
            reason: Motivo do reembolso
            gateway_id: ID do refund no gateway

        Returns:
            PaymentTransaction de refund criada

        Raises:
            PaymentError: INTENT_NOT_FOUND, INVALID_TRANSITION, AMOUNT_EXCEEDS_CAPTURED
        """
        intent = cls._get_for_update(ref)

        if intent.status not in (PaymentIntent.Status.CAPTURED, PaymentIntent.Status.REFUNDED):
            raise PaymentError(
                code="invalid_transition",
                message=f"Refund não permitido no status {intent.status}",
                context={"current_status": intent.status},
            )

        captured_q = cls._captured_total(intent)
        refunded_q = cls._refunded_total(intent)
        available_q = captured_q - refunded_q

        if available_q <= 0:
            raise PaymentError(
                code="already_refunded",
                message="Intent já foi totalmente reembolsado",
                context={"captured_q": captured_q, "refunded_q": refunded_q},
            )

        refund_amount = amount_q if amount_q is not None else available_q

        if refund_amount <= 0:
            raise PaymentError(
                code="invalid_amount",
                message=f"Valor de reembolso deve ser positivo, recebido: {refund_amount}q",
                context={"refund_amount": refund_amount},
            )

        if refund_amount > available_q:
            raise PaymentError(
                code="amount_exceeds_captured",
                message=f"Reembolso ({refund_amount}q) excede disponível ({available_q}q)",
                context={"refund_amount": refund_amount, "available_q": available_q},
            )

        txn = PaymentTransaction.objects.create(
            intent=intent,
            type=PaymentTransaction.Type.REFUND,
            amount_q=refund_amount,
            gateway_id=gateway_id,
        )

        # Transition to refunded status (idempotent if already refunded)
        if intent.status != PaymentIntent.Status.REFUNDED:
            intent.status = PaymentIntent.Status.REFUNDED
            intent.save()

        payment_refunded.send(
            sender=PaymentService,
            intent=intent,
            order_ref=intent.order_ref,
            amount_q=refund_amount,
            transaction=txn,
        )

        logger.info(
            "Intent refunded",
            extra={
                "ref": ref,
                "order_ref": intent.order_ref,
                "amount_q": refund_amount,
                "reason": reason,
            },
        )

        return txn

    # ================================================================
    # Cancel
    # ================================================================

    @classmethod
    @transaction.atomic
    def cancel(cls, ref: str, *, reason: str = "") -> PaymentIntent:
        """
        Cancela intent não capturado.

        Args:
            ref: Referência do intent
            reason: Motivo do cancelamento

        Returns:
            PaymentIntent cancelado

        Raises:
            PaymentError: INTENT_NOT_FOUND, INVALID_TRANSITION
        """
        intent = cls._get_for_update(ref)

        cls._require_can_transition(intent, PaymentIntent.Status.CANCELLED, "cancel")

        intent.status = PaymentIntent.Status.CANCELLED
        intent.cancel_reason = reason
        intent.save()

        payment_cancelled.send(
            sender=PaymentService,
            intent=intent,
            order_ref=intent.order_ref,
        )

        logger.info(
            "Intent cancelled",
            extra={"ref": ref, "order_ref": intent.order_ref, "reason": reason},
        )

        return intent

    # ================================================================
    # Fail
    # ================================================================

    @classmethod
    @transaction.atomic
    def fail(
        cls,
        ref: str,
        *,
        error_code: str = "",
        message: str = "",
    ) -> PaymentIntent:
        """
        Marca intent como falho.

        Args:
            ref: Referência do intent
            error_code: Código de erro do gateway
            message: Mensagem de erro

        Returns:
            PaymentIntent com status FAILED

        Raises:
            PaymentError: INTENT_NOT_FOUND, INVALID_TRANSITION
        """
        intent = cls._get_for_update(ref)

        cls._require_can_transition(intent, PaymentIntent.Status.FAILED, "fail")

        intent.status = PaymentIntent.Status.FAILED
        if error_code or message:
            intent.gateway_data = {
                **intent.gateway_data,
                "error_code": error_code,
                "error_message": message,
            }
        intent.save()

        payment_failed.send(
            sender=PaymentService,
            intent=intent,
            order_ref=intent.order_ref,
            error_code=error_code,
            message=message,
        )

        logger.info(
            "Intent failed",
            extra={"ref": ref, "order_ref": intent.order_ref, "error_code": error_code},
        )

        return intent

    # ================================================================
    # Queries
    # ================================================================

    @classmethod
    def get(cls, ref: str) -> PaymentIntent:
        """
        Busca intent por ref.

        Raises:
            PaymentError: INTENT_NOT_FOUND
        """
        try:
            return PaymentIntent.objects.get(ref=ref)
        except PaymentIntent.DoesNotExist as e:
            raise PaymentError(
                code="intent_not_found",
                message=f"Intent '{ref}' não encontrado",
                context={"ref": ref},
            ) from e

    @classmethod
    def get_by_order(cls, order_ref: str) -> QuerySet[PaymentIntent]:
        """Retorna todos os intents de um pedido, mais recentes primeiro."""
        return PaymentIntent.objects.filter(order_ref=order_ref)

    @classmethod
    def get_active_intent(cls, order_ref: str) -> PaymentIntent | None:
        """Retorna o intent não-terminal e não-expirado mais recente para o pedido."""
        now = timezone.now()
        return (
            PaymentIntent.objects.filter(order_ref=order_ref)
            .exclude(status__in=PaymentIntent.TERMINAL_STATUSES)
            .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
            .order_by("-created_at")
            .first()
        )

    @classmethod
    def get_by_gateway_id(
        cls,
        gateway_id: str,
        *,
        gateway: str | None = None,
    ) -> PaymentIntent | None:
        """Busca intent por ID externo, opcionalmente restrito ao gateway."""
        qs = PaymentIntent.objects.filter(gateway_id=gateway_id)
        if gateway is not None:
            qs = qs.filter(gateway=gateway)
        return qs.order_by("-created_at").first()

    # ================================================================
    # Aggregates
    # ================================================================

    @classmethod
    def captured_total(cls, ref: str) -> int:
        """Total capturado para um intent."""
        intent = cls.get(ref)
        return cls._captured_total(intent)

    @classmethod
    def refunded_total(cls, ref: str) -> int:
        """Total reembolsado para um intent."""
        intent = cls.get(ref)
        return cls._refunded_total(intent)

    # ================================================================
    # Private
    # ================================================================

    @classmethod
    def _get_for_update(cls, ref: str) -> PaymentIntent:
        """Get intent with select_for_update."""
        try:
            return PaymentIntent.objects.select_for_update().get(ref=ref)
        except PaymentIntent.DoesNotExist as e:
            raise PaymentError(
                code="intent_not_found",
                message=f"Intent '{ref}' não encontrado",
                context={"ref": ref},
            ) from e

    @classmethod
    def _require_status(cls, intent: PaymentIntent, expected: str, operation: str) -> None:
        """Raise if intent is not in the expected status."""
        if intent.status != expected:
            raise PaymentError(
                code="invalid_transition",
                message=f"Não é possível {operation}: status atual é {intent.status}, esperado {expected}",
                context={
                    "current_status": intent.status,
                    "expected_status": expected,
                    "operation": operation,
                },
            )

    @classmethod
    def _require_can_transition(cls, intent: PaymentIntent, target: str, operation: str) -> None:
        """Raise if intent cannot transition to target status."""
        if not intent.can_transition_to(target):
            raise PaymentError(
                code="invalid_transition",
                message=f"Não é possível {operation}: transição {intent.status} → {target} não permitida",
                context={
                    "current_status": intent.status,
                    "target_status": target,
                    "operation": operation,
                },
            )

    @classmethod
    def _check_not_expired(cls, intent: PaymentIntent) -> None:
        """Raise if intent is expired."""
        if intent.expires_at and intent.expires_at <= timezone.now():
            raise PaymentError(
                code="intent_expired",
                message=f"Intent '{intent.ref}' expirado em {intent.expires_at}",
                context={"ref": intent.ref, "expires_at": str(intent.expires_at)},
            )

    @classmethod
    def _captured_total(cls, intent: PaymentIntent) -> int:
        return (
            intent.transactions.filter(type=PaymentTransaction.Type.CAPTURE).aggregate(
                total=models.Sum("amount_q")
            )["total"]
            or 0
        )

    @classmethod
    def _refunded_total(cls, intent: PaymentIntent) -> int:
        return (
            intent.transactions.filter(type=PaymentTransaction.Type.REFUND).aggregate(
                total=models.Sum("amount_q")
            )["total"]
            or 0
        )

    @classmethod
    def _generate_ref(cls) -> str:
        return f"PAY-{uuid.uuid4().hex[:12].upper()}"
