// TS mirror da projeção de Expositores (shopman/backstage/projections/showcase.py).

export interface ShowcaseCollectionRef {
  ref: string;
  name: string;
  exists: boolean;
}

export interface ShowcaseProjection {
  ref: string;
  name: string;
  kind: "menuboard" | "google" | "meta";
  kind_label: string;
  kind_icon: string;
  capability: "display" | "feed";
  is_active: boolean;
  output_path: string;
  collections: ShowcaseCollectionRef[];
}

export interface CollectionOptionProjection {
  ref: string;
  name: string;
  product_count: number;
}

export interface ShowcaseBoardProjection {
  showcases: ShowcaseProjection[];
  all_collections: CollectionOptionProjection[];
}

export interface ShowcaseBoardResponse {
  board: ShowcaseBoardProjection;
}
