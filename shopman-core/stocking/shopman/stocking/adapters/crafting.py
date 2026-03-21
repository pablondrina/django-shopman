"""
Crafting Backend.

Implements ProductionBackend using Crafting's API (craft.*, work.*).

Vocabulary mapping:
    Stocking                →  Crafting
    ─────────────────────────────────────────
    request_production()    →  craft.plan() + craft.schedule()
    check_status()          →  WorkOrder.status
    cancel_request()        →  WorkOrder.cancel()
    list_pending()          →  WorkOrder.objects.filter()
"""

import logging
import threading
from datetime import date
from decimal import Decimal
from typing import Any, Callable

from django.db import transaction

from shopman.stocking.protocols.production import (
    ProductionPriority,
    ProductionRequest,
    ProductionResult,
    ProductionStatus,
    ProductionStatusEnum,
)

logger = logging.getLogger(__name__)


def _crafting_available() -> bool:
    """Check if Crafting is available."""
    try:
        from shopman.crafting.service import craft

        return True
    except ImportError:
        return False


def _map_workorder_status(status: str) -> ProductionStatusEnum:
    """Map Crafting WorkOrder status to ProductionStatusEnum."""
    mapping = {
        "pending": ProductionStatusEnum.PLANNED,
        "approved": ProductionStatusEnum.PLANNED,
        "scheduled": ProductionStatusEnum.SCHEDULED,
        "in_progress": ProductionStatusEnum.IN_PROGRESS,
        "completed": ProductionStatusEnum.COMPLETED,
        "cancelled": ProductionStatusEnum.CANCELLED,
    }
    return mapping.get(status, ProductionStatusEnum.REQUESTED)


class CraftingBackend:
    """
    Implementação do ProductionBackend usando a API do Crafting.

    Exemplo de uso:
        from shopman.stocking.adapters import get_production_backend

        backend = get_production_backend()
        result = backend.request_production(
            ProductionRequest(
                sku="CROISSANT",
                quantity=Decimal("50"),
                target_date=date.today(),
            )
        )
    """

    def __init__(self, recipe_resolver: Callable[[str], Any] | None = None):
        """
        Args:
            recipe_resolver: Função que resolve SKU → Recipe (model).
                            Se não fornecido, usa resolver padrão.
        """
        self._recipe_resolver = recipe_resolver

    def _get_recipe(self, sku: str):
        """Resolve SKU para Recipe."""
        if self._recipe_resolver:
            return self._recipe_resolver(sku)

        # Resolver padrão
        try:
            from shopman.crafting.models import Recipe

            return Recipe.objects.filter(product_sku=sku, is_active=True).first()
        except ImportError:
            return None

    def _get_craft(self):
        """Get Crafting service."""
        from shopman.crafting.service import craft

        return craft

    @transaction.atomic
    def request_production(
        self,
        request: ProductionRequest,
    ) -> ProductionResult:
        """Solicita produção usando craft.plan() + craft.schedule()."""
        if not _crafting_available():
            return ProductionResult(
                success=False,
                message="Crafting not available",
            )

        craft = self._get_craft()
        recipe = self._get_recipe(request.sku)

        if not recipe:
            return ProductionResult(
                success=False,
                message=f"Recipe não encontrada para SKU: {request.sku}",
            )

        try:
            # 1. Criar plano
            plan = craft.plan(
                recipe=recipe,
                quantity=request.quantity,
                target_date=request.target_date,
                metadata={
                    "source": "shopman.stocking",
                    "reference": request.reference,
                    "priority": request.priority.value,
                    **request.metadata,
                },
            )

            # 2. Aprovar e agendar
            # Mapeia prioridade para reserva automática
            reserve_materials = request.priority in (
                ProductionPriority.HIGH,
                ProductionPriority.URGENT,
            )

            work_order = craft.schedule(
                plan=plan,
                reserve_materials=reserve_materials,
            )

            return ProductionResult(
                success=True,
                request_id=f"production:{work_order.pk}",
                status=_map_workorder_status(work_order.status),
                work_order_id=str(work_order.uuid),
            )

        except Exception as e:
            logger.error(f"Failed to request production for {request.sku}: {e}")
            return ProductionResult(
                success=False,
                message=f"Falha ao criar produção: {e}",
            )

    def check_status(
        self,
        request_id: str,
    ) -> ProductionStatus | None:
        """Verifica status de uma solicitação."""
        if not _crafting_available():
            return None

        try:
            from shopman.crafting.models import WorkOrder

            # Parse request_id (formato: "production:{pk}")
            if not request_id.startswith("production:"):
                return None

            pk = int(request_id.replace("production:", ""))
            work_order = WorkOrder.objects.filter(pk=pk).first()

            if not work_order:
                return None

            return ProductionStatus(
                request_id=request_id,
                sku=work_order.plan.recipe.product_sku,
                quantity=work_order.planned_quantity,
                status=_map_workorder_status(work_order.status),
                target_date=work_order.target_date,
                estimated_completion=work_order.estimated_completion,
                work_order_id=str(work_order.uuid),
            )

        except (ValueError, WorkOrder.DoesNotExist):
            return None
        except Exception:
            logger.exception("Unexpected error in check_status for %s", request_id)
            raise

    @transaction.atomic
    def cancel_request(
        self,
        request_id: str,
        reason: str = "cancelled",
    ) -> ProductionResult:
        """Cancela uma solicitação de produção."""
        if not _crafting_available():
            return ProductionResult(
                success=False,
                message="Crafting not available",
            )

        try:
            from shopman.crafting.models import WorkOrder
            from shopman.crafting.service import work

            # Parse request_id
            if not request_id.startswith("production:"):
                return ProductionResult(
                    success=False,
                    message=f"Invalid request_id format: {request_id}",
                )

            pk = int(request_id.replace("production:", ""))
            work_order = WorkOrder.objects.filter(pk=pk).first()

            if not work_order:
                return ProductionResult(
                    success=False,
                    message=f"WorkOrder not found: {request_id}",
                )

            # Cancelar via service
            work.cancel(work_order, reason=reason)

            return ProductionResult(
                success=True,
                request_id=request_id,
                status=ProductionStatusEnum.CANCELLED,
                work_order_id=str(work_order.uuid),
            )

        except Exception as e:
            logger.error(f"Failed to cancel {request_id}: {e}")
            return ProductionResult(
                success=False,
                message=f"Falha ao cancelar: {e}",
            )

    def list_pending(
        self,
        sku: str | None = None,
        target_date: date | None = None,
    ) -> list[ProductionStatus]:
        """Lista solicitações pendentes."""
        if not _crafting_available():
            return []

        try:
            from shopman.crafting.models import WorkOrder

            queryset = WorkOrder.objects.filter(
                status__in=["pending", "approved", "scheduled", "in_progress"],
            )

            if sku:
                queryset = queryset.filter(plan__recipe__product_sku=sku)

            if target_date:
                queryset = queryset.filter(target_date=target_date)

            results = []
            for wo in queryset.select_related("plan__recipe"):
                results.append(
                    ProductionStatus(
                        request_id=f"production:{wo.pk}",
                        sku=wo.plan.recipe.product_sku,
                        quantity=wo.planned_quantity,
                        status=_map_workorder_status(wo.status),
                        target_date=wo.target_date,
                        estimated_completion=wo.estimated_completion,
                        work_order_id=str(wo.uuid),
                    )
                )

            return results

        except ImportError:
            return []
        except Exception:
            logger.exception("Unexpected error in list_pending")
            raise


# ══════════════════════════════════════════════════════════════
# Factory function
# ══════════════════════════════════════════════════════════════


_lock = threading.Lock()
_backend_instance: CraftingBackend | None = None


def get_production_backend(
    recipe_resolver: Callable[[str], Any] | None = None,
) -> CraftingBackend:
    """
    Get or create the production backend instance.

    Args:
        recipe_resolver: Optional custom recipe resolver

    Returns:
        CraftingBackend instance
    """
    global _backend_instance

    if recipe_resolver:
        # Se passou resolver customizado, cria nova instância
        return CraftingBackend(recipe_resolver=recipe_resolver)

    if _backend_instance is None:
        with _lock:
            if _backend_instance is None:  # double-checked
                _backend_instance = CraftingBackend()

    return _backend_instance


def reset_production_backend() -> None:
    """Reset singleton (for tests)."""
    global _backend_instance
    _backend_instance = None
