"""Operational contract guardrails for order mutations."""

from __future__ import annotations

from django.test import TestCase
from shopman.orderman.models import Directive, Order

from shopman.shop.services.cancellation import cancel
from shopman.shop.services.operator_orders import cancel_order, reject_order


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


class CancellationReasonReachesCustomerTests(TestCase):
    """G2: the operator's justification must reach the customer, not a generic notice."""

    def _cancelled_notifications(self, order_ref: str):
        return list(
            Directive.objects.filter(
                topic="notification.send",
                payload__order_ref=order_ref,
                payload__template="order_cancelled",
            )
        )

    def test_operator_cancel_with_reason_carries_it_to_the_customer(self) -> None:
        order = _order("CONTRACT-CANCEL-REASON", Order.Status.PREPARING)

        with self.captureOnCommitCallbacks(execute=True):
            cancel_order(
                order,
                reason="Item indisponível no momento",
                actor="operator:ana",
                customer_note="Item indisponível no momento",
            )

        order.refresh_from_db()
        # Customer-facing note is stored separately from the audit reason.
        self.assertEqual(order.data["cancellation_note"], "Item indisponível no momento")
        notes = self._cancelled_notifications(order.ref)
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0].payload.get("reason"), "Item indisponível no momento")

    def test_operator_cancel_without_reason_stays_generic(self) -> None:
        order = _order("CONTRACT-CANCEL-NOREASON", Order.Status.PREPARING)

        with self.captureOnCommitCallbacks(execute=True):
            cancel_order(order, reason="Cancelado pelo operador", actor="operator:ana")

        order.refresh_from_db()
        self.assertNotIn("cancellation_note", order.data)
        notes = self._cancelled_notifications(order.ref)
        self.assertEqual(len(notes), 1)
        self.assertIsNone(notes[0].payload.get("reason"))

    def test_machine_cancellation_code_never_leaks_to_customer(self) -> None:
        # Timeout/self-cancel paths write a machine code to cancellation_reason but
        # no customer note — the customer must not see "pix_timeout".
        order = _order("CONTRACT-CANCEL-CODE", Order.Status.NEW)

        with self.captureOnCommitCallbacks(execute=True):
            cancel(order, reason="pix_timeout", actor="system")

        notes = self._cancelled_notifications(order.ref)
        self.assertEqual(len(notes), 1)
        self.assertIsNone(notes[0].payload.get("reason"))

    def test_reject_does_not_also_send_a_generic_cancelled_notification(self) -> None:
        # reject_order queues order_rejected (with the reason). The CANCELLED
        # transition must not double-notify with a generic order_cancelled.
        order = _order("CONTRACT-REJECT-NODUP", Order.Status.NEW)

        with self.captureOnCommitCallbacks(execute=True):
            reject_order(order, reason="Sem estoque", actor="operator:ana", rejected_by="ana")

        self.assertEqual(self._cancelled_notifications(order.ref), [])
        rejected = Directive.objects.filter(
            topic="notification.send",
            payload__order_ref=order.ref,
            payload__template="order_rejected",
        )
        self.assertEqual(rejected.count(), 1)
        self.assertEqual(rejected.first().payload.get("reason"), "Sem estoque")
