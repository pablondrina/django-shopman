"""
Shopman Noop Customer Adapter -- No-op backend for development and testing.
"""

from __future__ import annotations

import logging

from shopman.customer.protocols import (
    CustomerContext,
    CustomerInfo,
    CustomerValidationResult,
)

logger = logging.getLogger(__name__)


class NoopCustomerBackend:
    """
    Customer backend that returns minimal placeholder data.
    """

    def get_customer(self, code: str) -> CustomerInfo | None:
        logger.debug("NoopCustomerBackend.get_customer: code=%s (returning placeholder)", code)
        return CustomerInfo(
            code=code,
            name=f"Guest {code}",
            customer_type="individual",
        )

    def validate_customer(self, code: str) -> CustomerValidationResult:
        logger.debug("NoopCustomerBackend.validate_customer: code=%s (always valid)", code)
        return CustomerValidationResult(
            valid=True,
            code=code,
            info=self.get_customer(code),
        )

    def get_listing_code(self, customer_ref: str) -> str | None:
        return None

    def get_customer_context(self, code: str) -> CustomerContext | None:
        info = self.get_customer(code)
        if info is None:
            return None

        logger.debug("NoopCustomerBackend.get_customer_context: code=%s (returning minimal context)", code)
        return CustomerContext(
            info=info,
            preferences={},
            recent_orders=[],
        )

    def record_order(self, customer_ref: str, order_data: dict) -> bool:
        logger.debug("NoopCustomerBackend.record_order: customer_ref=%s (no-op)", customer_ref)
        return True
