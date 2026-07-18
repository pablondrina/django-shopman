import { describe, expect, it } from "vitest";

import {
  availableAnywhere,
  cellPrice,
  cellState,
  cellSyncView,
  cellView,
  filterBySync,
  filterRows,
  pimSummary,
  rowStatus,
  surfaceIcon,
  syncBadge,
  syncErrorCount,
} from "../app/presentation/catalog";
import type {
  CatalogRowProjection,
  ProductSocial,
  SurfaceCellProjection,
  SurfaceProjection,
} from "../app/types/catalog";

const surface = (over: Partial<SurfaceProjection> = {}): SurfaceProjection => ({
  ref: "ifood",
  name: "iFood",
  is_projection_target: true,
  sync_status: "ok",
  kind: "channel",
  transactional: true,
  icon: "",
  is_active: true,
  output_path: "",
  ...over,
});

const cell = (over: Partial<SurfaceCellProjection> = {}): SurfaceCellProjection => ({
  surface_ref: "web",
  in_listing: true,
  is_published: true,
  is_sellable: true,
  available: true,
  price_q: 600,
  price_display: "R$ 6,00",
  sync_status: "",
  sync_error: "",
  synced_at: "",
  ...over,
});

const social = (over: Partial<ProductSocial> = {}): ProductSocial => ({
  brand: "",
  gtin: "",
  mpn: "",
  condition: "new",
  google_product_category: "",
  tiktok_category_id: "",
  hashtags: [],
  social_caption: "",
  has_data: false,
  ...over,
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
  keywords: ["padaria"],
  cells: [],
  social: social(),
  pim_complete: false,
  ...over,
});

describe("cellState", () => {
  it("available when product + listing both published/sellable", () => {
    expect(cellState(row(), cell())).toBe("available");
  });

  it("absent when not in the listing", () => {
    expect(cellState(row(), cell({ in_listing: false }))).toBe("absent");
  });

  it("paused when listing not sellable", () => {
    expect(cellState(row(), cell({ is_sellable: false }))).toBe("paused");
  });

  it("paused when the PRODUCT is not sellable (gates every surface)", () => {
    expect(cellState(row({ is_sellable: false }), cell())).toBe("paused");
  });

  it("unpublished when listing not published", () => {
    expect(cellState(row(), cell({ is_published: false }))).toBe("unpublished");
  });

  it("product unpublish gates every cell", () => {
    expect(cellState(row({ is_published: false }), cell())).toBe("unpublished");
  });
});

describe("cellView", () => {
  it("maps state to label + tone", () => {
    const v = cellView(row(), cell());
    expect(v.state).toBe("available");
    expect(v.label).toBe("Disponível");
    expect(v.toneClass).toContain("emerald");
  });
});

describe("filterRows", () => {
  const rows = [
    row({ sku: "PAO", name: "Pão", keywords: ["padaria"] }),
    row({ sku: "BOLO", name: "Bolo de Cenoura", keywords: ["doce"] }),
  ];
  it("returns all when query empty", () => {
    expect(filterRows(rows, "  ").length).toBe(2);
  });
  it("matches name", () => {
    expect(filterRows(rows, "cenoura").map((r) => r.sku)).toEqual(["BOLO"]);
  });
  it("matches sku case-insensitively", () => {
    expect(filterRows(rows, "pao").map((r) => r.sku)).toEqual(["PAO"]);
  });
  it("matches keyword", () => {
    expect(filterRows(rows, "doce").map((r) => r.sku)).toEqual(["BOLO"]);
  });
});

describe("surface metadata", () => {
  it("no sync badge for non-projection surfaces", () => {
    expect(syncBadge("na")).toBeNull();
    expect(syncBadge("ok")?.label).toBe("sincronizado");
  });
});

describe("cellPrice (preço só no delta)", () => {
  it("same when cell price equals the product base", () => {
    const view = cellPrice(row({ base_price_q: 500 }), cell({ price_q: 500 }));
    expect(view.delta).toBe("same");
    expect(view.differs).toBe(false);
  });
  it("up when the channel price is above base", () => {
    const view = cellPrice(row({ base_price_q: 500 }), cell({ price_q: 600 }));
    expect(view.delta).toBe("up");
    expect(view.differs).toBe(true);
  });
  it("down when the channel price is below base", () => {
    const view = cellPrice(row({ base_price_q: 500 }), cell({ price_q: 450 }));
    expect(view.delta).toBe("down");
    expect(view.differs).toBe(true);
  });
  it("falls back to base when the cell has no price (no false delta)", () => {
    const view = cellPrice(row({ base_price_q: 500 }), cell({ price_q: null }));
    expect(view.delta).toBe("same");
    expect(view.differs).toBe(false);
  });
});

describe("rowStatus (esmaecer quando 'fora')", () => {
  const cells = (over: Partial<SurfaceCellProjection>[] = []) =>
    over.map((o) => cell(o));

  it("ativo quando disponível em ao menos um canal", () => {
    const r = row({ cells: cells([{ available: true }, { available: false }]) });
    expect(availableAnywhere(r)).toBe(true);
    expect(rowStatus(r).off).toBe(false);
    expect(rowStatus(r).label).toBe("");
  });

  it("Despublicado quando o produto está despublicado (nível-produto)", () => {
    const r = row({ is_published: false, cells: cells([{ available: false }]) });
    expect(rowStatus(r)).toEqual({ off: true, label: "Despublicado", tone: "muted" });
  });

  it("Pausado quando o produto está pausado (globalzinho)", () => {
    const r = row({ is_sellable: false, cells: cells([{ available: false }]) });
    expect(rowStatus(r)).toEqual({ off: true, label: "Pausado", tone: "amber" });
  });

  it("Indisponível quando cada canal foi pausado individualmente (sem pausa global)", () => {
    const r = row({
      is_published: true,
      is_sellable: true,
      cells: cells([
        { in_listing: true, available: false },
        { in_listing: true, available: false },
      ]),
    });
    expect(availableAnywhere(r)).toBe(false);
    expect(rowStatus(r)).toEqual({ off: true, label: "Indisponível", tone: "amber" });
  });

  it("não marca 'Indisponível' um produto sem nenhuma listing", () => {
    const r = row({ cells: cells([{ in_listing: false, available: false }]) });
    expect(rowStatus(r).off).toBe(false);
  });

  it("Esgotado (estoque) — ortogonal à pausa, tom danger p/ diferenciar", () => {
    const r = row({
      is_published: true,
      is_sellable: true,
      sold_out: true,
      cells: cells([{ in_listing: true, available: true }]), // switch ligado, mas sem estoque
    });
    expect(rowStatus(r)).toEqual({ off: true, label: "Esgotado", tone: "danger" });
  });

  it("Pausado tem precedência sobre Esgotado", () => {
    const r = row({ is_sellable: false, sold_out: true, cells: cells([{ available: false }]) });
    expect(rowStatus(r).label).toBe("Pausado");
  });
});

describe("surfaceIcon", () => {
  it("maps known channels to distinct icons", () => {
    expect(surfaceIcon("pdv")).toContain("store");
    expect(surfaceIcon("ifood")).toContain("bike");
    expect(surfaceIcon("web")).toContain("globe");
  });
  it("falls back for unknown refs", () => {
    expect(surfaceIcon("tiktok")).toBe("lucide:radio-tower");
  });
});

// ── Arc H: sync por célula + filtro por estado + PIM ───────────────────────────

describe("cellSyncView (selo de sync por célula)", () => {
  const ifood = surface({ ref: "ifood", is_projection_target: true });
  const web = surface({ ref: "web", is_projection_target: false });

  it("esconde o selo em superfície que não projeta", () => {
    const v = cellSyncView(web, cell({ surface_ref: "web", sync_status: "" }));
    expect(v.show).toBe(false);
    expect(v.actionable).toBe(false);
  });

  it("synced = verde, não acionável", () => {
    const v = cellSyncView(ifood, cell({ surface_ref: "ifood", sync_status: "synced" }));
    expect(v.show).toBe(true);
    expect(v.actionable).toBe(false);
    expect(v.toneClass).toContain("emerald");
  });

  it("error e pending são acionáveis (oferecem reenvio)", () => {
    expect(cellSyncView(ifood, cell({ sync_status: "error" })).actionable).toBe(true);
    expect(cellSyncView(ifood, cell({ sync_status: "pending" })).actionable).toBe(true);
  });

  it("alvo de projeção sem registro = 'nunca', acionável quando na listing", () => {
    const inList = cellSyncView(ifood, cell({ sync_status: "", in_listing: true }));
    expect(inList.show).toBe(true);
    expect(inList.actionable).toBe(true);
    expect(inList.label).toBe("Nunca sincronizado");
    // fora da listing → nada a reenviar
    expect(cellSyncView(ifood, cell({ sync_status: "", in_listing: false })).actionable).toBe(false);
  });

  it("superfície ausente (undefined) = sem selo", () => {
    expect(cellSyncView(undefined, cell()).show).toBe(false);
  });
});

describe("filterBySync (recorte por saúde de publicação)", () => {
  const surfaces = [
    surface({ ref: "ifood", is_projection_target: true }),
    surface({ ref: "web", is_projection_target: false, transactional: true }),
  ];
  const rows = [
    row({ sku: "A", cells: [cell({ surface_ref: "ifood", sync_status: "synced" })] }),
    row({ sku: "B", cells: [cell({ surface_ref: "ifood", sync_status: "error" })] }),
    row({ sku: "C", cells: [cell({ surface_ref: "ifood", sync_status: "pending" })] }),
    // fora do ar (despublicado) — casa "unpublished", ignora o sync
    row({ sku: "D", is_published: false, cells: [cell({ surface_ref: "ifood", sync_status: "" })] }),
  ];

  it("all devolve tudo", () => {
    expect(filterBySync(rows, surfaces, "all").map((r) => r.sku)).toEqual(["A", "B", "C", "D"]);
  });
  it("error só linhas com célula em erro (superfície-alvo)", () => {
    expect(filterBySync(rows, surfaces, "error").map((r) => r.sku)).toEqual(["B"]);
  });
  it("synced só as sincronizadas", () => {
    expect(filterBySync(rows, surfaces, "synced").map((r) => r.sku)).toEqual(["A"]);
  });
  it("pending só as em andamento", () => {
    expect(filterBySync(rows, surfaces, "pending").map((r) => r.sku)).toEqual(["C"]);
  });
  it("unpublished usa o status da linha, não o sync", () => {
    expect(filterBySync(rows, surfaces, "unpublished").map((r) => r.sku)).toEqual(["D"]);
  });
  it("ignora sync de superfície que não projeta", () => {
    const rowsWeb = [row({ sku: "X", cells: [cell({ surface_ref: "web", sync_status: "error" })] })];
    expect(filterBySync(rowsWeb, surfaces, "error")).toEqual([]);
  });
});

describe("syncErrorCount", () => {
  const surfaces = [
    surface({ ref: "ifood", is_projection_target: true }),
    surface({ ref: "meta", is_projection_target: true }),
    surface({ ref: "web", is_projection_target: false }),
  ];
  it("conta só erros em superfície-alvo", () => {
    const r = row({
      cells: [
        cell({ surface_ref: "ifood", sync_status: "error" }),
        cell({ surface_ref: "meta", sync_status: "error" }),
        cell({ surface_ref: "web", sync_status: "error" }), // não projeta → não conta
      ],
    });
    expect(syncErrorCount(r, surfaces)).toBe(2);
  });
  it("zero quando não há erro", () => {
    expect(syncErrorCount(row({ cells: [cell({ sync_status: "synced" })] }), surfaces)).toBe(0);
  });
});

describe("pimSummary", () => {
  it("completo quando tem marca e categoria", () => {
    const r = row({
      pim_complete: true,
      social: social({ brand: "Nelson", google_product_category: "Food", gtin: "7891000100103" }),
    });
    const s = pimSummary(r);
    expect(s.complete).toBe(true);
    expect(s.missing).toEqual([]);
    expect(s.filled).toBe(3);
  });
  it("lista o que falta p/ feed", () => {
    const s = pimSummary(row({ pim_complete: false, social: social({ brand: "Nelson" }) }));
    expect(s.complete).toBe(false);
    expect(s.missing).toEqual(["categoria"]);
    expect(s.filled).toBe(1);
  });
  it("sem PIM → falta marca e categoria", () => {
    expect(pimSummary(row()).missing).toEqual(["marca", "categoria"]);
  });
});
