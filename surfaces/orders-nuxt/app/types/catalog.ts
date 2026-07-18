// TS mirror of the Django catalog matrix projection
// (shopman/backstage/projections/catalog.py), serialised by backstage/api/projections.py.
// Kept in lockstep — the surface renders intent, the backend owns rules.

export type SurfaceSyncStatus = "ok" | "error" | "never" | "na";
export type SurfaceKind = "channel" | "display" | "feed";

// Estado de sync por CÉLULA (produto × plataforma) — CatalogSyncState (Arc C).
// "" = nunca sincronizado / superfície que não projeta (feed de pull).
export type CellSyncStatus = "synced" | "pending" | "error" | "retracted" | "skipped" | "";

// Atributos PIM sociais da linha (Arc A) — Product.metadata['social'].
export interface ProductSocial {
  brand: string;
  gtin: string;
  mpn: string;
  condition: string;
  google_product_category: string;
  tiktok_category_id: string;
  hashtags: string[];
  social_caption: string;
  has_data: boolean;
}

// Uma coluna da matriz é uma SUPERFÍCIE: um Canal de venda (transacional) OU um
// Feed, que só EMPURRA dados para fora (📺 menuboard / 🛰 Google/Meta). Feed não
// vende: a célula só pausa/reativa o item, sem preço nem publicação. A pausa global
// do produto gateia canais E feeds. No backend o model chama-se ``Showcase``.
export interface SurfaceProjection {
  ref: string;
  name: string;
  short_name: string; // rótulo curto do cabeçalho; nunca vazio (cai para `name`)
  is_projection_target: boolean;
  sync_status: SurfaceSyncStatus;
  kind: SurfaceKind;
  transactional: boolean; // canal vende (preço/publicação); feed só exibe (pausa)
  icon: string; // dica de ícone p/ feeds (tv/rss); vazio p/ canal
  is_active: boolean; // feed ligado/desligado (canal sempre ativo aqui)
  output_path: string; // saída pública do feed (abrir/prever); vazio p/ canal
  sync_key: string; // chave no CatalogSyncState.platform (ref p/ canais, kind p/ showcases)
}

export interface SurfaceCellProjection {
  surface_ref: string;
  in_listing: boolean;
  is_published: boolean;
  is_sellable: boolean;
  available: boolean;
  price_q: number | null;
  price_display: string;
  sync_status: CellSyncStatus; // estado do último push p/ esta plataforma
  sync_error: string; // mensagem do erro (quando sync_status="error")
  synced_at: string; // ISO do último push OK (vazio = nunca)
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
  social: ProductSocial; // atributos PIM sociais (Arc A)
  pim_complete: boolean; // tem o essencial p/ feed (brand + categoria Google)
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

// Tabela nutricional (ANVISA) — espelha a dataclass `offerman.nutrition.NutritionFacts`.
// `auto_filled` é sentinel interno (derivação a partir da receita) e não é editável
// aqui: o backend o zera sozinho quando o operador digita.
export interface NutritionFacts {
  serving_size_g: number;
  servings_per_container: number;
  energy_kcal: number | null;
  carbohydrates_g: number | null;
  sugars_g: number | null;
  proteins_g: number | null;
  total_fat_g: number | null;
  saturated_fat_g: number | null;
  trans_fat_g: number | null;
  fiber_g: number | null;
  sodium_mg: number | null;
}

// Classificação fiscal do produto — espelha `fiscalman.classification`.
// O que NÃO é por produto (CFOP, CSOSN, origem, PIS/COFINS) vem do perfil.
export interface ProductFiscal {
  profile: string;
  ncm: string;
  cest: string;
  unit: string;
}

export interface FiscalProfileChoice {
  key: string;
  name: string;
  requires_cest: boolean;
}

// Detalhe de UM produto — tudo que o painel de produto edita
// (GET/PATCH /api/v1/backstage/catalog/product/<sku>/). Espelha
// `backstage.services.catalog._detail_payload`. Fora daqui (segue no Admin):
// componentes de bundle, coleções e listings.
export interface ProductDetailProjection {
  readonly sku: string;
  name: string;
  short_description: string;
  long_description: string;
  keywords: string[];
  base_price_q: number;
  unit: string;
  unit_weight_g: number | null;
  availability_policy: string;
  shelf_life_days: number | null;
  storage_tip: string;
  production_cycle_hours: number | null;
  is_batch_produced: boolean;
  is_published: boolean;
  is_sellable: boolean;
  ingredients_text: string;
  image_url: string;
  // rotulagem de compra remota (Product.metadata) — o cliente não pega o produto
  // na mão, então alérgenos e restrições precisam estar escritos.
  allergens: string[];
  dietary_info: string[];
  serves: string;
  approx_dimensions: string;
  allows_next_day_sale: boolean;
  nutrition_facts: NutritionFacts;
  social: ProductSocial;
  fiscal: ProductFiscal;
  readonly primary_collection: string;
  readonly primary_collection_name: string;
  // somente-leitura: dado veio da receita; editar à mão congela a derivação.
  readonly dietary_auto_filled: boolean;
  readonly nutrition_auto_filled: boolean;
  readonly fiscal_profiles: FiscalProfileChoice[];
}

// Merge parcial: só as chaves presentes são gravadas. `social` e `fiscal` também
// fazem merge por dentro (mandar só `brand` não apaga a categoria).
export type ProductDetailPatch = Partial<
  Omit<
    ProductDetailProjection,
    | "sku"
    | "primary_collection"
    | "primary_collection_name"
    | "dietary_auto_filled"
    | "nutrition_auto_filled"
    | "fiscal_profiles"
    | "social"
    | "fiscal"
    | "nutrition_facts"
  >
> & {
  social?: Partial<Omit<ProductSocial, "has_data">>;
  fiscal?: Partial<ProductFiscal>;
  nutrition_facts?: Partial<NutritionFacts>;
};

export interface ProductDetailResponse {
  product: ProductDetailProjection;
}

// Assist de IA — sugestão de conteúdo para UM campo de texto de UM produto
// (POST /api/v1/backstage/catalog/ai-assist/). É sempre por campo: o operador
// aceita ou descarta cada sugestão sozinha, e nada é gravado até ele salvar.
// Espelha `backstage.services.catalog.ASSISTABLE_FIELDS`.
export type AssistableField =
  | "short_description"
  | "long_description"
  | "ingredients_text"
  | "social_caption"
  | "hashtags";

export interface AiAssistRequest {
  sku: string;
  field: AssistableField;
  current_value: string;
  context?: Record<string, unknown>;
}

// `hashtags` volta como texto separado por espaço — o painel já normaliza texto
// livre em lista, então o contrato é uma string para todos os campos.
export interface AiAssistResponse {
  suggestion: string;
}
