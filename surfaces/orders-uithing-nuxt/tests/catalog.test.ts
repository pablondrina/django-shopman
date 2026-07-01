import { describe, expect, it } from "vitest";

import {
  availableAnywhere,
  cellPrice,
  cellState,
  cellView,
  filterRows,
  rowStatus,
  surfaceIcon,
  syncBadge,
} from "../app/presentation/catalog";
import type { CatalogRowProjection, SurfaceCellProjection } from "../app/types/catalog";

const cell = (over: Partial<SurfaceCellProjection> = {}): SurfaceCellProjection => ({
  surface_ref: "web",
  in_listing: true,
  is_published: true,
  is_sellable: true,
  available: true,
  price_q: 600,
  price_display: "R$ 6,00",
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

  it("Esgotado (estoque) — ortogonal à pausa, tom neutro", () => {
    const r = row({
      is_published: true,
      is_sellable: true,
      sold_out: true,
      cells: cells([{ in_listing: true, available: true }]), // switch ligado, mas sem estoque
    });
    expect(rowStatus(r)).toEqual({ off: true, label: "Esgotado", tone: "muted" });
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
