"""
Noop SKU Validator — Stub adapter for development and testing.

This adapter implements the SkuValidator protocol with trivial defaults:
- All SKUs are considered valid
- Product info returns minimal placeholder data

Usage in settings.py:
    STOCKING = {
        "SKU_VALIDATOR": "shopman.stocking.adapters.noop.NoopSkuValidator",
    }

WARNING: Do NOT use in production. This adapter performs no real validation
and will accept any SKU, including nonexistent or inactive ones.
"""

from __future__ import annotations

from shopman.stocking.protocols.sku import SkuInfo, SkuValidationResult


class NoopSkuValidator:
    """
    No-operation SKU validator for development and testing.

    Every SKU is valid, every lookup returns minimal defaults.
    Implements the ``SkuValidator`` protocol without any external
    dependencies, making it suitable for:

    - Local development without a running catalog service
    - Unit/integration tests that don't need real SKU validation
    - CI pipelines where Offering is unavailable
    """

    def validate_sku(self, sku: str) -> SkuValidationResult:
        """
        Validate a SKU. Always returns valid=True.

        Args:
            sku: Product code (any string).

        Returns:
            SkuValidationResult with valid=True.
        """
        return SkuValidationResult(
            valid=True,
            sku=sku,
            product_name=sku,
            is_active=True,
        )

    def validate_skus(self, skus: list[str]) -> dict[str, SkuValidationResult]:
        """
        Validate multiple SKUs. All are considered valid.

        Args:
            skus: List of product codes.

        Returns:
            Dict mapping each SKU to a valid SkuValidationResult.
        """
        return {sku: self.validate_sku(sku) for sku in skus}

    def get_sku_info(self, sku: str) -> SkuInfo | None:
        """
        Get SKU information. Returns minimal defaults.

        Args:
            sku: Product code.

        Returns:
            SkuInfo with placeholder values (name=sku, unit='un').
        """
        return SkuInfo(
            sku=sku,
            name=sku,
            description=None,
            is_active=True,
            unit="un",
            category=None,
            base_price_q=None,
            metadata=None,
        )

    def search_skus(
        self,
        query: str,
        limit: int = 20,
        include_inactive: bool = False,
    ) -> list[SkuInfo]:
        """
        Search SKUs. Always returns an empty list.

        The noop adapter has no catalog to search, so this is a no-op.

        Args:
            query: Search term (ignored).
            limit: Maximum results (ignored).
            include_inactive: Include inactive SKUs (ignored).

        Returns:
            Empty list.
        """
        return []
