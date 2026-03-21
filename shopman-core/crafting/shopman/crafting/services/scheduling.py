"""
Planning service — plan and adjust operations.

All methods are @classmethod (mixin pattern, like Stocking).
"""

import logging
from decimal import Decimal

from django.db import models, transaction
from django.utils import timezone

from shopman.crafting.exceptions import CraftError, StaleRevision

logger = logging.getLogger(__name__)


def _check_rev(order, expected_rev):
    """
    Optimistic concurrency check.

    If expected_rev is provided, atomically check and bump.
    If not provided, just bump rev.
    """
    from shopman.crafting.models import WorkOrder

    if expected_rev is not None:
        updated = WorkOrder.objects.filter(
            pk=order.pk, rev=expected_rev,
        ).update(rev=models.F("rev") + 1)
        if not updated:
            raise StaleRevision(order, expected_rev)
        order.rev = expected_rev + 1
    else:
        WorkOrder.objects.filter(pk=order.pk).update(rev=models.F("rev") + 1)
        order.refresh_from_db(fields=["rev"])


def _next_seq(order):
    """
    Compute next event seq atomically.

    Uses MAX(seq) + 1 with Coalesce to handle zero events.
    Must be called inside transaction.atomic() after the WorkOrder row
    is already locked (via select_for_update or _check_rev's UPDATE).
    """
    from django.db.models import Value
    from django.db.models.functions import Coalesce

    max_seq = order.events.aggregate(
        m=Coalesce(models.Max("seq"), Value(-1))
    )["m"]
    return max_seq + 1


class CraftPlanning:
    """Plan and adjust operations."""

    @classmethod
    def plan(cls, recipe_or_items, quantity=None, date=None, **kwargs):
        """
        Create WorkOrder(s).

        Signatures:
            craft.plan(recipe, 100)                         -> WorkOrder
            craft.plan(recipe, 100, date=tomorrow)          -> WorkOrder
            craft.plan([(r_a, 100), (r_b, 45)], date=tomorrow) -> list[WorkOrder]

        Returns:
            WorkOrder for single, list[WorkOrder] for batch.
        """
        # Batch mode: list of (recipe, quantity) tuples
        if isinstance(recipe_or_items, (list, tuple)) and recipe_or_items and isinstance(recipe_or_items[0], (list, tuple)):
            return cls._plan_batch(recipe_or_items, date, **kwargs)

        # Single mode
        recipe = recipe_or_items
        if quantity is None:
            raise CraftError("INVALID_QUANTITY")
        quantity = Decimal(str(quantity))
        if quantity <= 0:
            raise CraftError("INVALID_QUANTITY", quantity=float(quantity))

        from shopman.crafting.models import WorkOrder
        from shopman.crafting.signals import production_changed

        with transaction.atomic():
            wo = cls._create_work_order(recipe, quantity, date, **kwargs)

        production_changed.send(
            sender=WorkOrder,
            product_ref=wo.output_ref,
            date=date,
            action="planned",
            work_order=wo,
        )

        logger.info("WorkOrder %s planned: %s x %s", wo.code, quantity, recipe.output_ref)
        return wo

    @classmethod
    def _create_work_order(cls, recipe, quantity, date, **kwargs):
        """
        Create WorkOrder + planned event + BOM snapshot (no signal).

        Used by plan() and _plan_batch(). Must be called inside
        transaction.atomic().

        The BOM snapshot freezes recipe items at plan time so that
        close() uses the recipe as-it-was, not as-it-is-now.
        """
        from shopman.crafting.models import WorkOrder, WorkOrderEvent

        wo_kwargs = {}
        for key in ("source_ref", "position_ref", "assigned_ref", "meta"):
            if key in kwargs:
                wo_kwargs[key] = kwargs[key]

        # Freeze BOM into meta._recipe_snapshot
        snapshot = {
            "batch_size": str(recipe.batch_size),
            "items": [
                {"input_ref": ri.input_ref, "quantity": str(ri.quantity), "unit": ri.unit}
                for ri in recipe.items.filter(is_optional=False).order_by("sort_order")
            ],
        }
        user_meta = wo_kwargs.get("meta", {})
        wo_kwargs["meta"] = {**user_meta, "_recipe_snapshot": snapshot}

        wo = WorkOrder.objects.create(
            recipe=recipe,
            output_ref=recipe.output_ref,
            quantity=quantity,
            status=WorkOrder.Status.OPEN,
            scheduled_date=date,
            **wo_kwargs,
        )

        WorkOrderEvent.objects.create(
            work_order=wo,
            seq=0,
            kind=WorkOrderEvent.Kind.PLANNED,
            payload={"quantity": str(quantity), "recipe": recipe.code},
            actor=kwargs.get("actor", ""),
        )

        return wo

    @classmethod
    def _plan_batch(cls, items, date, **kwargs):
        """
        Create multiple WorkOrders atomically.

        Signals are emitted after the transaction commits, preventing
        signal leak if a later item fails.
        """
        from shopman.crafting.models import WorkOrder
        from shopman.crafting.signals import production_changed

        orders = []
        with transaction.atomic():
            for recipe, qty in items:
                qty_decimal = Decimal(str(qty))
                if qty_decimal <= 0:
                    raise CraftError("INVALID_QUANTITY", quantity=float(qty_decimal))
                wo = cls._create_work_order(recipe, qty_decimal, date, **kwargs)
                orders.append(wo)

        # Signals emitted after transaction commits successfully
        for wo in orders:
            production_changed.send(
                sender=WorkOrder,
                product_ref=wo.output_ref,
                date=date,
                action="planned",
                work_order=wo,
            )

        return orders

    @classmethod
    def adjust(cls, order, quantity, reason=None, expected_rev=None, actor=None):
        """
        Adjust target quantity of an open WorkOrder.

        N adjustments possible, each generates an event.
        expected_rev is optional (last-write-wins if omitted).
        """
        from shopman.crafting.models import WorkOrder, WorkOrderEvent
        from shopman.crafting.signals import production_changed

        quantity = Decimal(str(quantity))
        if quantity <= 0:
            raise CraftError("INVALID_QUANTITY", quantity=float(quantity))

        with transaction.atomic():
            # Acquire row lock, then refresh caller's object in-place
            WorkOrder.objects.select_for_update().get(pk=order.pk)
            order.refresh_from_db()
            old_quantity = order.quantity

            # Status check (inside transaction, fresh from DB)
            if order.status != WorkOrder.Status.OPEN:
                raise CraftError("TERMINAL_STATUS", status=order.status)

            _check_rev(order, expected_rev)
            order.quantity = quantity
            if order.started_at is None:
                order.started_at = timezone.now()

            update_fields = ["quantity", "started_at", "updated_at"]
            order.save(update_fields=update_fields)
            order.refresh_from_db(fields=["rev"])

            # Atomic seq via row lock
            next_seq = _next_seq(order)
            WorkOrderEvent.objects.create(
                work_order=order,
                seq=next_seq,
                kind=WorkOrderEvent.Kind.ADJUSTED,
                payload={
                    "from": str(old_quantity),
                    "to": str(quantity),
                    "reason": reason or "",
                },
                actor=actor or "",
            )

        production_changed.send(
            sender=WorkOrder,
            product_ref=order.output_ref,
            date=order.scheduled_date,
            action="adjusted",
            work_order=order,
        )

        logger.info("WorkOrder %s adjusted: %s -> %s", order.code, old_quantity, quantity)
        return order
