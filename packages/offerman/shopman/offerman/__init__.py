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
    elif name == "find_alternatives":
        from shopman.offerman.contrib.suggestions.suggestions import find_alternatives

        return find_alternatives
    elif name == "find_similar":
        from shopman.offerman.contrib.suggestions.suggestions import find_similar

        return find_similar
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["CatalogService", "CatalogError", "find_alternatives", "find_similar"]
__version__ = "0.3.0"
