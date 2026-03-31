"""
Stock backends — pontes para shopman.stocking.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone

from channels.protocols import Alternative, AvailabilityResult, HoldResult

logger = logging.getLogger(__name__)


def _stocking_available() -> bool:
    try:
        from shopman.stocking import stock  # noqa: F401

        return True
    except ImportError:
        return False


class StockingBackend:
    """Adapter que conecta stock ao Stocking (shopman.stocking)."""

    def __init__(self, product_resolver: Callable[[str], Any]):
        self.get_product = product_resolver

    def check_availability(
        self,
        sku: str,
        quantity: Decimal,
        target_date: date | None = None,
        safety_margin: int = 0,
        allowed_positions: list[str] | None = None,
    ) -> AvailabilityResult:
        if not _stocking_available():
            raise ImportError("Stocking não está instalado.")

        from shopman.stocking.service import Stock as stock

        try:
            product = self.get_product(sku)
        except ObjectDoesNotExist:
            return AvailabilityResult(
                available=False,
                available_qty=Decimal("0"),
                message=f"Produto não encontrado: {sku}",
            )

        if allowed_positions is not None:
            available = self._available_at_positions(
                sku, product, target_date, allowed_positions,
            )
        else:
            available = stock.available(product, target_date=target_date)

        # Apply safety margin for planned stock (advance orders)
        if target_date and target_date > date.today() and safety_margin > 0:
            available = max(Decimal("0"), available - Decimal(str(safety_margin)))

        return AvailabilityResult(
            available=quantity <= available,
            available_qty=Decimal(str(available)),
            message=None if quantity <= available else f"Disponível: {available}",
        )

    @staticmethod
    def _available_at_positions(
        sku: str,
        product,
        target_date: date | None,
        position_refs: list[str],
    ) -> Decimal:
        """Sum availability across specific positions only."""
        from shopman.stocking.service import Stock as stock
        from shopman.stocking.models import Position

        total = Decimal("0")
        positions = Position.objects.filter(ref__in=position_refs)
        for pos in positions:
            total += stock.available(product, target_date=target_date, position=pos)
        return total

    def create_hold(
        self,
        sku: str,
        quantity: Decimal,
        expires_at: datetime | None = None,
        reference: str | None = None,
        target_date: date | None = None,
        planned_hold_ttl_hours: int = 48,
        **extra_metadata,
    ) -> HoldResult:
        if not _stocking_available():
            return HoldResult(
                success=False,
                error_code="stocking_not_installed",
                message="Stocking não está instalado",
            )

        from shopman.stocking.exceptions import StockError
        from shopman.stocking.service import Stock as stock

        try:
            product = self.get_product(sku)
        except ObjectDoesNotExist:
            return HoldResult(
                success=False,
                error_code="product_not_found",
                message=f"Produto não encontrado: {sku}",
            )

        try:
            hold_kwargs = dict(extra_metadata)
            if reference:
                hold_kwargs["reference"] = reference

            hold_id = stock.hold(
                quantity,
                product,
                target_date=target_date or date.today(),
                expires_at=expires_at,
                **hold_kwargs,
            )

            from shopman.stocking.models import Hold

            pk = int(hold_id.split(":")[1])
            hold = Hold.objects.get(pk=pk)

            is_planned = False
            if hold.quant and hold.quant.target_date is not None:
                is_planned = True
                # Set long TTL for planned holds instead of no expiration
                hold.expires_at = timezone.now() + timedelta(hours=planned_hold_ttl_hours)
                hold.save(update_fields=["expires_at"])

            return HoldResult(
                success=True,
                hold_id=hold_id,
                expires_at=hold.expires_at,
                is_planned=is_planned,
            )
        except StockError as e:
            return HoldResult(
                success=False,
                error_code=e.code if hasattr(e, "code") else "hold_failed",
                message=str(e),
            )
        except Exception as e:
            logger.warning("create_hold failed for SKU %s: %s", sku, e, exc_info=True)
            return HoldResult(
                success=False,
                error_code="hold_failed",
                message=str(e),
            )

    def release_hold(self, hold_id: str) -> None:
        if not _stocking_available():
            return

        from shopman.stocking.exceptions import StockError
        from shopman.stocking.service import Stock as stock

        try:
            stock.release(hold_id, reason="Liberado via Shopman")
        except StockError:
            logger.debug("release_hold: Hold %s already released or invalid", hold_id)

    def fulfill_hold(self, hold_id: str, reference: str | None = None) -> None:
        if not _stocking_available():
            raise ImportError("Stocking não está instalado.")

        from shopman.stocking.exceptions import StockError
        from shopman.stocking.models import Hold
        from shopman.stocking.models.enums import HoldStatus
        from shopman.stocking.service import Stock as stock

        pk = int(hold_id.split(":")[1])
        try:
            hold = Hold.objects.get(pk=pk)
        except Hold.DoesNotExist:
            raise StockError("HOLD_NOT_FOUND", hold_id=hold_id) from None

        if hold.status == HoldStatus.FULFILLED:
            return

        if hold.status == HoldStatus.PENDING:
            try:
                stock.confirm(hold_id)
            except StockError:
                hold.refresh_from_db()
                if hold.status not in (HoldStatus.CONFIRMED, HoldStatus.FULFILLED):
                    raise

        stock.fulfill(hold_id)

    def get_alternatives(self, sku: str, quantity: Decimal) -> list[Alternative]:
        try:
            from shopman.offering.contrib.suggestions import find_alternatives
        except ImportError:
            return []

        try:
            candidates = find_alternatives(sku, limit=5)
            alternatives = []
            for product in candidates:
                try:
                    avail_qty = Decimal("0")
                    if _stocking_available():
                        from shopman.stocking.service import Stock as stock

                        avail_qty = stock.available(product.sku)
                    if avail_qty >= quantity:
                        alternatives.append(
                            Alternative(sku=product.sku, name=product.name, available_qty=avail_qty)
                        )
                except Exception:
                    pass
            return alternatives
        except Exception:
            return []

    def release_holds_for_reference(self, reference: str) -> int:
        if not _stocking_available():
            return 0

        from shopman.stocking.exceptions import StockError
        from shopman.stocking.models import Hold
        from shopman.stocking.models.enums import HoldStatus
        from shopman.stocking.service import Stock as stock

        try:
            holds = Hold.objects.filter(
                status__in=[HoldStatus.PENDING, HoldStatus.CONFIRMED],
                metadata__reference=reference,
            )
            count = 0
            for hold in holds:
                try:
                    stock.release(hold.hold_id, reason="Idempotency cleanup")
                    count += 1
                except StockError:
                    pass
            return count
        except Exception:
            return 0

    def receive_return(
        self,
        sku: str,
        quantity: Decimal,
        *,
        reference: str | None = None,
        reason: str = "Devolução",
    ) -> None:
        if not _stocking_available():
            raise ImportError("Stocking não está instalado.")

        from shopman.stocking.services.movements import StockMovements

        StockMovements.receive(
            quantity=quantity,
            sku=sku,
            reason=f"{reason} (ref: {reference})" if reference else reason,
        )


class NoopStockBackend:
    """Stock backend that always reports items as available (dev/test)."""

    _hold_counter: int = 0

    def check_availability(self, sku: str, quantity: Decimal, target_date: date | None = None) -> AvailabilityResult:
        return AvailabilityResult(available=True, available_qty=Decimal("999999"))

    def create_hold(
        self, sku: str, quantity: Decimal, expires_at: datetime | None = None,
        reference: str | None = None, target_date: date | None = None,
    ) -> HoldResult:
        NoopStockBackend._hold_counter += 1
        hold_id = f"noop-hold:{NoopStockBackend._hold_counter}"
        return HoldResult(success=True, hold_id=hold_id, expires_at=expires_at or (timezone.now() + timedelta(minutes=15)))

    def release_hold(self, hold_id: str) -> None:
        pass

    def fulfill_hold(self, hold_id: str, reference: str | None = None) -> None:
        pass

    def get_alternatives(self, sku: str, quantity: Decimal) -> list[Alternative]:
        return []

    def release_holds_for_reference(self, reference: str) -> int:
        return 0

    def receive_return(self, sku: str, quantity: Decimal, *, reference: str | None = None, reason: str = "Devolução") -> None:
        pass


__all__ = ["StockingBackend", "NoopStockBackend"]
