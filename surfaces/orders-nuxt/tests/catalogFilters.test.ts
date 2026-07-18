import { describe, expect, it } from "vitest";

import {
  FILTER_PIM,
  FILTER_PUBLISHED,
  FILTER_SELLABLE,
  FILTER_STOCK,
  FILTER_SURFACE,
  FILTER_SYNC,
  catalogDimensions,
  filterByDimensions,
  stockBucket,
} from "../app/presentation/catalogFilters";
import type {
  CatalogRowProjection,
  ProductSocial,
  SurfaceCellProjection,
  SurfaceProjection,
} from "../app/types/catalog";

const surface = (over: Partial<SurfaceProjection> = {}): SurfaceProjection => ({
  ref: "ifood",
  name: "iFood",
  short_name: "iFood",
  is_projection_target: true,
  sync_status: "ok",
  kind: "channel",
  transactional: true,
  icon: "",
  is_active: true,
  output_path: "",
  sync_key: "ifood",
  ...over,
});

const cell = (over: Partial<SurfaceCellProjection> = {}): SurfaceCellProjection => ({
  surface_ref: "ifood",
  in_listing: true,
  is_published: true,
  is_sellable: true,
  available: true,
  price_q: 600,
  price_display: "R$ 6,00",
  sync_status: "synced",
  sync_error: "",
  synced_at: "",
  ...over,
});

const social = (): ProductSocial => ({
  brand: "",
  gtin: "",
  mpn: "",
  condition: "new",
  google_product_category: "",
  tiktok_category_id: "",
  hashtags: [],
  social_caption: "",
  has_data: false,
});

const row = (over: Partial<CatalogRowProjection> = {}): CatalogRowProjection => ({
  sku: "PAO",
  name: "Pão",
  image_url: "",
  primary_collection: "",
  primary_collection_name: "",
  is_published: true,
  is_sellable: true,
  base_price_q: 500,
  base_price_display: "R$ 5,00",
  edit_url: "",
  stock_tracked: true,
  stock_qty: 10,
  sold_out: false,
  low_stock: false,
  replenish_qty: 0,
  keywords: [],
  cells: [cell()],
  social: social(),
  pim_complete: false,
  ...over,
});

const surfaces = [
  surface({ ref: "ifood", name: "iFood", is_projection_target: true }),
  surface({ ref: "web", name: "Site", is_projection_target: false }),
];

describe("catalogDimensions", () => {
  it("oferece as 6 dimensões (coleção fica de fora — é o eixo das pills)", () => {
    const ids = catalogDimensions(surfaces, [row()]).map((d) => d.id);
    expect(ids).toEqual([FILTER_SYNC, FILTER_SURFACE, FILTER_PUBLISHED, FILTER_SELLABLE, FILTER_STOCK, FILTER_PIM]);
  });

  it("sem plataforma que projeta, envio e dados sociais somem", () => {
    const ids = catalogDimensions([surface({ ref: "web", is_projection_target: false })], [row()]).map((d) => d.id);
    expect(ids).toEqual([FILTER_SURFACE, FILTER_PUBLISHED, FILTER_SELLABLE, FILTER_STOCK]);
  });

  it("canais e feeds vêm da lista viva de superfícies", () => {
    const dimension = catalogDimensions(surfaces, [row()]).find((d) => d.id === FILTER_SURFACE)!;
    expect(dimension.options.map((o) => o.value)).toEqual(["ifood", "web"]);
    expect(dimension.options[0]!.label).toBe("iFood");
  });

  it("conta por opção isolada", () => {
    const rows = [
      row({ sku: "A", sold_out: true }),
      row({ sku: "B", low_stock: true }),
      row({ sku: "C" }),
    ];
    const stock = catalogDimensions(surfaces, rows).find((d) => d.id === FILTER_STOCK)!;
    expect(Object.fromEntries(stock.options.map((o) => [o.value, o.count]))).toEqual({ ok: 1, low: 1, out: 1 });
  });
});

describe("stockBucket", () => {
  it("esgotado ganha de estoque baixo", () => {
    expect(stockBucket(row({ sold_out: true, low_stock: true }))).toBe("out");
    expect(stockBucket(row({ low_stock: true }))).toBe("low");
    expect(stockBucket(row())).toBe("ok");
  });
});

describe("filterByDimensions", () => {
  const rows = [
    row({ sku: "A", cells: [cell({ sync_status: "synced" })] }),
    row({ sku: "B", cells: [cell({ sync_status: "error" })], is_published: false }),
    row({ sku: "C", cells: [cell({ sync_status: "" })], sold_out: true, pim_complete: true }),
    row({ sku: "D", cells: [cell({ surface_ref: "web", sync_status: "error" })], is_sellable: false }),
  ];
  const skus = (filters: Parameters<typeof filterByDimensions>[2]) =>
    filterByDimensions(rows, surfaces, filters).map((r) => r.sku);

  it("sem filtro devolve tudo", () => {
    expect(skus({})).toEqual(["A", "B", "C", "D"]);
  });

  it("envio: 'nunca' casa a célula sem sync em superfície que projeta", () => {
    expect(skus({ [FILTER_SYNC]: ["never"] })).toEqual(["C"]);
  });

  it("envio: dentro da dimensão é OU", () => {
    expect(skus({ [FILTER_SYNC]: ["error", "synced"] })).toEqual(["A", "B"]);
  });

  it("envio ignora superfície que não projeta", () => {
    expect(skus({ [FILTER_SYNC]: ["error"] })).toEqual(["B"]);
  });

  it("canal/feed casa quem está ofertado ali", () => {
    expect(skus({ [FILTER_SURFACE]: ["web"] })).toEqual(["D"]);
  });

  it("publicado e à venda recortam pelo lado escolhido (\"false\" filtra)", () => {
    expect(skus({ [FILTER_PUBLISHED]: ["false"] })).toEqual(["B"]);
    expect(skus({ [FILTER_SELLABLE]: ["false"] })).toEqual(["D"]);
  });

  it("estoque recorta pelo balde da linha", () => {
    expect(skus({ [FILTER_STOCK]: ["out"] })).toEqual(["C"]);
  });

  it("dados sociais completos", () => {
    expect(skus({ [FILTER_PIM]: ["true"] })).toEqual(["C"]);
  });

  it("entre dimensões é E", () => {
    expect(skus({ [FILTER_STOCK]: ["out"], [FILTER_PUBLISHED]: ["false"] })).toEqual([]);
    expect(skus({ [FILTER_STOCK]: ["out"], [FILTER_PIM]: ["true"] })).toEqual(["C"]);
  });

  it("lista vazia numa dimensão não recorta nada", () => {
    expect(skus({ [FILTER_SYNC]: [] })).toEqual(["A", "B", "C", "D"]);
    expect(skus({ [FILTER_PUBLISHED]: [] })).toEqual(["A", "B", "C", "D"]);
  });
});
