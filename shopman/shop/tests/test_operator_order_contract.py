"""Operational contract guardrails for order commands."""

from __future__ import annotations

from django.test import TestCase
from shopman.orderman.models import Directive, Order

from shopman.shop.services.cancellation import cancel
from shopman.shop.services.operator_orders import reject_order


def _order(ref: str, status: str) -> Order:
    return Order.objects.create(
        ref=ref,
        channel_ref="web",
        session_key=f"session-{ref}",
        status=status,
        total_q=1500,
        snapshot={"items": [{"sku": "PAO", "qty": 1}], "data": {}},
        data={
            "customer": {"name": "Cliente"},
            "fulfillment_type": "pickup",
            "payment": {"method": "cash"},
        },
    )


class OperatorOrderContractTests(TestCase):
    def test_reject_uses_canonical_notification_contract(self) -> None:
        order = _order("CONTRACT-REJECT-NEW", Order.Status.NEW)

        reject_order(
            order,
            reason="sem estoque",
            actor="operator:ana",
            rejected_by="ana",
        )

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)
        directive = Directive.objects.get(topic="notification.send", payload__order_ref=order.ref)
        self.assertEqual(directive.payload["template"], "order_rejected")
        self.assertEqual(directive.payload["reason"], "sem estoque")
        self.assertEqual(directive.payload["rejected_by"], "ana")
        self.assertTrue(directive.payload["requires_active_notification"])
        self.assertEqual(directive.dedupe_key, f"notification.send:{order.ref}:order_rejected")

    def test_reject_is_not_a_late_stage_cancel_shortcut(self) -> None:
        order = _order("CONTRACT-REJECT-CONF", Order.Status.CONFIRMED)

        with self.assertRaises(ValueError):
            reject_order(
                order,
                reason="sem estoque",
                actor="operator:ana",
                rejected_by="ana",
            )

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CONFIRMED)
        self.assertNotIn("cancellation_reason", order.data)
        self.assertNotIn("rejected_by", order.data)

    def test_cancel_does_not_mutate_orders_that_cannot_transition_to_cancelled(self) -> None:
        for status in (
            Order.Status.READY,
            Order.Status.DISPATCHED,
            Order.Status.DELIVERED,
            Order.Status.COMPLETED,
            Order.Status.RETURNED,
        ):
            with self.subTest(status=status):
                order = _order(f"CONTRACT-CANCEL-{status}", status)

                changed = cancel(order, reason="operator_requested", actor="operator:ana")

                self.assertFalse(changed)
                order.refresh_from_db()
                self.assertEqual(order.status, status)
                self.assertNotIn("cancellation_reason", order.data)
                self.assertNotIn("cancelled_by", order.data)

    def test_cancel_still_applies_when_status_allows_cancellation(self) -> None:
        order = _order("CONTRACT-CANCEL-PREPARING", Order.Status.PREPARING)

        changed = cancel(order, reason="operator_requested", actor="operator:ana")

        self.assertTrue(changed)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertEqual(order.data["cancellation_reason"], "operator_requested")
