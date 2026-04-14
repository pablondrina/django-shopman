"""
Craftsman Backend.

Implements ProductionBackend using Craftsman's API (craft.*, work.*).

Vocabulary mapping:
    Stockman                →  Craftsman
    ─────────────────────────────────────────
    request_production()    →  craft.plan()
    check_status()          →  WorkOrder.status
    cancel_request()        →  craft.void()
    list_pending()          →  WorkOrder.objects.filter()
"""

import logging
import threading
from collections.abc import Callable
from datetime import date
from typing import Any

from django.db import transaction
from shopman.stockman.protocols.production import (
    ProductionPriority,
    ProductionRequest,
    ProductionResult,
    ProductionStatus,
    ProductionStatusEnum,
)

logger = logging.getLogger(__name__)


def _craftsman_available() -> bool:
    """Check if Craftsman is available."""
    try:
        from shopman.craftsman.service import craft

        return True
    except ImportError:
        return False


def _map_workorder_status(status: str) -> ProductionStatusEnum:
    """Map Craftsman WorkOrder status to ProductionStatusEnum."""
    mapping = {
        "planned": ProductionStatusEnum.PLANNED,
        "started": ProductionStatusEnum.STARTED,
        "finished": ProductionStatusEnum.FINISHED,
        "void": ProductionStatusEnum.VOIDED,
    }
    try:
        return mapping[status]
    except KeyError:
        logger.warning("Unknown Craftsman WorkOrder status for ProductionStatusEnum: %s", status)
        return ProductionStatusEnum.PLANNED


class ProductionBackend:
    """
    Implementação do ProductionBackend usando a API do Craftsman.

    Exemplo de uso:
        from shopman.stockman.adapters import get_production_backend

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
            from shopman.craftsman.models import Recipe

            return Recipe.objects.filter(product_sku=sku, is_active=True).first()
        except ImportError:
            return None

    def _get_craft(self):
        """Get Craftsman service."""
        from shopman.craftsman.service import craft

        return craft

    @transaction.atomic
    def request_production(
        self,
        request: ProductionRequest,
    ) -> ProductionResult:
        """Solicita produção usando craft.plan() + craft.schedule()."""
        if not _craftsman_available():
            return ProductionResult(
                success=False,
                message="Craftsman not available",
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
                    "source": "shopman.stockman",
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
        if not _craftsman_available():
            return None

        try:
            from shopman.craftsman.models import WorkOrder

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
        if not _craftsman_available():
            return ProductionResult(
                success=False,
                message="Craftsman not available",
            )

        try:
            from shopman.craftsman.models import WorkOrder
            from shopman.craftsman.service import craft

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

            craft.void(work_order, reason=reason, actor="stockman:cancel")

            return ProductionResult(
                success=True,
                request_id=request_id,
                status=ProductionStatusEnum.VOIDED,
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
        if not _craftsman_available():
            return []

        try:
            from shopman.craftsman.models import WorkOrder

            queryset = WorkOrder.objects.filter(
                status__in=["planned", "started"],
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
_backend_instance: ProductionBackend | None = None


def get_production_backend(
    recipe_resolver: Callable[[str], Any] | None = None,
) -> ProductionBackend:
    """
    Get or create the production backend instance.

    Args:
        recipe_resolver: Optional custom recipe resolver

    Returns:
        ProductionBackend instance
    """
    global _backend_instance

    if recipe_resolver:
        # Se passou resolver customizado, cria nova instância
        return ProductionBackend(recipe_resolver=recipe_resolver)

    if _backend_instance is None:
        with _lock:
            if _backend_instance is None:  # double-checked
                _backend_instance = ProductionBackend()

    return _backend_instance


def reset_production_backend() -> None:
    """Reset singleton (for tests)."""
    global _backend_instance
    _backend_instance = None
