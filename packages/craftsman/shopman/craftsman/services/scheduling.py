"""
Planning service — plan and adjust operations.

All methods are @classmethod (mixin pattern, like Stockman).
"""

import logging
from decimal import Decimal

from django.db import models, transaction
from django.utils import timezone
from shopman.craftsman.exceptions import CraftError, StaleRevision

logger = logging.getLogger(__name__)


def _check_rev(order, expected_rev):
    """
    Optimistic concurrency check.

    If expected_rev is provided, atomically check and bump.
    If not provided, just bump rev.
    """
    from shopman.craftsman.models import WorkOrder

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

        from shopman.craftsman.models import WorkOrder
        from shopman.craftsman.signals import production_changed

        with transaction.atomic():
            wo = cls._create_work_order(recipe, quantity, date, **kwargs)

        production_changed.send(
            sender=WorkOrder,
            product_ref=wo.output_sku,
            date=date,
            action="planned",
            work_order=wo,
        )

        logger.info("WorkOrder %s planned: %s x %s", wo.ref, quantity, recipe.output_sku)
        return wo

    @classmethod
    def _create_work_order(cls, recipe, quantity, date, **kwargs):
        """
        Create WorkOrder + planned event + BOM snapshot (no signal).

        Used by plan() and _plan_batch(). Must be called inside
        transaction.atomic().

        The BOM snapshot freezes recipe items at plan time so that
        finish() uses the recipe as-it-was, not as-it-is-now.
        """
        from shopman.craftsman.models import WorkOrder, WorkOrderEvent

        wo_kwargs = {}
        for key in ("source_ref", "position_ref", "operator_ref", "meta"):
            if key in kwargs:
                wo_kwargs[key] = kwargs[key]

        # Freeze BOM into meta._recipe_snapshot
        snapshot = {
            "batch_size": str(recipe.batch_size),
            "items": [
                {"input_sku": ri.input_sku, "quantity": str(ri.quantity), "unit": ri.unit}
                for ri in recipe.items.filter(is_optional=False).order_by("sort_order")
            ],
        }
        user_meta = wo_kwargs.get("meta", {})
        wo_kwargs["meta"] = {**user_meta, "_recipe_snapshot": snapshot}

        wo = WorkOrder.objects.create(
            recipe=recipe,
            output_sku=recipe.output_sku,
            quantity=quantity,
            status=WorkOrder.Status.PLANNED,
            target_date=date,
            **wo_kwargs,
        )

        WorkOrderEvent.objects.create(
            work_order=wo,
            seq=0,
            kind=WorkOrderEvent.Kind.PLANNED,
            payload={
                "quantity": str(quantity),
                "recipe": recipe.ref,
                "output_sku": recipe.output_sku,
                "target_date": str(date) if date else None,
                "source_ref": wo.source_ref,
                "position_ref": wo.position_ref,
                "operator_ref": wo.operator_ref,
            },
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
        from shopman.craftsman.models import WorkOrder
        from shopman.craftsman.signals import production_changed

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
                product_ref=wo.output_sku,
                date=date,
                action="planned",
                work_order=wo,
            )

        return orders

    @classmethod
    def adjust(cls, order, quantity, reason=None, expected_rev=None, actor=None, force=False):
        """
        Adjust target quantity of a planned WorkOrder.

        N adjustments possible, each generates an event.
        expected_rev is optional (last-write-wins if omitted).

        quantity=0: voids the WorkOrder instead of adjusting.
        force=False: raise CraftError("DOWNSTREAM_DEFICIT") if reducing a
            shared-ingredient WO creates shortage for downstream WOs.
            force=True: allow with warning.
        """
        from shopman.craftsman.models import WorkOrder, WorkOrderEvent
        from shopman.craftsman.signals import production_changed

        quantity = Decimal(str(quantity))
        if quantity < 0:
            raise CraftError("INVALID_QUANTITY", quantity=float(quantity))

        # V3: quantity=0 → void
        if quantity == Decimal("0"):
            return cls.void(order, reason=reason or "Remanejo: zerado", expected_rev=expected_rev, actor=actor)

        with transaction.atomic():
            # Acquire row lock, then refresh caller's object in-place
            WorkOrder.objects.select_for_update().get(pk=order.pk)
            order.refresh_from_db()
            old_quantity = order.quantity

            # Status check (inside transaction, fresh from DB)
            if order.status != WorkOrder.Status.PLANNED:
                raise CraftError("INVALID_STATUS", current=order.status, expected=WorkOrder.Status.PLANNED)

            _check_rev(order, expected_rev)

            # V1: validate committed holds (graceful if DEMAND_BACKEND not configured)
            _validate_committed_holds(order, quantity)

            # V2: validate shared ingredient availability (graceful if INVENTORY_BACKEND not configured)
            _validate_shared_ingredients(order, quantity)

            # V3 (downstream): check if reducing a shared-input WO creates deficit
            _validate_downstream_deficit(order, quantity, force=force)

            order.quantity = quantity
            update_fields = ["quantity", "updated_at"]
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
            product_ref=order.output_sku,
            date=order.target_date,
            action="adjusted",
            work_order=order,
        )

        logger.info("WorkOrder %s adjusted: %s -> %s", order.ref, old_quantity, quantity)
        return order

    @classmethod
    def start(
        cls,
        order,
        quantity,
        *,
        expected_rev=None,
        actor=None,
        operator_ref=None,
        position_ref=None,
        note=None,
    ):
        """
        Mark a WorkOrder as started with the quantity that entered production.
        """
        from shopman.craftsman.models import WorkOrder, WorkOrderEvent
        from shopman.craftsman.signals import production_changed

        quantity = Decimal(str(quantity))
        if quantity <= 0:
            raise CraftError("INVALID_QUANTITY", quantity=float(quantity))

        with transaction.atomic():
            WorkOrder.objects.select_for_update().get(pk=order.pk)
            order.refresh_from_db()

            if order.status != WorkOrder.Status.PLANNED:
                raise CraftError("INVALID_STATUS", current=order.status, expected=WorkOrder.Status.PLANNED)

            _check_rev(order, expected_rev)

            now = timezone.now()
            if order.started_at is None:
                order.started_at = now
            order.status = WorkOrder.Status.STARTED
            if operator_ref is not None:
                order.operator_ref = operator_ref
            if position_ref is not None:
                order.position_ref = position_ref

            order.save(update_fields=["started_at", "status", "operator_ref", "position_ref", "updated_at"])

            next_seq = _next_seq(order)
            WorkOrderEvent.objects.create(
                work_order=order,
                seq=next_seq,
                kind=WorkOrderEvent.Kind.STARTED,
                payload={
                    "quantity": str(quantity),
                    "operator_ref": order.operator_ref,
                    "position_ref": order.position_ref,
                    "note": note or "",
                },
                actor=actor or "",
            )

        production_changed.send(
            sender=WorkOrder,
            product_ref=order.output_sku,
            date=order.target_date,
            action="started",
            work_order=order,
        )

        logger.info("WorkOrder %s started", order.ref)
        return order


# ── Adjust validation helpers ──────────────────────────────────────────────────


def _validate_committed_holds(order, new_quantity: Decimal) -> None:
    """
    V1: Raise CraftError("COMMITTED_HOLDS") if new_quantity is below committed orders.

    Graceful: skipped if DEMAND_BACKEND is not configured or raises.
    """
    try:
        from shopman.craftsman.conf import get_setting

        backend_path = get_setting("DEMAND_BACKEND")
        if not backend_path:
            return

        from django.utils.module_loading import import_string

        backend = import_string(backend_path)()
        committed = backend.committed(order.output_sku, order.target_date)

        if new_quantity < committed:
            raise CraftError(
                "COMMITTED_HOLDS",
                committed=float(committed),
                requested=float(new_quantity),
                message=f"Há {committed} unidades comprometidas em encomendas",
            )
    except CraftError:
        raise
    except Exception as e:
        from shopman.craftsman.conf import get_setting
        mode = get_setting("MODE")
        if mode == "strict":
            raise CraftError(
                "DEMAND_BACKEND_FAILED",
                message=f"Demand backend failed during validation: {e}",
            ) from e
        # graceful: no backend or unavailable → skip


def _validate_shared_ingredients(order, new_quantity: Decimal) -> None:
    """
    V2: Raise CraftError("INSUFFICIENT_MATERIALS") if shared ingredients are insufficient.

    Checks total ingredient consumption across all active WOs on the same date
    against what's available. Graceful: skipped if INVENTORY_BACKEND is not configured.
    """
    try:
        from shopman.craftsman.conf import get_setting

        inv_path = get_setting("INVENTORY_BACKEND")
        if not inv_path:
            return

        from django.utils.module_loading import import_string
        from shopman.craftsman.models import WorkOrder
        from shopman.craftsman.protocols.inventory import MaterialNeed

        recipe = order.recipe
        coefficient_new = new_quantity / recipe.batch_size

        # Own new ingredient needs
        own_needs: dict[str, Decimal] = {}
        for ri in recipe.items.filter(is_optional=False):
            own_needs[ri.input_sku] = ri.quantity * coefficient_new

        if not own_needs:
            return

        # Other WOs on same date
        other_wos = (
            WorkOrder.objects.filter(
                status__in=[WorkOrder.Status.PLANNED, WorkOrder.Status.STARTED],
                target_date=order.target_date,
            )
            .exclude(pk=order.pk)
            .select_related("recipe")
            .prefetch_related("recipe__items")
        )

        other_needs: dict[str, Decimal] = {}
        for other in other_wos:
            other_coeff = other.quantity / other.recipe.batch_size
            for ri in other.recipe.items.filter(is_optional=False):
                if ri.input_sku in own_needs:
                    other_needs[ri.input_sku] = (
                        other_needs.get(ri.input_sku, Decimal("0"))
                        + ri.quantity * other_coeff
                    )

        # Check availability for shared ingredients only
        shared_refs = set(own_needs) & set(other_needs) | set(own_needs)
        material_needs = [
            MaterialNeed(sku=ref, quantity=own_needs.get(ref, Decimal("0")) + other_needs.get(ref, Decimal("0")))
            for ref in shared_refs
        ]

        inv_backend = import_string(inv_path)()
        result = inv_backend.available(material_needs)

        if not result.all_available:
            shortages = [
                {"sku": ms.sku, "needed": float(ms.needed), "available": float(ms.available)}
                for ms in result.materials
                if not ms.sufficient
            ]
            raise CraftError("INSUFFICIENT_MATERIALS", shortages=shortages)

    except CraftError:
        raise
    except Exception as e:
        from shopman.craftsman.conf import get_setting
        mode = get_setting("MODE")
        if mode == "strict":
            raise CraftError(
                "INVENTORY_BACKEND_FAILED",
                message=f"Inventory backend failed during validation: {e}",
            ) from e
        # graceful: backend unavailable → skip


def _validate_downstream_deficit(order, new_quantity: Decimal, *, force: bool) -> None:
    """
    V3 (downstream): If this WO's output_sku is used as input_sku by other active
    recipes, check if reducing will create ingredient shortage for other active WOs.

    force=False → raise CraftError("DOWNSTREAM_DEFICIT") if deficit found.
    force=True  → log warning and proceed.

    Graceful: skipped if an unexpected error occurs.
    """
    try:
        from shopman.craftsman.models import Recipe, WorkOrder

        # Is this WO's output used as an input in other recipes?
        downstream_recipes = list(
            Recipe.objects.filter(
                items__input_sku=order.output_sku,
                is_active=True,
            )
            .distinct()
            .prefetch_related("items")
        )
        if not downstream_recipes:
            return

        # How much will this WO produce (new vs old)?
        old_qty = order.quantity  # already refreshed from DB
        delta = new_quantity - old_qty  # negative = reducing
        if delta >= 0:
            return  # increasing or same → no deficit risk

        # Reduction amount
        reduction = abs(delta)

        # Check downstream WOs on the same date that need this ingredient
        deficit_items = []
        downstream_wos = (
            WorkOrder.objects.filter(
                status__in=[WorkOrder.Status.PLANNED, WorkOrder.Status.STARTED],
                target_date=order.target_date,
                recipe__in=downstream_recipes,
            )
            .exclude(pk=order.pk)
            .select_related("recipe")
            .prefetch_related("recipe__items")
        )

        for downstream_wo in downstream_wos:
            coeff = downstream_wo.quantity / downstream_wo.recipe.batch_size
            for ri in downstream_wo.recipe.items.filter(input_sku=order.output_sku):
                total_needed = ri.quantity * coeff
                # This WO was supposed to provide some of the supply; reduction reduces it
                if total_needed > 0:
                    shortage = min(reduction, total_needed)
                    deficit_items.append({
                        "wo_ref": downstream_wo.ref,
                        "sku": order.output_sku,
                        "shortage": float(shortage),
                    })

        if not deficit_items:
            return

        if force:
            logger.warning(
                "WorkOrder %s adjusted with downstream deficit: %s",
                order.ref,
                deficit_items,
            )
        else:
            raise CraftError(
                "DOWNSTREAM_DEFICIT",
                deficit=deficit_items,
                message="Insumo insuficiente para produção planejada",
            )

    except CraftError:
        raise
    except Exception:
        pass  # graceful
