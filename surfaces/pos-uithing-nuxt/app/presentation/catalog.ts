// Presentation — catalog shaping for the Sale Workspace grid.
//
// Pure transforms over the catalog Projection: ordering the category rail,
// filtering the product grid, and the calm tile fallback visual. No price or
// availability arithmetic — those are sealed in the Projection (price_display,
// is_d1) and only rendered here.

import type { POSCollectionProjection, POSProductProjection } from "~/types/pos";

/** Favourites first (Projection-driven), then alphabetical (pt-BR). */
export function orderCollections(
  collections: POSCollectionProjection[],
  favoriteRefs: Iterable<string>,
): POSCollectionProjection[] {
  const favorites = new Set(favoriteRefs);
  return [...collections].sort((a, b) => {
    const aFavorite = favorites.has(a.ref) ? 0 : 1;
    const bFavorite = favorites.has(b.ref) ? 0 : 1;
    return aFavorite - bFavorite || a.name.localeCompare(b.name, "pt-BR");
  });
}

/** Filter the grid by active collection and a free-text query (name or SKU). */
export function filterProducts(
  products: POSProductProjection[],
  options: { collectionRef?: string; query?: string } = {},
): POSProductProjection[] {
  const collectionRef = options.collectionRef || "";
  const normalized = (options.query || "").trim().toLowerCase();
  return products.filter((product) => {
    if (collectionRef && product.collection_ref !== collectionRef) return false;
    if (!normalized) return true;
    return product.name.toLowerCase().includes(normalized)
      || product.sku.toLowerCase().includes(normalized);
  });
}

/**
 * Deterministic, calm hue for products without a photo — derived from the
 * collection ref so a whole collection shares a family tint (Odoo-style colour
 * coding), kept low-saturation so the grid stays calm, not marketing.
 */
export function productFallbackHue(product: POSProductProjection): number {
  const seed = product.collection_ref || product.sku || product.name;
  let hash = 0;
  for (let i = 0; i < seed.length; i += 1) {
    hash = (hash * 31 + seed.charCodeAt(i)) % 360;
  }
  return hash;
}

export function productFallbackStyle(product: POSProductProjection): { background: string } {
  const hue = productFallbackHue(product);
  return {
    background: `linear-gradient(135deg, hsl(${hue} 42% 92%), hsl(${(hue + 24) % 360} 38% 85%))`,
  };
}

export function productMonogram(product: POSProductProjection): string {
  return (product.name?.trim()?.[0] || "·").toUpperCase();
}
