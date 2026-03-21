"""
Shopman Return Service -- Lógica de negócio para devoluções.

ReturnService orquestra:
- Validação de status e items
- Criação de eventos de auditoria
- Transição de status (total) ou registro (parcial)
- Criação de Directive para processamento async (estoque, reembolso, fiscal)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from shopman.ordering.models import Directive, Order, OrderEvent, OrderItem

logger = logging.getLogger(__name__)


@dataclass
class ReturnResult:
    """Resultado da iniciação de devolução."""

    success: bool
    return_type: str = ""  # "total" | "partial"
    refund_total_q: int = 0
    items_returned: list[dict] = field(default_factory=list)
    directive_id: int | None = None
    error: str | None = None


class ReturnService:
    """Service para devoluções de pedidos."""

    @classmethod
    @transaction.atomic
    def initiate_return(
        cls,
        order: Order,
        items: list[dict],
        reason: str,
        actor: str,
    ) -> ReturnResult:
        """
        Inicia devolução de um pedido.

        Args:
            order: Pedido a ser devolvido
            items: Lista de {line_id, qty} para devolução
            reason: Motivo da devolução
            actor: Quem está iniciando a devolução

        Returns:
            ReturnResult com detalhes da devolução

        Raises:
            InvalidTransition: Se o pedido não está em status válido para devolução
        """
        from shopman.ordering.exceptions import InvalidTransition

        # Lock para evitar race conditions
        order = Order.objects.select_for_update().get(pk=order.pk)

        # Valida status
        valid_statuses = [Order.Status.DELIVERED, Order.Status.COMPLETED]
        if order.status not in valid_statuses:
            raise InvalidTransition(
                code="invalid_transition",
                message=f"Devolução só é permitida para pedidos com status delivered ou completed, atual: {order.status}",
                context={
                    "current_status": order.status,
                    "valid_statuses": [s.value for s in valid_statuses],
                },
            )

        # Valida items e calcula reembolso
        order_items_by_line = {item.line_id: item for item in order.items.all()}
        items_detail = []
        refund_total_q = 0
        total_qty_returned = Decimal("0")
        total_qty_order = Decimal("0")

        for item_req in items:
            line_id = item_req["line_id"]
            qty = Decimal(str(item_req["qty"]))

            if line_id not in order_items_by_line:
                return ReturnResult(
                    success=False,
                    error=f"Item não encontrado no pedido: {line_id}",
                )

            order_item = order_items_by_line[line_id]

            if qty > order_item.qty:
                return ReturnResult(
                    success=False,
                    error=f"Quantidade de devolução ({qty}) excede quantidade do pedido ({order_item.qty}) para item {line_id}",
                )

            refund_q = int(order_item.unit_price_q * qty)
            refund_total_q += refund_q
            total_qty_returned += qty

            items_detail.append({
                "line_id": line_id,
                "sku": order_item.sku,
                "qty": str(qty),
                "refund_q": refund_q,
            })

        # Determina se é total ou parcial
        for oi in order_items_by_line.values():
            total_qty_order += oi.qty

        is_total = all(
            Decimal(str(item_req["qty"])) == order_items_by_line[item_req["line_id"]].qty
            for item_req in items
        ) and len(items) == len(order_items_by_line)

        return_type = "total" if is_total else "partial"

        # Registra no order.data
        return_record = {
            "timestamp": timezone.now().isoformat(),
            "actor": actor,
            "reason": reason,
            "type": return_type,
            "items": items_detail,
            "refund_total_q": refund_total_q,
            "refund_processed": False,
        }

        if "returns" not in order.data:
            order.data["returns"] = []
        order.data["returns"].append(return_record)
        order.save(update_fields=["data", "updated_at"])

        # Evento de auditoria
        order.emit_event(
            event_type="return_initiated",
            actor=actor,
            payload={
                "reason": reason,
                "return_type": return_type,
                "items": items_detail,
                "refund_total_q": refund_total_q,
            },
        )

        # Transiciona para RETURNED se devolução total
        if is_total:
            order.transition_status(Order.Status.RETURNED, actor=actor)

        # Cria directive para processamento async
        directive = Directive.objects.create(
            topic="return.process",
            payload={
                "order_ref": order.ref,
                "items": items_detail,
                "reason": reason,
                "refund_total_q": refund_total_q,
                "return_index": len(order.data["returns"]) - 1,
            },
        )

        return ReturnResult(
            success=True,
            return_type=return_type,
            refund_total_q=refund_total_q,
            items_returned=items_detail,
            directive_id=directive.pk,
        )

    @classmethod
    @transaction.atomic
    def process_refund(
        cls,
        order: Order,
        amount_q: int,
        actor: str,
        *,
        payment_backend=None,
        fiscal_backend=None,
    ) -> dict:
        """
        Processa reembolso e cancelamento fiscal.

        Args:
            order: Pedido
            amount_q: Valor a reembolsar em centavos
            actor: Quem está processando
            payment_backend: PaymentBackend instance
            fiscal_backend: FiscalBackend instance (opcional)

        Returns:
            Dict com resultado do reembolso
        """
        result = {"refund": None, "fiscal": None}

        # Reembolso via PaymentBackend
        intent_id = (order.data.get("payment") or {}).get("intent_id")
        if intent_id and payment_backend:
            refund_result = payment_backend.refund(
                intent_id,
                amount_q=amount_q,
                reason="Devolução de mercadoria",
            )
            result["refund"] = {
                "success": refund_result.success,
                "refund_id": refund_result.refund_id,
                "amount_q": refund_result.amount_q,
            }

            order.emit_event(
                event_type="refund_processed",
                actor=actor,
                payload={
                    "amount_q": amount_q,
                    "refund_id": refund_result.refund_id,
                    "success": refund_result.success,
                },
            )

        # Cancelamento fiscal
        if order.data.get("nfce_access_key") and fiscal_backend:
            cancel_result = fiscal_backend.cancel(
                reference=order.ref,
                reason="Devolução de mercadoria",
            )
            result["fiscal"] = {
                "success": cancel_result.success,
                "protocol_number": cancel_result.protocol_number,
            }

            order.emit_event(
                event_type="fiscal_cancelled",
                actor=actor,
                payload={
                    "success": cancel_result.success,
                    "protocol_number": cancel_result.protocol_number,
                },
            )

        return result
