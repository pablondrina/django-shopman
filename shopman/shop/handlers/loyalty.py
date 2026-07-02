"""
Loyalty handlers — earn points on completion, redeem points on commit.
"""

from __future__ import annotations

import logging

from shopman.orderman.exceptions import DirectiveTerminalError, DirectiveTransientError
from shopman.orderman.models import Directive

from shopman.shop.adapters import get_adapter
from shopman.shop.directives import LOYALTY_EARN, LOYALTY_REDEEM

logger = logging.getLogger(__name__)


class LoyaltyEarnHandler:
    """Awards loyalty points on order completion. Topic: loyalty.earn"""

    topic = LOYALTY_EARN

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from shopman.orderman.models import Order

        payload = message.payload
        order_ref = payload.get("order_ref")

        if not order_ref:
            raise DirectiveTerminalError("missing order_ref")

        try:
            order = Order.objects.get(ref=order_ref)
        except Order.DoesNotExist as exc:
            raise DirectiveTerminalError(f"Order not found: {order_ref}") from exc

        customer_ref = _customer_ref_for_order(order)
        if not customer_ref:
            logger.warning("loyalty.earn: no customer_ref on order %s, skipping", order_ref)
            return

        # Calculate points: points_per_real por R$ 1,00 (100 centavos),
        # configurável via Shop.defaults["loyalty"] (admin).
        from shopman.shop.loyalty_config import resolve_loyalty_config

        config = resolve_loyalty_config()
        points = (order.total_q // 100) * config.points_per_real
        if points <= 0:
            return

        try:
            adapter = get_adapter("customer")

            # Enroll if not yet enrolled (idempotent)
            adapter.enroll_loyalty(customer_ref)

            reference = f"order:{order.ref}"
            # At-least-once: retry da directive não pode creditar duas vezes.
            if adapter.has_loyalty_transaction(
                customer_ref, reference=reference, transaction_type="earn"
            ):
                logger.info("loyalty.earn: already credited for %s, skipping", reference)
                return

            # Award points
            adapter.earn_points(
                customer_ref=customer_ref,
                points=points,
                description=f"Pedido {order.ref}",
                reference=reference,
                created_by="system",
            )

            logger.info("loyalty.earn: +%d points for %s (order %s)", points, customer_ref, order_ref)

        except Exception as exc:
            raise DirectiveTransientError(str(exc)) from exc


class LoyaltyRedeemHandler:
    """Redeems loyalty points on order commit. Topic: loyalty.redeem"""

    topic = LOYALTY_REDEEM

    def handle(self, *, message: Directive, ctx: dict) -> None:
        payload = message.payload
        order_ref = payload.get("order_ref")
        points = int(payload.get("points", 0))

        if not order_ref or points <= 0:
            return

        try:
            from shopman.orderman.models import Order
            order = Order.objects.get(ref=order_ref)
        except Order.DoesNotExist as exc:
            raise DirectiveTerminalError(f"Order not found: {order_ref}") from exc

        customer_ref = _customer_ref_for_order(order)
        if not customer_ref:
            logger.warning("loyalty.redeem: no customer_ref on order %s, skipping", order_ref)
            return

        try:
            adapter = get_adapter("customer")

            reference = f"order:{order_ref}"
            # At-least-once: retry da directive não pode debitar duas vezes.
            if adapter.has_loyalty_transaction(
                customer_ref, reference=reference, transaction_type="redeem"
            ):
                logger.info("loyalty.redeem: already debited for %s, skipping", reference)
                return

            adapter.redeem_points(
                customer_ref=customer_ref,
                points=points,
                description=f"Resgate pedido {order_ref}",
                reference=reference,
                created_by="system",
            )

            logger.info("loyalty.redeem: -%d points for %s (order %s)", points, customer_ref, order_ref)

        except Exception as exc:
            raise _redeem_directive_error(exc, order_ref=order_ref, points=points) from exc


def _redeem_directive_error(exc: Exception, *, order_ref: str, points: int):
    """Saldo insuficiente nunca se cura com retry → terminal; resto é transiente.

    Mas o desconto de pontos JÁ foi aplicado ao total no commit — um terminal
    silencioso é receita perdida invisível. Alertar o operador para conciliar.
    """
    from shopman.guestman.exceptions import CustomerError

    if isinstance(exc, CustomerError) and getattr(exc, "code", "") == "LOYALTY_INSUFFICIENT_POINTS":
        from shopman.shop.services.observability import create_operator_alert

        create_operator_alert(
            type="loyalty_redeem_uncovered",
            severity="critical",
            message=(
                f"Pedido {order_ref} recebeu desconto de {points} pontos, mas o "
                "saldo do cliente ficou insuficiente na hora de debitar (corrida "
                "de resgate). O desconto foi dado sem baixa de pontos — conciliar."
            ),
            order_ref=order_ref,
            dedupe_key=f"loyalty_redeem_uncovered:{order_ref}",
        )
        return DirectiveTerminalError(str(exc))
    return DirectiveTransientError(str(exc))


def _customer_ref_for_order(order) -> str:
    data = order.data or {}
    customer_ref = data.get("customer_ref")
    if customer_ref:
        return str(customer_ref)

    try:
        from shopman.shop.services import customer as customer_service

        customer_service.ensure(order)
        order.refresh_from_db()
    except Exception:
        logger.warning("loyalty.customer_ref_resolution_failed order=%s", order.ref, exc_info=True)
        return ""

    return str((order.data or {}).get("customer_ref") or "")
