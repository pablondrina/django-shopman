"""
Composed CatalogBackend — Offerman (vendáveis) + Buyman (insumos).

Craftsman resolves a sku via this backend (RecipeItem unit cross-check etc.).
A sellable output resolves through Offerman; an ingredient (Material) resolves
through Buyman. Everything else delegates to the Offerman backend.

Wired via CRAFTSMAN["CATALOG_BACKEND"]. Resolution-only — does NOT touch stock
availability (that is the SkuValidator seam, flipped on by Buyman WP-B5).
"""

from __future__ import annotations

import threading


class ComposedCatalogBackend:
    """Catalog backend that resolves Products (Offerman) then Materials (Buyman)."""

    def __init__(self):
        from shopman.buyman.adapters.catalog_backend import BuymanCatalogBackend
        from shopman.offerman.adapters.catalog_backend import OffermanCatalogBackend

        self._offerman = OffermanCatalogBackend()
        self._buyman = BuymanCatalogBackend()

    def get_product(self, sku: str):
        """Resolve a sku as a sellable product first, then as an ingredient."""
        return self._offerman.get_product(sku) or self._buyman.get_product(sku)

    def __getattr__(self, name):
        # Anything not overridden (get_price, expand, etc.) is an Offerman/sellable
        # concern — delegate. (Called only for attrs missing on this instance.)
        return getattr(self.__dict__["_offerman"], name)


_lock = threading.Lock()
_instance: ComposedCatalogBackend | None = None


def get_composed_catalog_backend() -> ComposedCatalogBackend:
    """Return the singleton ComposedCatalogBackend."""
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = ComposedCatalogBackend()
    return _instance


def reset_composed_catalog_backend() -> None:
    """Reset the singleton (for tests)."""
    global _instance
    _instance = None
