"""
Shopman Noop Stock Adapter -- No-op backend for development and testing.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from django.utils import timezone

from shopman.inventory.protocols import (
    Alternative,
    AvailabilityResult,
    HoldResult,
)

logger = logging.getLogger(__name__)


class NoopStockBackend:
    """
    Stock backend that always reports items as available.
    """

    _hold_counter: int = 0

    def check_availability(
        self,
        sku: str,
        quantity: Decimal,
        target_date: date | None = None,
    ) -> AvailabilityResult:
        logger.debug("NoopStockBackend.check_availability: sku=%s qty=%s (always available)", sku, quantity)
        return AvailabilityResult(
            available=True,
            available_qty=Decimal("999999"),
        )

    def create_hold(
        self,
        sku: str,
        quantity: Decimal,
        expires_at: datetime | None = None,
        reference: str | None = None,
        target_date: date | None = None,
    ) -> HoldResult:
        NoopStockBackend._hold_counter += 1
        hold_id = f"noop-hold:{NoopStockBackend._hold_counter}"
        hold_expires = expires_at or (timezone.now() + timedelta(minutes=15))

        logger.debug(
            "NoopStockBackend.create_hold: sku=%s qty=%s hold_id=%s (no-op)",
            sku, quantity, hold_id,
        )

        return HoldResult(
            success=True,
            hold_id=hold_id,
            expires_at=hold_expires,
        )

    def release_hold(self, hold_id: str) -> None:
        logger.debug("NoopStockBackend.release_hold: hold_id=%s (no-op)", hold_id)

    def fulfill_hold(self, hold_id: str, reference: str | None = None) -> None:
        logger.debug("NoopStockBackend.fulfill_hold: hold_id=%s reference=%s (no-op)", hold_id, reference)

    def get_alternatives(self, sku: str, quantity: Decimal) -> list[Alternative]:
        return []

    def release_holds_for_reference(self, reference: str) -> int:
        logger.debug("NoopStockBackend.release_holds_for_reference: reference=%s (no-op)", reference)
        return 0

    def receive_return(
        self,
        sku: str,
        quantity: Decimal,
        *,
        reference: str | None = None,
        reason: str = "Devolução",
    ) -> None:
        logger.debug(
            "NoopStockBackend.receive_return: sku=%s qty=%s reference=%s (no-op)",
            sku, quantity, reference,
        )
