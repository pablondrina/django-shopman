"""
Composed SkuValidator — Offerman (vendáveis) + Buyman (insumos) + neutro.

Resolves a sku as a sellable Product (Offerman) first, then as an ingredient
Material (Buyman). Implements Stockman's SkuValidator protocol.

⚠️ NOT wired globally yet. STOCKMAN["SKU_VALIDATOR"] stays Noop until Buyman
WP-B5 turns shelf-life/availability on with care (flipping a real validator
changes availability semantics for every sku — see config/settings STOCKMAN
note and ADR-001). This adapter is the resolution layer that B5 will activate.
"""

from __future__ import annotations

import threading


class ComposedSkuValidator:
    """SkuValidator chaining Offerman (products) then Buyman (materials)."""

    def __init__(self):
        from shopman.buyman.adapters.sku_validator import MaterialSkuValidator
        from shopman.offerman.adapters.sku_validator import SkuValidator as OffermanSkuValidator

        self._offerman = OffermanSkuValidator()
        self._buyman = MaterialSkuValidator()

    def validate_sku(self, sku: str):
        result = self._offerman.validate_sku(sku)
        if result.valid:
            return result
        material = self._buyman.validate_sku(sku)
        return material if material.valid else result

    def validate_skus(self, skus: list[str]) -> dict:
        merged = self._offerman.validate_skus(skus)
        missing = [sku for sku, r in merged.items() if not r.valid]
        if missing:
            for sku, r in self._buyman.validate_skus(missing).items():
                if r.valid:
                    merged[sku] = r
        return merged

    def get_sku_info(self, sku: str):
        return self._offerman.get_sku_info(sku) or self._buyman.get_sku_info(sku)

    def search_skus(self, query: str, limit: int = 20, include_inactive: bool = False) -> list:
        results = list(self._offerman.search_skus(query, limit=limit, include_inactive=include_inactive))
        seen = {info.sku for info in results}
        for info in self._buyman.search_skus(query, limit=limit, include_inactive=include_inactive):
            if info.sku not in seen and len(results) < limit:
                results.append(info)
                seen.add(info.sku)
        return results


_lock = threading.Lock()
_instance: ComposedSkuValidator | None = None


def get_composed_sku_validator() -> ComposedSkuValidator:
    """Return the singleton ComposedSkuValidator."""
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = ComposedSkuValidator()
    return _instance


def reset_composed_sku_validator() -> None:
    """Reset the singleton (for tests)."""
    global _instance
    _instance = None
