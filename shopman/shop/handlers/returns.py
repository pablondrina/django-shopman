"""
Return handler + service — devoluções.

Inline de shopman.returns.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from shopman.orderman.exceptions import DirectiveTerminalError
from shopman.orderman.models import Directive, Order

from shopman.shop.directives import RETURN_PROCESS

logger = logging.getLogger(__name__)


@dataclass
class ReturnResult:
    """Resultado da iniciação de devolução."""

    success: bool
    return_type: str = ""
    refund_total_q: int = 0
    items_returned: list[dict] = field(default_factory=list)
    directive_id: int | None = None
    error: str | None = None


class ReturnService:
    """Service para devoluções de pedidos."""

    @classmethod
    @transaction.atomic
    def initiate_return(cls, order: Order, items: list[dict], reason: str, actor: str) -> ReturnResult:
        from shopman.orderman.exceptions import InvalidTransition

        order = Order.objects.select_for_update().get(pk=order.pk)

        valid_statuses = [Order.Status.DELIVERED, Order.Status.COMPLETED]
        if order.status not in valid_statuses:
            raise InvalidTransition(
                code="invalid_transition",
                message=f"Devolução só é permitida para pedidos com status delivered ou completed, atual: {order.status}",
                context={"current_status": order.status, "valid_statuses": [s.value for s in valid_statuses]},
            )

        order_items_by_line = {item.line_id: item for item in order.items.all()}
        items_detail = []
        refund_total_q = 0

        for item_req in items:
            line_id = item_req["line_id"]
            qty = Decimal(str(item_req["qty"]))

            if line_id not in order_items_by_line:
                return ReturnResult(success=False, error=f"Item não encontrado no pedido: {line_id}")

            order_item = order_items_by_line[line_id]
            if qty > order_item.qty:
                return ReturnResult(success=False, error=f"Quantidade de devolução ({qty}) excede quantidade do pedido ({order_item.qty}) para item {line_id}")

            refund_q = int(order_item.unit_price_q * qty)
            refund_total_q += refund_q
            items_detail.append({"line_id": line_id, "sku": order_item.sku, "qty": str(qty), "refund_q": refund_q})

        is_total = all(
            Decimal(str(item_req["qty"])) == order_items_by_line[item_req["line_id"]].qty
            for item_req in items
        ) and len(items) == len(order_items_by_line)

        return_type = "total" if is_total else "partial"

        return_record = {
            "timestamp": timezone.now().isoformat(), "actor": actor, "reason": reason,
            "type": return_type, "items": items_detail, "refund_total_q": refund_total_q,
            "refund_processed": False,
        }

        if "returns" not in order.data:
            order.data["returns"] = []
        order.data["returns"].append(return_record)
        order.save(update_fields=["data", "updated_at"])

        order.emit_event(
            event_type="return_initiated", actor=actor,
            payload={"reason": reason, "return_type": return_type, "items": items_detail, "refund_total_q": refund_total_q},
        )

        if is_total:
            order.transition_status(Order.Status.RETURNED, actor=actor)

        directive = Directive.objects.create(
            topic=RETURN_PROCESS,
            payload={
                "order_ref": order.ref, "items": items_detail, "reason": reason,
                "refund_total_q": refund_total_q, "return_index": len(order.data["returns"]) - 1,
            },
        )

        return ReturnResult(
            success=True, return_type=return_type, refund_total_q=refund_total_q,
            items_returned=items_detail, directive_id=directive.pk,
        )

    @classmethod
    @transaction.atomic
    def process_refund(cls, order: Order, amount_q: int, actor: str, *, fiscal_backend=None) -> dict:
        from shopman.shop.services import payment as payment_service

        result = {"refund": None, "fiscal": None}

        if (order.data.get("payment") or {}).get("intent_ref"):
            try:
                payment_service.refund(order)
                result["refund"] = {"success": True, "amount_q": amount_q}
                order.emit_event(
                    event_type="refund_processed",
                    actor=actor,
                    payload={"amount_q": amount_q, "success": True},
                )
            except Exception as exc:
                logger.exception("process_refund: payment refund failed for %s", order.ref)
                result["refund"] = {"success": False, "error": str(exc)}

        if order.data.get("nfce_access_key") and fiscal_backend:
            cancel_result = fiscal_backend.cancel(reference=order.ref, reason="Devolução de mercadoria")
            result["fiscal"] = {"success": cancel_result.success, "protocol_number": cancel_result.protocol_number}
            order.emit_event(event_type="fiscal_cancelled", actor=actor, payload={"success": cancel_result.success, "protocol_number": cancel_result.protocol_number})

        return result


class ReturnHandler:
    """Directive handler para processamento de devoluções. Topic: return.process"""

    topic = RETURN_PROCESS

    def __init__(self, *, fiscal_backend=None):
        self.fiscal_backend = fiscal_backend

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from shopman.shop.adapters import get_adapter

        payload = message.payload
        order_ref = payload["order_ref"]
        items = payload["items"]
        refund_total_q = payload["refund_total_q"]
        return_index = payload.get("return_index", 0)

        try:
            order = Order.objects.get(ref=order_ref)
        except Order.DoesNotExist:
            raise DirectiveTerminalError(f"Order not found: {order_ref}")

        returns = order.data.get("returns", [])
        if return_index < len(returns) and returns[return_index].get("refund_processed"):
            return

        stock_adapter = get_adapter("stock")
        if stock_adapter:
            for item in items:
                try:
                    stock_adapter.receive_return(
                        sku=item["sku"],
                        qty=Decimal(str(item["qty"])),
                        reference=order_ref,
                        reason=f"Devolução pedido {order_ref}",
                    )
                except Exception:
                    logger.exception("ReturnHandler: Failed to reverse stock for sku=%s order=%s", item["sku"], order_ref)

        try:
            ReturnService.process_refund(
                order=order, amount_q=refund_total_q, actor="return.process",
                fiscal_backend=self.fiscal_backend,
            )
        except Exception as exc:
            raise DirectiveTerminalError(f"Refund processing failed: {exc}") from exc

        order.refresh_from_db()
        returns = order.data.get("returns", [])
        if return_index < len(returns):
            returns[return_index]["refund_processed"] = True
            order.data["returns"] = returns
            order.save(update_fields=["data", "updated_at"])


__all__ = ["ReturnHandler", "ReturnService", "ReturnResult"]
