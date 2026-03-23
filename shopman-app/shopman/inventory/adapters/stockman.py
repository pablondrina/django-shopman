"""
Shopman Stockman Adapter — Adapter para integração com Stockman.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Callable

from django.core.exceptions import ObjectDoesNotExist

from shopman.inventory.protocols import (
    Alternative,
    AvailabilityResult,
    HoldResult,
    StockBackend,
)

logger = logging.getLogger(__name__)


def _stockman_available() -> bool:
    """Check if Stockman is installed."""
    try:
        from shopman.stocking import stock
        return True
    except ImportError:
        return False


class StockmanBackend:
    """
    Adapter que conecta stock ao Stockman.
    """

    def __init__(self, product_resolver: Callable[[str], Any]):
        self.get_product = product_resolver

    def check_availability(
        self,
        sku: str,
        quantity: Decimal,
        target_date: date | None = None,
    ) -> AvailabilityResult:
        if not _stockman_available():
            raise ImportError(
                "Stockman não está instalado. "
                "Instale com: pip install django-stockman"
            )

        from shopman.stocking.service import Stock as stock

        try:
            product = self.get_product(sku)
        except ObjectDoesNotExist:
            return AvailabilityResult(
                available=False,
                available_qty=Decimal("0"),
                message=f"Produto não encontrado: {sku}",
            )
        except Exception:
            logger.exception("Unexpected error checking availability for %s", sku)
            raise

        available = stock.available(product, target_date=target_date)

        return AvailabilityResult(
            available=quantity <= available,
            available_qty=Decimal(str(available)),
            message=None if quantity <= available else f"Disponível: {available}",
        )

    def create_hold(
        self,
        sku: str,
        quantity: Decimal,
        expires_at: datetime | None = None,
        reference: str | None = None,
        target_date: date | None = None,
        **extra_metadata,
    ) -> HoldResult:
        if not _stockman_available():
            return HoldResult(
                success=False,
                error_code="stockman_not_installed",
                message="Stockman não está instalado",
            )

        from shopman.stocking.service import Stock as stock
        from shopman.stocking.exceptions import StockError

        try:
            product = self.get_product(sku)
        except ObjectDoesNotExist:
            return HoldResult(
                success=False,
                error_code="product_not_found",
                message=f"Produto não encontrado: {sku}",
            )
        except Exception:
            logger.exception("Unexpected error resolving product for hold on %s", sku)
            raise

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
                hold.expires_at = None
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
        if not _stockman_available():
            logger.warning("release_hold: Stockman not installed, cannot release hold %s", hold_id)
            return

        from shopman.stocking.service import Stock as stock
        from shopman.stocking.exceptions import StockError

        try:
            stock.release(hold_id, reason="Liberado via Shopman")
        except StockError as e:
            logger.debug("release_hold: Hold %s already released or invalid: %s", hold_id, e)
        except Exception as e:
            logger.warning("release_hold: Failed to release hold %s: %s", hold_id, e)

    def fulfill_hold(self, hold_id: str, reference: str | None = None) -> None:
        if not _stockman_available():
            raise ImportError("Stockman não está instalado.")

        from shopman.stocking.service import Stock as stock
        from shopman.stocking.models import Hold
        from shopman.stocking.models.enums import HoldStatus
        from shopman.stocking.exceptions import StockError

        pk = int(hold_id.split(":")[1])
        try:
            hold = Hold.objects.get(pk=pk)
        except Hold.DoesNotExist:
            raise StockError("HOLD_NOT_FOUND", hold_id=hold_id) from None

        if hold.status == HoldStatus.FULFILLED:
            logger.debug("fulfill_hold: hold %s already fulfilled, skipping.", hold_id)
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
            logger.debug("shopman.offering.contrib.suggestions not available, skipping alternatives")
            return []

        try:
            candidates = find_alternatives(sku, limit=5)
            alternatives = []
            for product in candidates:
                try:
                    avail_qty = Decimal("0")
                    if _stockman_available():
                        from shopman.stocking.service import Stock as stock
                        avail_qty = stock.available(product.sku)
                    if avail_qty >= quantity:
                        alternatives.append(
                            Alternative(
                                sku=product.sku,
                                name=product.name,
                                available_qty=avail_qty,
                            )
                        )
                except Exception:
                    logger.debug("Failed to check availability for alternative %s", product.sku)
            return alternatives
        except Exception:
            logger.debug("find_alternatives failed for %s", sku, exc_info=True)
            return []

    def release_holds_for_reference(self, reference: str) -> int:
        if not _stockman_available():
            logger.warning("release_holds_for_reference: Stockman not installed")
            return 0

        from shopman.stocking.service import Stock as stock
        from shopman.stocking.models import Hold
        from shopman.stocking.models.enums import HoldStatus
        from shopman.stocking.exceptions import StockError

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
                except Exception as e:
                    logger.warning(
                        "release_holds_for_reference: Failed to release hold %s: %s",
                        hold.hold_id, e
                    )
            return count
        except Exception as e:
            logger.warning("release_holds_for_reference: Failed for reference %s: %s", reference, e)
            return 0

    def receive_return(
        self,
        sku: str,
        quantity: Decimal,
        *,
        reference: str | None = None,
        reason: str = "Devolução",
    ) -> None:
        if not _stockman_available():
            raise ImportError("Stockman não está instalado.")

        from shopman.stocking.services.movements import StockMovements

        StockMovements.receive(
            quantity=quantity,
            sku=sku,
            reason=f"{reason} (ref: {reference})" if reference else reason,
        )
