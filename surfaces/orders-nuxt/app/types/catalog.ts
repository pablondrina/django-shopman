// TS mirror of the Django catalog matrix projection
// (shopman/backstage/projections/catalog.py), serialised by backstage/api/projections.py.
// Kept in lockstep — the surface renders intent, the backend owns rules.

export type SurfaceSyncStatus = "ok" | "error" | "never" | "na";
export type SurfaceKind = "channel" | "display" | "feed";

// Uma coluna da matriz é uma SUPERFÍCIE: um Canal de venda (transacional) OU um
// Expositor que só EXIBE (📺 menuboard / 🛰 feed Google/Meta). Expositor não vende:
// a célula só pausa/reativa o item, sem preço nem publicação. A pausa global do
// produto gateia canais E expositores.
export interface SurfaceProjection {
  ref: string;
  name: string;
  is_projection_target: boolean;
  sync_status: SurfaceSyncStatus;
  kind: SurfaceKind;
  transactional: boolean; // canal vende (preço/publicação); expositor só exibe (pausa)
  icon: string; // dica de ícone p/ expositores (tv/rss); vazio p/ canal
  is_active: boolean; // expositor ligado/desligado (canal sempre ativo aqui)
  output_path: string; // saída pública do expositor (abrir/prever); vazio p/ canal
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
  stock_tracked: boolean;
  stock_qty: number | null;
  sold_out: boolean;
  low_stock: boolean;
  replenish_qty: number;
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
