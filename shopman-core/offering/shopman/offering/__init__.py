"""
Shopman Offering - Product Catalog.

Usage:
    from shopman.offering import CatalogService, CatalogError

    product = CatalogService.get("BAGUETE")
    price = CatalogService.price("BAGUETE", qty=3, channel="ifood")
"""


def __getattr__(name):
    if name == "CatalogService":
        from shopman.offering.service import CatalogService

        return CatalogService
    elif name == "CatalogError":
        from shopman.offering.exceptions import CatalogError

        return CatalogError
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["CatalogService", "CatalogError"]
__version__ = "0.3.0"
