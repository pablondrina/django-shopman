"""
Buyman CatalogBackend — resolve insumos (Material) for Craftsman's catalog lookups.

Craftsman validates RecipeItem units via the catalog backend's ``get_product(sku)``
(reads ``.unit`` / ``.is_bundle``). An ingredient is a Material, not a Product, so
this adapter answers those lookups for ingredient skus. Composed with Offerman's
catalog backend in the orchestrator. No cross-core import at module top (ADR-001).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MaterialProductInfo:
    """Catalog view of a Material — duck-compatible with what Craftsman reads."""

    sku: str
    name: str
    unit: str
    description: str | None = None
    category: str | None = "insumo"
    base_price_q: int | None = None
    is_bundle: bool = False
    is_sellable: bool = False
    is_published: bool = True


class BuymanCatalogBackend:
    """CatalogBackend over Buyman's Material master (ingredient resolution)."""

    def get_product(self, sku: str) -> MaterialProductInfo | None:
        from shopman.buyman.models import Material

        material = Material.objects.filter(sku=sku).first()
        if material is None:
            return None
        return MaterialProductInfo(
            sku=material.sku,
            name=material.name,
            unit=material.unit,
            is_published=material.is_active,
        )
