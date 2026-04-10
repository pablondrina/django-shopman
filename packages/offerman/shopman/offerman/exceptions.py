"""Offerman exceptions."""

from shopman.utils.exceptions import BaseError


class CatalogError(BaseError):
    """
    Structured exception for catalog operations.

    Usage:
        try:
            price = catalog.price("XYZ")
        except CatalogError as e:
            if e.code == "SKU_NOT_FOUND":
                print(f"SKU {e.sku} does not exist")
    """

    _default_messages = {
        "SKU_NOT_FOUND": "SKU not found",
        "SKU_INACTIVE": "SKU is inactive",
        "NOT_A_BUNDLE": "SKU is not a bundle",
        "INVALID_PRICE_LIST": "Invalid price list",
        "PRICE_LIST_EXPIRED": "Price list expired",
        "INVALID_QUANTITY": "Invalid quantity",
        "CIRCULAR_COMPONENT": "Circular component reference detected",
    }

    @property
    def sku(self) -> str | None:
        return self.data.get("sku")
