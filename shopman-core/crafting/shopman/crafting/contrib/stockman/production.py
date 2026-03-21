"""
Production Backend Adapter (vNext).

Implements Stockman's ProductionBackend protocol for Craftsman.
This allows Stockman to request production when stock reaches reorder point.

Uses craft.plan() and craft.void() instead of direct WorkOrder manipulation.
"""

import logging
import threading
from datetime import date, datetime
from decimal import Decimal

from shopman.crafting.exceptions import CraftError

logger = logging.getLogger(__name__)

# Singleton instance
_lock = threading.Lock()
_production_backend = None


class CraftsmanProductionBackend:
    """
    Implements ProductionBackend for Stockman to request production.

    Usage:
        from shopman.crafting.contrib.stockman.production import get_production_backend

        backend = get_production_backend()
        result = backend.request_production(ProductionRequest(
            sku="CROISSANT",
            quantity=Decimal("50"),
            target_date=date(2026, 2, 25),
        ))
    """

    def request_production(self, request) -> "ProductionResult":
        """
        Request production of a product (Protocol-compliant signature).

        Args:
            request: ProductionRequest dataclass from shopman.stocking.protocols.production
        """
        from shopman.stocking.protocols.production import ProductionResult

        sku = request.sku
        qty = request.quantity
        target_date = request.target_date
        metadata = dict(request.metadata) if request.metadata else {}

        if hasattr(request, "priority") and request.priority:
            metadata["priority"] = (
                request.priority.value
                if hasattr(request.priority, "value")
                else str(request.priority)
            )

        if request.reference:
            metadata["reference"] = request.reference

        return self._create_work_order(sku, qty, target_date, metadata)

    def request_production_simple(
        self,
        sku: str,
        qty: Decimal,
        needed_by: datetime | None = None,
        priority: int = 50,
        metadata: dict | None = None,
    ) -> "ProductionResult":
        """Request production — simplified API."""
        combined_metadata = metadata or {}
        combined_metadata["priority"] = priority

        target_date = needed_by.date() if needed_by else None
        return self._create_work_order(sku, qty, target_date, combined_metadata)

    def _create_work_order(
        self,
        sku: str,
        qty: Decimal,
        target_date: date | None,
        metadata: dict | None,
    ) -> "ProductionResult":
        """Internal: create WorkOrder via craft.plan()."""
        from shopman.crafting.models import Recipe
        from shopman.crafting.service import craft
        from shopman.stocking.protocols.production import ProductionResult, ProductionStatusEnum

        try:
            recipe = Recipe.objects.filter(
                output_ref=sku,
                is_active=True,
            ).first()

            if not recipe:
                return ProductionResult(
                    success=False,
                    message=f"No active recipe found for SKU {sku}",
                )

            wo = craft.plan(
                recipe,
                qty,
                date=target_date,
                source_ref="stockman:reorder",
                meta=metadata or {},
            )

            logger.info(
                "Production requested for SKU %s: WorkOrder %s created",
                sku, wo.code,
            )

            return ProductionResult(
                success=True,
                work_order_id=str(wo.pk),
                status=ProductionStatusEnum.SCHEDULED,
                request_id=f"production:{wo.pk}",
            )

        except CraftError as e:
            logger.warning("Production request denied for SKU %s: [%s] %s", sku, e.code, e)
            return ProductionResult(success=False, message=str(e))
        except Exception as e:
            logger.error("Failed to request production for SKU %s: %s", sku, e, exc_info=True)
            return ProductionResult(success=False, message=str(e))

    def check_status(self, request_id: str) -> "ProductionStatus | None":
        """Check status of a production request."""
        from shopman.crafting.models import WorkOrder
        from shopman.stocking.protocols.production import ProductionStatus, ProductionStatusEnum

        try:
            if request_id.startswith("production:"):
                pk = int(request_id.split(":")[1])
                wo = WorkOrder.objects.get(pk=pk)
            else:
                wo = WorkOrder.objects.filter(code=request_id).first()
                if not wo:
                    return None

            status_map = {
                WorkOrder.Status.OPEN: ProductionStatusEnum.SCHEDULED,
                WorkOrder.Status.DONE: ProductionStatusEnum.COMPLETED,
                WorkOrder.Status.VOID: ProductionStatusEnum.CANCELLED,
            }

            return ProductionStatus(
                request_id=f"production:{wo.pk}",
                sku=wo.output_ref,
                quantity=wo.quantity,
                status=status_map.get(wo.status, ProductionStatusEnum.REQUESTED),
                target_date=wo.scheduled_date,
                estimated_completion=None,
                work_order_id=str(wo.pk),
            )
        except WorkOrder.DoesNotExist:
            return None

    def cancel_request(
        self, request_id: str, reason: str = "cancelled"
    ) -> "ProductionResult":
        """Cancel a production request via craft.void()."""
        from shopman.crafting.models import WorkOrder
        from shopman.crafting.service import craft
        from shopman.stocking.protocols.production import ProductionResult, ProductionStatusEnum

        try:
            if request_id.startswith("production:"):
                pk = int(request_id.split(":")[1])
                wo = WorkOrder.objects.get(pk=pk)
            else:
                wo = WorkOrder.objects.filter(code=request_id).first()
                if not wo:
                    return ProductionResult(
                        success=False,
                        message=f"WorkOrder {request_id} not found",
                    )

            craft.void(wo, reason=reason, actor="stockman:cancel")
            logger.info("Production request %s cancelled: %s", wo.code, reason)

            return ProductionResult(
                success=True,
                request_id=request_id,
                status=ProductionStatusEnum.CANCELLED,
                work_order_id=str(wo.pk),
            )
        except WorkOrder.DoesNotExist:
            return ProductionResult(
                success=False,
                message=f"WorkOrder {request_id} not found",
            )
        except CraftError as e:
            logger.warning("Cannot cancel WorkOrder %s: [%s] %s", request_id, e.code, e)
            return ProductionResult(success=False, message=str(e))
        except Exception as e:
            logger.error("Failed to cancel WorkOrder %s: %s", request_id, e, exc_info=True)
            return ProductionResult(success=False, message=str(e))

    def list_pending(
        self,
        sku: str | None = None,
        target_date: date | None = None,
    ) -> list["ProductionStatus"]:
        """List pending production requests."""
        from shopman.crafting.models import WorkOrder
        from shopman.stocking.protocols.production import ProductionStatus, ProductionStatusEnum

        qs = WorkOrder.objects.filter(
            status=WorkOrder.Status.OPEN,
            source_ref__startswith="stockman:",
        )

        if sku:
            qs = qs.filter(output_ref=sku)

        if target_date:
            qs = qs.filter(scheduled_date=target_date)

        results = []
        for wo in qs:
            results.append(
                ProductionStatus(
                    request_id=f"production:{wo.pk}",
                    sku=wo.output_ref,
                    quantity=wo.quantity,
                    status=ProductionStatusEnum.SCHEDULED,
                    target_date=wo.scheduled_date,
                    estimated_completion=None,
                    work_order_id=str(wo.pk),
                )
            )

        return results


def get_production_backend() -> CraftsmanProductionBackend:
    """Get the production backend instance (singleton)."""
    global _production_backend
    if _production_backend is None:
        with _lock:
            if _production_backend is None:
                _production_backend = CraftsmanProductionBackend()
    return _production_backend


def reset_production_backend():
    """Reset the singleton (useful for testing)."""
    global _production_backend
    _production_backend = None
