"""
Stockman Backend — implements InventoryProtocol using Stockman's API.

Vocabulary mapping:
    Craftsman          →  Stockman
    ─────────────────────────────────
    available()         →  stock.available()
    reserve()           →  stock.hold()
    consume()           →  stock.fulfill()
    release()           →  stock.release()
    receive()           →  stock.receive()
"""

import logging
import threading
from decimal import Decimal
from typing import Any, Callable

from django.db import transaction

from shopman.craftsman.protocols.inventory import (
    AvailabilityResult,
    ConsumeResult,
    MaterialAdjustment,
    MaterialHold,
    MaterialNeed,
    MaterialProduced,
    MaterialStatus,
    MaterialUsed,
    ReceiveResult,
    ReleaseResult,
    ReserveResult,
)

logger = logging.getLogger(__name__)


def _stocking_available() -> bool:
    """Check if Stockman is available."""
    try:
        from shopman.stockman.service import stock  # noqa: F401

        return True
    except ImportError:
        return False


class StockingBackend:
    """
    Implementação do InventoryProtocol usando a API do Stockman.

    Exemplo de uso:
        from shopman.craftsman.adapters import get_stock_backend

        backend = get_stock_backend()
        result = backend.available([
            MaterialNeed(sku="FARINHA", quantity=Decimal("10")),
        ])
    """

    def __init__(self, product_resolver: Callable[[str], Any] | None = None):
        self._product_resolver = product_resolver

    def _get_product(self, sku: str):
        """Resolve SKU to product."""
        if self._product_resolver:
            return self._product_resolver(sku)

        try:
            from shopman.craftsman.adapters.offering import get_catalog_backend

            backend = get_catalog_backend()
            info = backend.resolve(sku)
            if info:
                return info
        except ImportError:
            logger.debug("Catalog backend not available for SKU resolution: %s", sku)
        except Exception:
            logger.warning("Failed to resolve SKU via catalog backend: %s", sku, exc_info=True)

        logger.warning("Could not resolve product for SKU: %s", sku)
        return None

    def _get_stock(self):
        """Get Stockman service."""
        from shopman.stockman.service import stock

        return stock

    def _get_position(self, ref: str | None):
        """Get Position by ref."""
        if not ref:
            return None
        try:
            from shopman.stockman.models import Position

            return Position.objects.filter(ref=ref).first()
        except ImportError:
            return None

    def available(self, materials: list[MaterialNeed]) -> AvailabilityResult:
        """Verifica disponibilidade usando stock.available()."""
        if not _stocking_available():
            return AvailabilityResult(
                all_available=True,
                materials=[
                    MaterialStatus(sku=mat.sku, needed=mat.quantity, available=mat.quantity)
                    for mat in materials
                ],
            )

        stock = self._get_stock()
        items = []
        all_available = True

        for mat in materials:
            product = self._get_product(mat.sku)
            if not product:
                items.append(MaterialStatus(sku=mat.sku, needed=mat.quantity, available=Decimal("0")))
                all_available = False
                continue

            avail = stock.available(product)
            if avail < mat.quantity:
                all_available = False

            items.append(MaterialStatus(sku=mat.sku, needed=mat.quantity, available=avail))

        return AvailabilityResult(all_available=all_available, materials=items)

    @transaction.atomic
    def reserve(
        self,
        materials: list[MaterialNeed],
        ref: str,
        metadata: dict[str, Any] | None = None,
    ) -> ReserveResult:
        """Reserva materiais usando stock.hold()."""
        if not _stocking_available():
            return ReserveResult(
                success=True,
                holds=[
                    MaterialHold(sku=mat.sku, quantity=mat.quantity, hold_id="mock:0")
                    for mat in materials
                ],
            )

        stock = self._get_stock()
        holds = []
        failed_items = []

        for mat in materials:
            product = self._get_product(mat.sku)
            if not product:
                failed_items.append(MaterialStatus(sku=mat.sku, needed=mat.quantity, available=Decimal("0")))
                continue

            avail = stock.available(product)
            if avail < mat.quantity:
                failed_items.append(MaterialStatus(sku=mat.sku, needed=mat.quantity, available=avail))
                continue

            try:
                from datetime import date

                hold_id = stock.hold(
                    quantity=mat.quantity,
                    product=product,
                    target_date=date.today(),
                    metadata={
                        "work_order_ref": ref,
                        "reference_type": "shopman.craftsman.workorder",
                        **(metadata or {}),
                    },
                )
                holds.append(MaterialHold(sku=mat.sku, quantity=mat.quantity, hold_id=hold_id))

            except Exception as e:
                logger.error("Failed to create hold for %s: %s", mat.sku, e)
                failed_items.append(MaterialStatus(sku=mat.sku, needed=mat.quantity, available=avail))

        if failed_items:
            for hold in holds:
                try:
                    stock.release(hold.hold_id, reason="rollback")
                except Exception as e:
                    logger.error("Failed to release hold %s: %s", hold.hold_id, e)

            return ReserveResult(
                success=False, holds=[], failed=failed_items,
                message="Estoque insuficiente para alguns materiais",
            )

        return ReserveResult(success=True, holds=holds, failed=[])

    @transaction.atomic
    def consume(
        self,
        items: list[MaterialUsed],
        ref: str,
    ) -> ConsumeResult:
        """Consome materiais reservados usando stock.fulfill()."""
        if not _stocking_available():
            return ConsumeResult(success=True)

        stock = self._get_stock()

        try:
            from shopman.stockman.models import Hold, HoldStatus

            holds = Hold.objects.filter(
                metadata__work_order_ref=ref,
                status__in=[HoldStatus.PENDING, HoldStatus.CONFIRMED],
            )
        except ImportError:
            return ConsumeResult(success=False, message="Stockman not available")

        consumed = []
        adjustments = []

        for hold in holds:
            sku = getattr(hold.product, "sku", str(hold.product))

            actual_item = next((c for c in items if c.sku == sku), None) if items else None
            consume_qty = actual_item.quantity if actual_item else hold.quantity

            try:
                stock.fulfill(hold.hold_id, qty=consume_qty)
                consumed.append(MaterialUsed(sku=sku, quantity=consume_qty))

                if consume_qty != hold.quantity:
                    adjustments.append(
                        MaterialAdjustment(sku=sku, reserved=hold.quantity, consumed=consume_qty)
                    )
            except Exception as e:
                logger.error("Failed to fulfill hold %s: %s", hold.hold_id, e)
                return ConsumeResult(
                    success=False, consumed=consumed,
                    message=f"Falha ao consumir {sku}: {e}",
                )

        return ConsumeResult(success=True, consumed=consumed, adjustments=adjustments)

    @transaction.atomic
    def release(
        self,
        ref: str,
        reason: str = "voided",
    ) -> ReleaseResult:
        """Libera materiais reservados usando stock.release()."""
        if not _stocking_available():
            return ReleaseResult(success=True)

        stock = self._get_stock()

        try:
            from shopman.stockman.models import Hold, HoldStatus

            holds = Hold.objects.filter(
                metadata__work_order_ref=ref,
                status__in=[HoldStatus.PENDING, HoldStatus.CONFIRMED],
            )
        except ImportError:
            return ReleaseResult(success=False, message="Stockman not available")

        released = []
        failed = []
        for hold in holds:
            try:
                sku = getattr(hold.product, "sku", str(hold.product))
                stock.release(hold.hold_id, reason=reason)
                released.append(MaterialHold(sku=sku, quantity=hold.quantity, hold_id=hold.hold_id))
            except Exception as e:
                logger.error("Failed to release hold %s: %s", hold.hold_id, e)
                failed.append(hold.hold_id)

        return ReleaseResult(
            success=len(failed) == 0,
            released=released,
            message=f"Failed to release holds: {failed}" if failed else None,
        )

    @transaction.atomic
    def receive(
        self,
        items: list[MaterialProduced],
        ref: str,
    ) -> ReceiveResult:
        """Registra output de produção usando stock.receive()."""
        if not _stocking_available():
            return ReceiveResult(success=True, quant_id="mock:0")

        stock = self._get_stock()
        last_quant_id = None

        for item in items:
            product = self._get_product(item.sku)
            if not product:
                return ReceiveResult(
                    success=False,
                    message=f"Produto não encontrado: {item.sku}",
                )

            position = self._get_position(item.position_ref)

            try:
                quant = stock.receive(
                    quantity=item.quantity,
                    product=product,
                    position=position,
                    reference=ref,
                    metadata={
                        "work_order_ref": ref,
                        "source": "crafting",
                        **(item.metadata or {}),
                    },
                )
                last_quant_id = f"quant:{quant.pk}"

            except Exception as e:
                logger.error("Failed to register output for %s: %s", item.sku, e)
                return ReceiveResult(success=False, message=f"Falha ao registrar saída: {e}")

        return ReceiveResult(success=True, quant_id=last_quant_id)


# ══════════════════════════════════════════════════════════════
# Factory function
# ══════════════════════════════════════════════════════════════

_lock = threading.Lock()
_backend_instance: StockingBackend | None = None


def get_stock_backend(
    product_resolver: Callable[[str], Any] | None = None,
) -> StockingBackend:
    """Get or create the stock backend instance."""
    global _backend_instance

    if product_resolver:
        return StockingBackend(product_resolver=product_resolver)

    if _backend_instance is None:
        with _lock:
            if _backend_instance is None:
                _backend_instance = StockingBackend()

    return _backend_instance


def reset_stock_backend() -> None:
    """Reset singleton (for tests)."""
    global _backend_instance
    _backend_instance = None
