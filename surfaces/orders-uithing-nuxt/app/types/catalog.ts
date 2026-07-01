// TS mirror of the Django catalog matrix projection
// (shopman/backstage/projections/catalog.py), serialised by backstage/api/projections.py.
// Kept in lockstep — the surface renders intent, the backend owns rules.

export type SurfaceSyncStatus = "ok" | "error" | "never" | "na";

// Uma coluna da matriz é um CANAL de venda (transacional). Exibição/feed (menuboard,
// Google, Meta) são Expositores, geridos no Admin — não aparecem aqui.
export interface SurfaceProjection {
  ref: string;
  name: string;
  is_projection_target: boolean;
  sync_status: SurfaceSyncStatus;
}

export interface SurfaceCellProjection {
  surface_ref: string;
  in_listing: boolean;
  is_published: boolean;
  is_sellable: boolean;
  available: boolean;
  price_q: number | null;
  price_display: string;
}

export interface CatalogRowProjection {
  sku: string;
  name: string;
  image_url: string;
  primary_collection: string;
  primary_collection_name: string;
  is_published: boolean;
  is_sellable: boolean;
  base_price_q: number;
  base_price_display: string;
  edit_url: string;
  keywords: string[];
  cells: SurfaceCellProjection[];
}

export interface CollectionProjection {
  ref: string;
  name: string;
  is_smart: boolean;
  product_count: number;
}

export interface CatalogMatrixProjection {
  surfaces: SurfaceProjection[];
  rows: CatalogRowProjection[];
  collections: CollectionProjection[];
}

export interface CatalogMatrixResponse {
  matrix: CatalogMatrixProjection;
}
