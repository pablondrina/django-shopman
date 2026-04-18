"""
Shopman Offerman - Product Catalog.

Usage:
    from shopman.offerman import CatalogService, CatalogError

    product = CatalogService.get("BAGUETE")
    price = CatalogService.price("BAGUETE", qty=3, channel="ifood")
"""


def __getattr__(name):
    if name == "CatalogService":
        from shopman.offerman.service import CatalogService

        return CatalogService
    elif name == "CatalogError":
        from shopman.offerman.exceptions import CatalogError

        return CatalogError
    elif name == "find_substitutes":
        from shopman.offerman.contrib.substitutes.substitutes import find_substitutes

        return find_substitutes
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["CatalogService", "CatalogError", "find_substitutes"]
__version__ = "0.3.0"
