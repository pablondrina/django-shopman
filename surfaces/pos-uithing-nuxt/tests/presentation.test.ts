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
import {
  cashDeltaPresets,
  collectionsForFulfillment,
  injectableMethods,
  isPaymentCovered,
  methodLabel,
  paymentChangeQ,
  paymentIcon,
  paymentProofView,
  paymentRemainingQ,
  qrCodeSrc,
  tenderLineView,
  tenderSumQ,
} from "../app/presentation/payment";
import { formatOpenedAt, isTerminalOccupied, movementLabel } from "../app/presentation/cash";
import { formatBRL } from "../app/utils/posIntent";
import type {
  POSCashRuntimeProjection,
  POSCheckoutContractProjection,
  POSPaymentCollectionProjection,
  POSPaymentMethodProjection,
  POSPaymentResultProjection,
  POSPaymentTenderDraft,
} from "../app/types/pos";

function tender(method: string, amountQ: number): POSPaymentTenderDraft {
  return { method, amount_q: amountQ, collection: "terminal" };
}

const METHODS: POSPaymentMethodProjection[] = [
  { ref: "cash", label: "Dinheiro" },
  { ref: "pix", label: "PIX" },
  { ref: "card", label: "Cartão" },
  { ref: "mixed", label: "Misto" },
];

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

describe("presentation/payment — tender math & method affordance", () => {
  it("drops the derived 'mixed' pseudo-method from the injectable buttons", () => {
    expect(injectableMethods(METHODS).map((method) => method.ref)).toEqual(["cash", "pix", "card"]);
  });

  it("resolves the method label and icon, with fallbacks", () => {
    expect(methodLabel("pix", METHODS)).toBe("PIX");
    expect(methodLabel("unknown", METHODS)).toBe("unknown");
    expect(paymentIcon("cash")).toBe("lucide:banknote");
    expect(paymentIcon("weird")).toBe("lucide:wallet");
  });

  it("sums tenders and derives remaining/change/covered against the authoritative total", () => {
    const tenders = [tender("cash", 3000), tender("pix", 1000)];
    expect(tenderSumQ(tenders)).toBe(4000);
    expect(paymentRemainingQ(tenders, 5000)).toBe(1000);
    expect(paymentRemainingQ(tenders, 3500)).toBe(-500);
    expect(paymentChangeQ(tenders, 3500)).toBe(500);
    expect(paymentChangeQ(tenders, 5000)).toBe(0);
    expect(isPaymentCovered(tenders, 4000)).toBe(true);
    expect(isPaymentCovered(tenders, 5000)).toBe(false);
    expect(isPaymentCovered([], 0)).toBe(false);
  });

  it("shapes a tender line view", () => {
    expect(tenderLineView(tender("pix", 2599), METHODS)).toEqual({
      method: "pix",
      label: "PIX",
      icon: "lucide:qr-code",
      amountQ: 2599,
      amountDisplay: formatBRL(2599),
    });
  });

  it("sources cash quick-add presets from the contract, falling back when absent", () => {
    const contract = { cash_tender_delta_presets_q: [0, 1000, 5000] } as POSCheckoutContractProjection;
    expect(cashDeltaPresets(contract)).toEqual([0, 1000, 5000]);
    expect(cashDeltaPresets(null)).toEqual([1000, 5000, 10000]);
    expect(cashDeltaPresets({ cash_tender_delta_presets_q: [] } as unknown as POSCheckoutContractProjection)).toEqual([1000, 5000, 10000]);
  });

  it("filters payment collections by fulfillment type", () => {
    const collections: POSPaymentCollectionProjection[] = [
      { ref: "terminal", label: "No balcão", description: "", fulfillment_types: ["pickup", "delivery"], payment_method_refs: [] },
      { ref: "on_delivery", label: "Na entrega", description: "", fulfillment_types: ["delivery"], payment_method_refs: [] },
    ];
    expect(collectionsForFulfillment(collections, "pickup").map((c) => c.ref)).toEqual(["terminal"]);
    expect(collectionsForFulfillment(collections, "delivery").map((c) => c.ref)).toEqual(["terminal", "on_delivery"]);
  });
});

describe("presentation/payment — digital proof (PCI SAQ A)", () => {
  it("returns null for cash or empty results", () => {
    expect(paymentProofView(null)).toBeNull();
    expect(paymentProofView(undefined)).toBeNull();
    expect(paymentProofView({ method: "cash" } as POSPaymentResultProjection)).toBeNull();
  });

  it("shapes a PIX proof with a render-ready QR src and copy-paste", () => {
    const proof = paymentProofView({
      method: "pix",
      amount_q: 5000,
      amount_display: "R$ 50,00",
      status: "pending",
      message: "Aguarde confirmação.",
      qr_code: "iVBORw0KGgo=",
      copy_paste: "00020126BR.GOV.BCB.PIX",
    } as POSPaymentResultProjection);
    expect(proof).not.toBeNull();
    expect(proof!.isPix).toBe(true);
    expect(proof!.tone).toBe("info");
    expect(proof!.qrCodeSrc).toBe("data:image/png;base64,iVBORw0KGgo=");
    expect(proof!.copyPaste).toBe("00020126BR.GOV.BCB.PIX");
    expect(proof!.hasProof).toBe(true);
  });

  it("shapes a card proof with a checkout link and never invents proof", () => {
    const proof = paymentProofView({
      method: "card",
      amount_q: 9900,
      amount_display: "R$ 99,00",
      status: "error",
      checkout_url: "https://checkout.stripe.com/x",
    } as POSPaymentResultProjection);
    expect(proof!.isCard).toBe(true);
    expect(proof!.tone).toBe("danger");
    expect(proof!.checkoutUrl).toBe("https://checkout.stripe.com/x");
    expect(proof!.qrCodeSrc).toBe("");
    expect(proof!.hasProof).toBe(true);
  });

  it("passes through data/http QR URIs and wraps bare base64", () => {
    expect(qrCodeSrc("")).toBe("");
    expect(qrCodeSrc("data:image/png;base64,abc")).toBe("data:image/png;base64,abc");
    expect(qrCodeSrc("https://x/qr.png")).toBe("https://x/qr.png");
    expect(qrCodeSrc("abc123")).toBe("data:image/png;base64,abc123");
  });
});

describe("presentation/cash — blind drawer shaping", () => {
  it("labels movement kinds with a fallback", () => {
    expect(movementLabel("sangria")).toBe("Sangria");
    expect(movementLabel("suprimento")).toBe("Suprimento");
    expect(movementLabel("custom")).toBe("custom");
  });

  it("formats the opening timestamp, falling back gracefully", () => {
    expect(formatOpenedAt(null)).toBe("—");
    expect(formatOpenedAt("")).toBe("—");
    expect(formatOpenedAt("not-a-date")).toBe("not-a-date");
    expect(formatOpenedAt("2026-06-06T13:05:00")).toMatch(/06\/06/);
  });

  it("detects a terminal held by another operator's open shift", () => {
    const base = { has_open_shift: false, shift_id: null, terminal_ref: "t1", terminal_label: "T1", operator_username: "", opened_at: "" } as POSCashRuntimeProjection;
    expect(isTerminalOccupied({ ...base, status: "terminal_occupied" }, false)).toBe(true);
    expect(isTerminalOccupied({ ...base, blocking_operator_username: "ana" }, false)).toBe(true);
    expect(isTerminalOccupied({ ...base, blocking_operator_username: "ana" }, true)).toBe(false);
    expect(isTerminalOccupied(base, false)).toBe(false);
  });
});
