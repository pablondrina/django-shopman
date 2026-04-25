"""
Execution service — finish and void operations.

All methods are @classmethod (mixin pattern).
"""

import logging
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from shopman.craftsman.exceptions import CraftError
from shopman.craftsman.services.scheduling import _check_rev, _next_seq

logger = logging.getLogger(__name__)


def _positive_decimal(value, *, field: str = "quantity") -> Decimal:
    try:
        quantity = Decimal(str(value))
    except Exception as exc:
        raise CraftError("INVALID_QUANTITY", field=field, quantity=value) from exc
    if quantity <= 0:
        raise CraftError("INVALID_QUANTITY", field=field, quantity=float(quantity))
    return quantity


def _required_ref(value, *, field: str) -> str:
    ref = str(value or "").strip()
    if not ref:
        raise CraftError("INVALID_REF", field=field)
    return ref


def _mapping_item(value, *, field: str) -> dict:
    if not isinstance(value, dict):
        raise CraftError("INVALID_PAYLOAD", field=field)
    return value


class CraftExecution:
    """Finish and void operations."""

    @classmethod
    def finish(
        cls,
        order,
        finished,
        *,
        consumed=None,
        wasted=None,
        expected_rev=None,
        actor=None,
        note=None,
        idempotency_key=None,
    ):
        """
        Finish a WorkOrder with final production results.
        """
        from shopman.craftsman.models import WorkOrder, WorkOrderEvent
        from shopman.craftsman.signals import production_changed

        # Normalize finished quantity (pure computation, safe outside transaction)
        if isinstance(finished, (int, float, Decimal, str)):
            finished_decimal = _positive_decimal(finished, field="finished")
            finished_items = None
        else:
            finished_items = finished
            if not finished_items:
                raise CraftError("INVALID_QUANTITY", field="finished")
            finished_decimal = Decimal("0")
            for p in finished_items:
                p = _mapping_item(p, field="finished")
                finished_decimal += _positive_decimal(p.get("quantity"), field="finished.quantity")

        with transaction.atomic():
            WorkOrder.objects.select_for_update().get(pk=order.pk)
            order.refresh_from_db()

            if idempotency_key:
                existing = WorkOrderEvent.objects.filter(
                    idempotency_key=idempotency_key,
                ).select_related("work_order").first()
                if existing:
                    if existing.work_order_id != order.pk:
                        raise CraftError(
                            "IDEMPOTENCY_CONFLICT",
                            idempotency_key=idempotency_key,
                            work_order=order.ref,
                            existing_work_order=existing.work_order.ref,
                        )
                    return existing.work_order

            if order.status == WorkOrder.Status.FINISHED:
                raise CraftError("TERMINAL_STATUS", status=order.status)
            if order.status == WorkOrder.Status.VOID:
                raise CraftError("TERMINAL_STATUS", status=order.status)

            _check_rev(order, expected_rev)

            now = timezone.now()
            if order.started_at is None:
                order.started_at = now

            if order.status == WorkOrder.Status.PLANNED:
                implicit_started_qty = order.quantity
                next_seq = _next_seq(order)
                WorkOrderEvent.objects.create(
                    work_order=order,
                    seq=next_seq,
                    kind=WorkOrderEvent.Kind.STARTED,
                    payload={
                        "quantity": str(implicit_started_qty),
                        "operator_ref": order.operator_ref,
                        "position_ref": order.position_ref,
                        "note": note or "",
                        "implicit": True,
                    },
                    actor=actor or "",
                )
                order.status = WorkOrder.Status.STARTED
                order.save(update_fields=["started_at", "status", "updated_at"])

            recipe = order.recipe
            started_qty = order.started_qty or order.quantity

            snapshot = order.meta.get("_recipe_snapshot") if order.meta else None
            if snapshot:
                batch_size = Decimal(snapshot["batch_size"])
                coefficient = started_qty / batch_size
                recipe_item_data = snapshot["items"]
            else:
                coefficient = started_qty / recipe.batch_size
                recipe_item_data = [
                    {"input_sku": ri.input_sku, "quantity": str(ri.quantity), "unit": ri.unit}
                    for ri in recipe.items.filter(is_optional=False).order_by("sort_order")
                ]

            from shopman.craftsman.models import WorkOrderItem

            all_items = []
            requirements = []

            for item_data in recipe_item_data:
                req_qty = Decimal(item_data["quantity"]) * coefficient
                requirements.append({
                    "item_ref": item_data["input_sku"],
                    "quantity": req_qty,
                    "unit": item_data["unit"],
                })
                all_items.append(WorkOrderItem(
                    work_order=order,
                    kind=WorkOrderItem.Kind.REQUIREMENT,
                    item_ref=item_data["input_sku"],
                    quantity=req_qty,
                    unit=item_data["unit"],
                    recorded_at=now,
                    recorded_by=actor or "",
                ))

            if consumed is not None:
                recipe_refs = {r["item_ref"] for r in requirements}
                for c in consumed:
                    if c["item_ref"] not in recipe_refs:
                        logger.warning(
                            "WorkOrder %s: consumed item_ref '%s' not in recipe (substitution?)",
                            order.ref, c["item_ref"],
                        )

            if consumed is None:
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
                    c = _mapping_item(c, field="consumed")
                    consumed_ref = _required_ref(c.get("item_ref"), field="consumed.item_ref")
                    consumed_quantity = _positive_decimal(c.get("quantity"), field="consumed.quantity")
                    all_items.append(WorkOrderItem(
                        work_order=order,
                        kind=WorkOrderItem.Kind.CONSUMPTION,
                        item_ref=consumed_ref,
                        quantity=consumed_quantity,
                        unit=c.get("unit", ""),
                        recorded_at=now,
                        recorded_by=actor or "",
                        meta=c.get("meta", {}),
                    ))

            if finished_items is None:
                all_items.append(WorkOrderItem(
                    work_order=order,
                    kind=WorkOrderItem.Kind.OUTPUT,
                    item_ref=order.output_sku,
                    quantity=finished_decimal,
                    unit="",
                    recorded_at=now,
                    recorded_by=actor or "",
                ))
            else:
                for p in finished_items:
                    p = _mapping_item(p, field="finished")
                    output_ref = _required_ref(p.get("item_ref"), field="finished.item_ref")
                    output_quantity = _positive_decimal(p.get("quantity"), field="finished.quantity")
                    all_items.append(WorkOrderItem(
                        work_order=order,
                        kind=WorkOrderItem.Kind.OUTPUT,
                        item_ref=output_ref,
                        quantity=output_quantity,
                        unit=p.get("unit", ""),
                        recorded_at=now,
                        recorded_by=actor or "",
                    ))

            if wasted is None:
                auto_waste = started_qty - finished_decimal
                if auto_waste > 0:
                    all_items.append(WorkOrderItem(
                        work_order=order,
                        kind=WorkOrderItem.Kind.WASTE,
                        item_ref=order.output_sku,
                        quantity=auto_waste,
                        unit="",
                        recorded_at=now,
                        recorded_by=actor or "",
                    ))
            elif isinstance(wasted, (int, float, Decimal, str)):
                waste_decimal = _positive_decimal(wasted, field="wasted")
                all_items.append(WorkOrderItem(
                    work_order=order,
                    kind=WorkOrderItem.Kind.WASTE,
                    item_ref=order.output_sku,
                    quantity=waste_decimal,
                    unit="",
                    recorded_at=now,
                    recorded_by=actor or "",
                ))
            else:
                for w in wasted:
                    w = _mapping_item(w, field="wasted")
                    waste_ref = _required_ref(w.get("item_ref"), field="wasted.item_ref")
                    waste_quantity = _positive_decimal(w.get("quantity"), field="wasted.quantity")
                    all_items.append(WorkOrderItem(
                        work_order=order,
                        kind=WorkOrderItem.Kind.WASTE,
                        item_ref=waste_ref,
                        quantity=waste_quantity,
                        unit=w.get("unit", ""),
                        recorded_at=now,
                        recorded_by=actor or "",
                        meta=w.get("meta", {}),
                    ))

            waste_total = sum(
                item.quantity for item in all_items if item.kind == WorkOrderItem.Kind.WASTE
            )
            WorkOrderItem.objects.bulk_create(all_items)

            order.finished = finished_decimal
            order.status = WorkOrder.Status.FINISHED
            order.finished_at = now
            order.save(update_fields=[
                "finished", "status", "finished_at", "started_at", "updated_at",
            ])

            next_seq = _next_seq(order)
            WorkOrderEvent.objects.create(
                work_order=order,
                seq=next_seq,
                kind=WorkOrderEvent.Kind.FINISHED,
                payload={
                    "finished_qty": str(finished_decimal),
                    "planned_qty": str(order.quantity),
                    "started_qty": str(started_qty),
                    "loss_qty": str(waste_total),
                    "output_sku": order.output_sku,
                    "target_date": str(order.target_date) if order.target_date else None,
                    "source_ref": order.source_ref,
                    "position_ref": order.position_ref,
                    "operator_ref": order.operator_ref,
                },
                actor=actor or "",
                idempotency_key=idempotency_key,
            )

            cls._call_inventory_on_finish(order, requirements, finished_decimal)

        production_changed.send(
            sender=WorkOrder,
            product_ref=order.output_sku,
            date=order.target_date,
            action="finished",
            work_order=order,
        )

        logger.info("WorkOrder %s finished: finished_qty=%s", order.ref, finished_decimal)
        return order

    @classmethod
    def void(cls, order, reason, expected_rev=None, actor=None):
        """Void (cancel) a non-finished WorkOrder."""
        from shopman.craftsman.models import WorkOrder, WorkOrderEvent
        from shopman.craftsman.signals import production_changed

        with transaction.atomic():
            # Acquire row lock, then refresh caller's object in-place
            WorkOrder.objects.select_for_update().get(pk=order.pk)
            order.refresh_from_db()

            # Status check (inside transaction, fresh from DB)
            if order.status == WorkOrder.Status.FINISHED:
                raise CraftError("VOID_FROM_DONE", work_order=order.ref)
            if order.status == WorkOrder.Status.VOID:
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
            product_ref=order.output_sku,
            date=order.target_date,
            action="voided",
            work_order=order,
        )

        logger.info("WorkOrder %s voided: %s", order.ref, reason)
        return order

    @classmethod
    def _call_inventory_on_finish(cls, order, requirements, produced_decimal):
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
                [MaterialProduced(sku=order.output_sku, quantity=produced_decimal)],
                ref=order.ref,
            )

        except Exception as e:
            mode = get_setting("MODE")
            if mode == "strict":
                from shopman.craftsman.exceptions import CraftError
                raise CraftError(
                    code="inventory_backend_failed",
                    message=f"InventoryProtocol.finish failed for {order.ref}: {e}",
                    context={"order_ref": order.ref, "original_error": str(e)},
                ) from e
            logger.warning(
                "InventoryProtocol.finish failed for %s: %s (non-fatal)",
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
