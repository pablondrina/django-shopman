"""
Execution service — close and void operations.

All methods are @classmethod (mixin pattern).
"""

import logging
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from shopman.craftsman.exceptions import CraftError
from shopman.craftsman.services.scheduling import _check_rev, _next_seq

logger = logging.getLogger(__name__)


class CraftExecution:
    """Close and void operations."""

    @classmethod
    def close(cls, order, produced, consumed=None, wasted=None,
              expected_rev=None, actor=None, idempotency_key=None):
        """
        Close a WorkOrder with production results.

        Progressive disclosure:
            produced=93             -> single output (Decimal)
            produced=[{...}, ...]   -> co-products (list)
            consumed=None           -> auto from requirements
            consumed=[{...}, ...]   -> explicit consumption
            wasted=None             -> auto (quantity - produced)
            wasted=5                -> explicit single waste
            wasted=[{...}, ...]     -> detailed waste items
        """
        from shopman.craftsman.models import WorkOrder, WorkOrderEvent, WorkOrderItem
        from shopman.craftsman.signals import production_changed

        # Normalize produced (pure computation, safe outside transaction)
        if isinstance(produced, (int, float, Decimal)):
            produced_decimal = Decimal(str(produced))
            produced_items = None
        else:
            produced_items = produced
            produced_decimal = sum(Decimal(str(p["quantity"])) for p in produced)

        if produced_decimal < 0:
            raise CraftError("INVALID_QUANTITY", quantity=float(produced_decimal))

        with transaction.atomic():
            # Acquire row lock, then refresh caller's object in-place
            WorkOrder.objects.select_for_update().get(pk=order.pk)
            order.refresh_from_db()

            # Idempotency check (inside transaction, after lock)
            if idempotency_key:
                existing = WorkOrderEvent.objects.filter(
                    idempotency_key=idempotency_key,
                ).select_related("work_order").first()
                if existing:
                    return existing.work_order

            # Status check (inside transaction, fresh from DB)
            if order.status != WorkOrder.Status.OPEN:
                raise CraftError("TERMINAL_STATUS", status=order.status)

            # Rev check
            _check_rev(order, expected_rev)

            # 5. Timestamps
            now = timezone.now()
            if order.started_at is None:
                order.started_at = now

            recipe = order.recipe

            # 6. Materialize requirements (French coefficient)
            # Use BOM snapshot from plan-time if available (v0.2.2+),
            # otherwise fall back to current recipe items (backward compat).
            snapshot = order.meta.get("_recipe_snapshot") if order.meta else None
            if snapshot:
                batch_size = Decimal(snapshot["batch_size"])
                coefficient = order.quantity / batch_size
                recipe_item_data = snapshot["items"]
            else:
                coefficient = order.quantity / recipe.batch_size
                recipe_item_data = [
                    {"input_ref": ri.input_ref, "quantity": str(ri.quantity), "unit": ri.unit}
                    for ri in recipe.items.filter(is_optional=False).order_by("sort_order")
                ]

            # Build all ledger items, then bulk_create for efficiency.
            all_items = []
            requirements = []

            for item_data in recipe_item_data:
                req_qty = Decimal(item_data["quantity"]) * coefficient
                requirements.append({
                    "item_ref": item_data["input_ref"],
                    "quantity": req_qty,
                    "unit": item_data["unit"],
                })
                all_items.append(WorkOrderItem(
                    work_order=order,
                    kind=WorkOrderItem.Kind.REQUIREMENT,
                    item_ref=item_data["input_ref"],
                    quantity=req_qty,
                    unit=item_data["unit"],
                    recorded_at=now,
                    recorded_by=actor or "",
                ))

            # 7. Consumption items (with optional validation)
            if consumed is not None:
                recipe_refs = {r["item_ref"] for r in requirements}
                for c in consumed:
                    if c["item_ref"] not in recipe_refs:
                        logger.warning(
                            "WorkOrder %s: consumed item_ref '%s' not in recipe (substitution?)",
                            order.ref, c["item_ref"],
                        )

            if consumed is None:
                # Auto: consumption = requirements
                for req in requirements:
                    all_items.append(WorkOrderItem(
                        work_order=order,
                        kind=WorkOrderItem.Kind.CONSUMPTION,
                        item_ref=req["item_ref"],
                        quantity=req["quantity"],
                        unit=req["unit"],
                        recorded_at=now,
                        recorded_by=actor or "",
                    ))
            else:
                for c in consumed:
                    all_items.append(WorkOrderItem(
                        work_order=order,
                        kind=WorkOrderItem.Kind.CONSUMPTION,
                        item_ref=c["item_ref"],
                        quantity=Decimal(str(c["quantity"])),
                        unit=c.get("unit", ""),
                        recorded_at=now,
                        recorded_by=actor or "",
                        meta=c.get("meta", {}),
                    ))

            # 8. Output items
            if produced_items is None:
                all_items.append(WorkOrderItem(
                    work_order=order,
                    kind=WorkOrderItem.Kind.OUTPUT,
                    item_ref=order.output_ref,
                    quantity=produced_decimal,
                    unit="",
                    recorded_at=now,
                    recorded_by=actor or "",
                ))
            else:
                for p in produced_items:
                    all_items.append(WorkOrderItem(
                        work_order=order,
                        kind=WorkOrderItem.Kind.OUTPUT,
                        item_ref=p["item_ref"],
                        quantity=Decimal(str(p["quantity"])),
                        unit=p.get("unit", ""),
                        recorded_at=now,
                        recorded_by=actor or "",
                    ))

            # 9. Waste items
            if wasted is None:
                auto_waste = order.quantity - produced_decimal
                if auto_waste > 0:
                    all_items.append(WorkOrderItem(
                        work_order=order,
                        kind=WorkOrderItem.Kind.WASTE,
                        item_ref=order.output_ref,
                        quantity=auto_waste,
                        unit="",
                        recorded_at=now,
                        recorded_by=actor or "",
                    ))
            elif isinstance(wasted, (int, float, Decimal)):
                waste_decimal = Decimal(str(wasted))
                if waste_decimal > 0:
                    all_items.append(WorkOrderItem(
                        work_order=order,
                        kind=WorkOrderItem.Kind.WASTE,
                        item_ref=order.output_ref,
                        quantity=waste_decimal,
                        unit="",
                        recorded_at=now,
                        recorded_by=actor or "",
                    ))
            else:
                for w in wasted:
                    all_items.append(WorkOrderItem(
                        work_order=order,
                        kind=WorkOrderItem.Kind.WASTE,
                        item_ref=w["item_ref"],
                        quantity=Decimal(str(w["quantity"])),
                        unit=w.get("unit", ""),
                        recorded_at=now,
                        recorded_by=actor or "",
                        meta=w.get("meta", {}),
                    ))

            WorkOrderItem.objects.bulk_create(all_items)

            # 10. Update WorkOrder
            order.produced = produced_decimal
            order.status = WorkOrder.Status.DONE
            order.finished_at = now
            order.save(update_fields=[
                "produced", "status", "finished_at", "started_at", "updated_at",
            ])

            # Create event (atomic seq via row lock)
            next_seq = _next_seq(order)
            WorkOrderEvent.objects.create(
                work_order=order,
                seq=next_seq,
                kind=WorkOrderEvent.Kind.CLOSED,
                payload={
                    "produced": str(produced_decimal),
                    "quantity": str(order.quantity),
                },
                actor=actor or "",
                idempotency_key=idempotency_key,
            )

            # 12. InventoryProtocol (stub — Phase D)
            cls._call_inventory_on_close(order, requirements, produced_decimal)

        # 13. Signal (outside transaction)
        production_changed.send(
            sender=WorkOrder,
            product_ref=order.output_ref,
            date=order.scheduled_date,
            action="closed",
            work_order=order,
        )

        logger.info("WorkOrder %s closed: produced=%s", order.ref, produced_decimal)
        return order

    @classmethod
    def void(cls, order, reason, expected_rev=None, actor=None):
        """Void (cancel) an open WorkOrder."""
        from shopman.craftsman.models import WorkOrder, WorkOrderEvent
        from shopman.craftsman.signals import production_changed

        with transaction.atomic():
            # Acquire row lock, then refresh caller's object in-place
            WorkOrder.objects.select_for_update().get(pk=order.pk)
            order.refresh_from_db()

            # Status check (inside transaction, fresh from DB)
            if order.status == WorkOrder.Status.DONE:
                raise CraftError("VOID_FROM_DONE", work_order=order.ref)
            if order.status != WorkOrder.Status.OPEN:
                raise CraftError("TERMINAL_STATUS", status=order.status)

            _check_rev(order, expected_rev)

            order.status = WorkOrder.Status.VOID
            order.save(update_fields=["status", "updated_at"])

            # Atomic seq via row lock
            next_seq = _next_seq(order)
            WorkOrderEvent.objects.create(
                work_order=order,
                seq=next_seq,
                kind=WorkOrderEvent.Kind.VOIDED,
                payload={"reason": reason},
                actor=actor or "",
            )

            # InventoryProtocol.release (stub — Phase D)
            cls._call_inventory_on_void(order)

        production_changed.send(
            sender=WorkOrder,
            product_ref=order.output_ref,
            date=order.scheduled_date,
            action="voided",
            work_order=order,
        )

        logger.info("WorkOrder %s voided: %s", order.ref, reason)
        return order

    @classmethod
    def _call_inventory_on_close(cls, order, requirements, produced_decimal):
        """
        Call InventoryProtocol.consume + receive if configured.

        In MODE=graceful (default): logs warning on failure, does not raise.
        In MODE=strict: re-raises the exception, aborting the operation.
        """
        from shopman.craftsman.conf import get_setting

        backend_path = get_setting("INVENTORY_BACKEND")
        if not backend_path:
            return  # standalone mode

        try:
            from django.utils.module_loading import import_string
            from shopman.craftsman.protocols.inventory import MaterialProduced, MaterialUsed

            backend = import_string(backend_path)()

            consumed = [
                MaterialUsed(sku=r["item_ref"], quantity=r["quantity"])
                for r in requirements
            ]
            backend.consume(consumed, ref=order.ref)

            backend.receive(
                [MaterialProduced(sku=order.output_ref, quantity=produced_decimal)],
                ref=order.ref,
            )

        except Exception as e:
            mode = get_setting("MODE")
            if mode == "strict":
                from shopman.craftsman.exceptions import CraftError
                raise CraftError(
                    code="inventory_backend_failed",
                    message=f"InventoryProtocol.close failed for {order.ref}: {e}",
                    context={"order_ref": order.ref, "original_error": str(e)},
                ) from e
            logger.warning(
                "InventoryProtocol.close failed for %s: %s (non-fatal)",
                order.ref, e, exc_info=True,
            )

    @classmethod
    def _call_inventory_on_void(cls, order):
        """
        Call InventoryProtocol.release if configured.

        In MODE=graceful (default): logs warning on failure, does not raise.
        In MODE=strict: re-raises the exception, aborting the operation.
        """
        from shopman.craftsman.conf import get_setting

        backend_path = get_setting("INVENTORY_BACKEND")
        if not backend_path:
            return  # standalone mode

        try:
            from django.utils.module_loading import import_string

            backend = import_string(backend_path)()
            backend.release(ref=order.ref)

        except Exception as e:
            mode = get_setting("MODE")
            if mode == "strict":
                from shopman.craftsman.exceptions import CraftError
                raise CraftError(
                    code="inventory_backend_failed",
                    message=f"InventoryProtocol.release failed for {order.ref}: {e}",
                    context={"order_ref": order.ref, "original_error": str(e)},
                ) from e
            logger.warning(
                "InventoryProtocol.release failed for %s: %s (non-fatal)",
                order.ref, e, exc_info=True,
            )
