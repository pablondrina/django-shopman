import { describe, expect, it } from "vitest";

import type { Action, POSCollectionProjection, POSProductProjection, POSTabProjection } from "../app/types/pos";
import { findAction, hasAction, resolveAffordance } from "../app/presentation/actions";
import {
  filterProducts,
  orderCollections,
  productFallbackHue,
  productFallbackStyle,
  productMonogram,
} from "../app/presentation/catalog";
import { countOpenTabs, filterTabs, sanitizeTabRef, sortTabs, tabCardView } from "../app/presentation/tabBoard";
import { clampPercent, clampQty, popDigit, pushDigit } from "../app/presentation/numpad";

function action(overrides: Partial<Action> & { ref: string }): Action {
  return {
    kind: "mutation",
    label: "",
    priority: "secondary",
    enabled: true,
    reason: "",
    href: "",
    method: "POST",
    payload_schema: {},
    idempotency: "none",
    confirmation: {},
    ...overrides,
  };
}

function product(overrides: Partial<POSProductProjection> & { sku: string }): POSProductProjection {
  return {
    name: overrides.sku,
    price_q: 0,
    price_display: "",
    collection_ref: "",
    is_d1: false,
    image_url: "",
    ...overrides,
  };
}

function tab(overrides: Partial<POSTabProjection> & { ref: string }): POSTabProjection {
  return {
    display_ref: overrides.ref,
    session_key: "",
    state: "empty",
    status_label: "",
    status_class: "",
    customer_name: "",
    customer_phone: "",
    item_count: 0,
    line_count: 0,
    total_display: "",
    last_touched_display: "",
    items_preview: "",
    ...overrides,
  };
}

describe("presentation/actions — Action → affordance", () => {
  const actions = [
    action({ ref: "open_tab", label: "Abrir", href: "/api/v1/backstage/pos/tabs/{tab_ref}/open/" }),
    action({ ref: "fire_tab", label: "Cozinha", enabled: false, reason: "Caixa fechado", priority: "primary" }),
  ];

  it("finds actions and reports presence", () => {
    expect(findAction(actions, "open_tab")?.label).toBe("Abrir");
    expect(findAction(actions, "missing")).toBeUndefined();
    expect(hasAction(actions, "fire_tab")).toBe(true);
    expect(hasAction(actions, "missing")).toBe(false);
  });

  it("substitutes path params into the concrete href", () => {
    const aff = resolveAffordance(actions, "open_tab", { params: { tab_ref: "00001007" } });
    expect(aff.present).toBe(true);
    expect(aff.enabled).toBe(true);
    expect(aff.href).toBe("/api/v1/backstage/pos/tabs/00001007/open/");
  });

  it("reflects enabled/reason verbatim from the projection (zero policy)", () => {
    const aff = resolveAffordance(actions, "fire_tab");
    expect(aff.enabled).toBe(false);
    expect(aff.reason).toBe("Caixa fechado");
    expect(aff.priority).toBe("primary");
  });

  it("returns an absent affordance with the fallback href when the action is missing", () => {
    const aff = resolveAffordance(actions, "close_sale", { fallbackHref: "/fallback/" });
    expect(aff.present).toBe(false);
    expect(aff.enabled).toBe(false);
    expect(aff.href).toBe("/fallback/");
    expect(aff.method).toBe("POST");
  });
});

describe("presentation/catalog — grid shaping", () => {
  const collections: POSCollectionProjection[] = [
    { ref: "doces", name: "Doces" },
    { ref: "paes", name: "Pães" },
    { ref: "bebidas", name: "Bebidas" },
  ];

  it("orders favourites first, then alphabetically (pt-BR)", () => {
    expect(orderCollections(collections, ["paes"]).map((c) => c.ref)).toEqual([
      "paes",
      "bebidas",
      "doces",
    ]);
  });

  it("filters by collection and query (name or sku)", () => {
    const products = [
      product({ sku: "PAO-FRANCES", name: "Pão Francês", collection_ref: "paes" }),
      product({ sku: "CROISSANT", name: "Croissant", collection_ref: "paes" }),
      product({ sku: "CAFE", name: "Café", collection_ref: "bebidas" }),
    ];
    expect(filterProducts(products, { collectionRef: "paes" }).map((p) => p.sku)).toEqual([
      "PAO-FRANCES",
      "CROISSANT",
    ]);
    expect(filterProducts(products, { query: "cafe" }).map((p) => p.sku)).toEqual(["CAFE"]);
    expect(filterProducts(products, { query: "croiss" }).map((p) => p.sku)).toEqual(["CROISSANT"]);
    expect(filterProducts(products, {}).length).toBe(3);
  });

  it("derives a deterministic, calm fallback visual", () => {
    const p = product({ sku: "X", name: "Bolo", collection_ref: "doces" });
    expect(productFallbackHue(p)).toBe(productFallbackHue(p));
    expect(productFallbackStyle(p).background).toContain("linear-gradient");
    expect(productMonogram(p)).toBe("B");
    expect(productMonogram(product({ sku: "Y", name: "" }))).toBe("·");
  });
});

describe("presentation/tabBoard — board shaping", () => {
  const tabs = [
    tab({ ref: "00001003", state: "empty", status_label: "Livre" }),
    tab({ ref: "00001001", state: "in_use", status_label: "Em uso", item_count: 2, total_display: "R$ 24,00", customer_name: "Ana" }),
    tab({ ref: "00001002", state: "in_use", status_label: "Em uso", item_count: 1, total_display: "R$ 8,00", fired: true }),
  ];

  it("sorts open tabs first, then numerically by display ref", () => {
    expect(sortTabs(tabs).map((t) => t.ref)).toEqual(["00001001", "00001002", "00001003"]);
  });

  it("filters and counts the in-use tabs", () => {
    expect(filterTabs(tabs, "in_use").map((t) => t.ref)).toEqual(["00001001", "00001002"]);
    expect(filterTabs(tabs, "all").length).toBe(3);
    expect(countOpenTabs(tabs)).toBe(2);
  });

  it("builds the per-tab card view", () => {
    const open = tabCardView(tabs[1]!, "00001001");
    expect(open).toMatchObject({
      displayRef: "00001001",
      isInUse: true,
      isFree: false,
      isUnpaid: false,
      identity: "Ana",
      summary: "2 itens · R$ 24,00",
      selected: true,
    });

    const free = tabCardView(tabs[0]!);
    expect(free).toMatchObject({ isFree: true, summary: "Comanda livre", identity: "—", selected: false });

    const fired = tabCardView(tabs[2]!);
    expect(fired).toMatchObject({ isUnpaid: true, summary: "1 item · R$ 8,00" });
  });

  it("sanitizes a tab ref to the channel's allowed shape", () => {
    const opts = { maxLength: 8, disallowedChars: ["/", "#"] };
    // Collapses runs of whitespace to one space (does not trim — faithful to the
    // original) and clamps to maxLength.
    expect(sanitizeTabRef("Mesa  12", opts)).toBe("Mesa 12");
    expect(sanitizeTabRef("a/b#c", opts)).toBe("abc");
    expect(sanitizeTabRef("123456789", opts)).toBe("12345678");
    expect(sanitizeTabRef("li\tn\ne", opts)).toBe("line");
  });
});

describe("presentation/numpad — quantity/discount buffer", () => {
  it("replaces on the first fresh keystroke, then appends up to maxLength", () => {
    expect(pushDigit("5", "3", { fresh: true, maxLength: 3 })).toBe("3");
    expect(pushDigit("3", "2", { fresh: false, maxLength: 3 })).toBe("32");
    expect(pushDigit("999", "1", { fresh: false, maxLength: 3 })).toBe("999");
    expect(pushDigit("12", "a", { fresh: false, maxLength: 3 })).toBe("12");
  });

  it("pops the last digit", () => {
    expect(popDigit("123")).toBe("12");
    expect(popDigit("")).toBe("");
  });

  it("clamps quantity and discount percentage", () => {
    expect(clampQty("500", 999)).toBe(500);
    expect(clampQty("1500", 999)).toBe(999);
    expect(clampQty("", 999)).toBe(0);
    expect(clampPercent("40")).toBe(40);
    expect(clampPercent("150")).toBe(100);
  });
});
