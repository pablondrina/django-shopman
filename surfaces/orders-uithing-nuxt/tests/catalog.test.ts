import { describe, expect, it } from "vitest";

import {
  cellDot,
  cellPrice,
  cellState,
  cellTint,
  cellView,
  filterRows,
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

describe("heatmap chrome", () => {
  it("tints available cells green and paused amber", () => {
    expect(cellTint("available")).toContain("emerald");
    expect(cellTint("paused")).toContain("amber");
    expect(cellTint("absent")).not.toContain("emerald");
  });
  it("dots match the state", () => {
    expect(cellDot("available")).toContain("emerald");
    expect(cellDot("paused")).toContain("amber");
    expect(cellDot("absent")).toContain("transparent");
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
