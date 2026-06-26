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
  cashNotesQ,
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
import {
  availableMoveModes,
  buildMovePayload,
  canSubmitMove,
  defaultMoveTarget,
  freezesPriceOnMove,
  moveLineId,
  moveLineView,
  modeNeedsSelection,
  moveTargetOptions,
  selectedLineIds,
} from "../app/presentation/moveLines";
import {
  allLinesFired,
  fireBarView,
  firedCount,
  kitchenLineState,
  unfiredCount,
} from "../app/presentation/kitchen";
import { pruneSelection, selectedItems, selectionView, toggleSelected } from "../app/presentation/selection";
import { receiptLineTotalQ, receiptLines, receiptPayments, type PosReceiptSnapshot } from "../app/presentation/receipt";
import type { ActionAffordance } from "../app/presentation/actions";
import { formatBRL } from "../app/utils/posIntent";
import type {
  POSCartItem,
  POSCashRuntimeProjection,
  POSCheckoutContractProjection,
  POSPaymentCollectionProjection,
  POSPaymentMethodProjection,
  POSPaymentResultProjection,
  POSPaymentTenderDraft,
} from "../app/types/pos";

function cartItem(overrides: Partial<POSCartItem> & { sku: string }): POSCartItem {
  return {
    name: overrides.sku,
    price_q: 0,
    qty: 1,
    notes: "",
    is_d1: false,
    ...overrides,
  };
}

function affordance(overrides: Partial<ActionAffordance> = {}): ActionAffordance {
  return {
    ref: "fire_tab",
    present: true,
    label: "Enviar itens",
    priority: "normal",
    enabled: true,
    reason: "",
    href: "",
    method: "POST",
    idempotency: "none",
    confirmation: {},
    ...overrides,
  };
}

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
      pendingKitchen: true,
      identity: "Ana",
      summary: "2 itens · R$ 24,00",
      selected: true,
    });

    const free = tabCardView(tabs[0]!);
    expect(free).toMatchObject({ isFree: true, pendingKitchen: false, summary: "Comanda livre", identity: "—", selected: false });

    const fired = tabCardView(tabs[2]!);
    expect(fired).toMatchObject({ isUnpaid: true, pendingKitchen: false, summary: "1 item · R$ 8,00" });
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

  it("offers the main BR cash notes (R$2..R$100) for accumulation", () => {
    expect(cashNotesQ()).toEqual([200, 500, 1000, 2000, 5000, 10000]);
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

describe("presentation/moveLines — move modes, gate & payload", () => {
  it("offers modes driven by the tab_manipulation capability", () => {
    expect(availableMoveModes({ allows_split: true, allows_transfer: true, allows_merge: true }).map((m) => m.ref))
      .toEqual(["split", "transfer", "merge"]);
    expect(availableMoveModes({ allows_split: true, allows_transfer: false, allows_merge: true }).map((m) => m.ref))
      .toEqual(["split", "merge"]);
    // Absent capability is defensive: offer all three so the dialog still works.
    expect(availableMoveModes(null).map((m) => m.ref)).toEqual(["split", "transfer", "merge"]);
  });

  it("flags price-freezing from the capability, defaulting to true", () => {
    expect(freezesPriceOnMove({ freezes_price_on_move: true })).toBe(true);
    expect(freezesPriceOnMove({ freezes_price_on_move: false })).toBe(false);
    expect(freezesPriceOnMove({})).toBe(true);
    expect(freezesPriceOnMove(null)).toBe(true);
  });

  it("addresses a line by server line_id, falling back to sku", () => {
    expect(moveLineId(cartItem({ sku: "CR", line_id: "L1" }))).toBe("L1");
    expect(moveLineId(cartItem({ sku: "CR" }))).toBe("CR");
  });

  it("needs line selection for split/transfer but not merge", () => {
    expect(modeNeedsSelection("split")).toBe(true);
    expect(modeNeedsSelection("transfer")).toBe(true);
    expect(modeNeedsSelection("merge")).toBe(false);
  });

  it("shapes a line view and selects ids in tab order", () => {
    const items = [
      cartItem({ sku: "CR", name: "Croissant", price_q: 800, qty: 2, line_id: "L1" }),
      cartItem({ sku: "PC", name: "Pão", price_q: 500, qty: 1, line_id: "L2" }),
    ];
    expect(moveLineView(items[0]!)).toEqual({ id: "L1", label: "2x Croissant", amountDisplay: formatBRL(1600) });
    expect(selectedLineIds(items, new Set(["L2"]))).toEqual(["L2"]);
    expect(selectedLineIds(items, new Set(["L2", "L1"]))).toEqual(["L1", "L2"]);
  });

  it("gates submit per mode", () => {
    const base = { selectedIds: ["L1"], splitRef: "1007/2", targetSessionKey: "s1", itemCount: 2, busy: false };
    expect(canSubmitMove({ ...base, mode: "split" })).toBe(true);
    expect(canSubmitMove({ ...base, mode: "split", splitRef: " " })).toBe(false);
    expect(canSubmitMove({ ...base, mode: "split", selectedIds: [] })).toBe(false);
    expect(canSubmitMove({ ...base, mode: "transfer" })).toBe(true);
    expect(canSubmitMove({ ...base, mode: "transfer", targetSessionKey: "" })).toBe(false);
    expect(canSubmitMove({ ...base, mode: "merge", selectedIds: [] })).toBe(true);
    expect(canSubmitMove({ ...base, mode: "merge", itemCount: 0 })).toBe(false);
    expect(canSubmitMove({ ...base, mode: "split", busy: true })).toBe(false);
  });

  it("builds the move payload per mode, or null when invalid", () => {
    const items = [cartItem({ sku: "CR", line_id: "L1" }), cartItem({ sku: "PC", line_id: "L2" })];
    expect(buildMovePayload({ mode: "split", items, selectedIds: ["L1"], splitRef: " 1007/2 ", targetSessionKey: "" }))
      .toEqual({ mode: "split", lineIds: ["L1"], toTabRef: "1007/2" });
    expect(buildMovePayload({ mode: "transfer", items, selectedIds: ["L1"], splitRef: "", targetSessionKey: "s1" }))
      .toEqual({ mode: "transfer", lineIds: ["L1"], toSessionKey: "s1" });
    expect(buildMovePayload({ mode: "merge", items, selectedIds: [], splitRef: "", targetSessionKey: "s1" }))
      .toEqual({ mode: "merge", lineIds: ["L1", "L2"], toSessionKey: "s1", closeSource: true });
    expect(buildMovePayload({ mode: "split", items, selectedIds: [], splitRef: "x", targetSessionKey: "" })).toBeNull();
    expect(buildMovePayload({ mode: "merge", items: [], selectedIds: [], splitRef: "", targetSessionKey: "s1" })).toBeNull();
  });

  it("lists destination tabs with a session, labelling by customer when present", () => {
    const tabs = [
      tab({ ref: "1007", display_ref: "1007", session_key: "s1", customer_name: "Maria" }),
      tab({ ref: "1011", display_ref: "1011", session_key: "s2" }),
      tab({ ref: "1099", display_ref: "1099", session_key: "" }),
    ];
    expect(moveTargetOptions(tabs)).toEqual([
      { sessionKey: "s1", label: "#1007 · Maria" },
      { sessionKey: "s2", label: "#1011" },
    ]);
    expect(defaultMoveTarget(tabs)).toBe("s1");
    expect(defaultMoveTarget([])).toBe("");
  });
});

describe("presentation/kitchen — fire-to-kitchen shaping", () => {
  it("counts fired vs unfired lines", () => {
    const items = [cartItem({ sku: "A", fired: true }), cartItem({ sku: "B" }), cartItem({ sku: "C" })];
    expect(firedCount(items)).toBe(1);
    expect(unfiredCount(items)).toBe(2);
    expect(allLinesFired(items)).toBe(false);
    expect(allLinesFired([cartItem({ sku: "A", fired: true })])).toBe(true);
    expect(allLinesFired([])).toBe(false);
  });

  it("derives per-line kitchen state", () => {
    expect(kitchenLineState(cartItem({ sku: "A" }), { canUnfire: true })).toBe("unfired");
    expect(kitchenLineState(cartItem({ sku: "A", fired: true, line_id: "L1" }), { canUnfire: true })).toBe("fired_cancellable");
    // Fired but no unfire affordance, or no line_id to target → non-interactive.
    expect(kitchenLineState(cartItem({ sku: "A", fired: true, line_id: "L1" }), { canUnfire: false })).toBe("fired");
    expect(kitchenLineState(cartItem({ sku: "A", fired: true }), { canUnfire: true })).toBe("fired");
  });

  it("shapes the fire bar: Action label + delta, all-fired state, disabled logic", () => {
    const items = [cartItem({ sku: "A", fired: true }), cartItem({ sku: "B" })];
    const bar = fireBarView({ items, affordance: affordance(), hasOpenTab: true, busy: false });
    expect(bar.visible).toBe(true);
    expect(bar.label).toBe("Enviar itens (1)");
    expect(bar.unfired).toBe(1);
    expect(bar.disabled).toBe(false);

    const allFired = fireBarView({
      items: [cartItem({ sku: "A", fired: true })],
      affordance: affordance(),
      hasOpenTab: true,
      busy: false,
    });
    expect(allFired.label).toBe("Tudo na cozinha");
    expect(allFired.allFired).toBe(true);
    expect(allFired.disabled).toBe(true); // nothing left to fire

    expect(fireBarView({ items, affordance: affordance({ present: false }), hasOpenTab: true, busy: false }).visible).toBe(false);
    expect(fireBarView({ items, affordance: affordance(), hasOpenTab: false, busy: false }).visible).toBe(false);
    expect(fireBarView({ items: [], affordance: affordance(), hasOpenTab: true, busy: false }).visible).toBe(false);
    expect(fireBarView({ items, affordance: affordance(), hasOpenTab: true, busy: true }).disabled).toBe(true);
    expect(fireBarView({ items, affordance: affordance({ enabled: false }), hasOpenTab: true, busy: false }).disabled).toBe(true);
  });
});

describe("presentation/selection — multi-select batch shaping", () => {
  const items = [
    cartItem({ sku: "A", line_id: "L1" }),
    cartItem({ sku: "B", line_id: "L2", fired: true }),
    cartItem({ sku: "C" }), // no line_id yet (unsaved)
  ];

  it("toggles a sku immutably", () => {
    const a = toggleSelected(new Set<string>(), "A");
    expect([...a]).toEqual(["A"]);
    const b = toggleSelected(a, "B");
    expect([...b].sort()).toEqual(["A", "B"]);
    expect([...toggleSelected(b, "A")].sort()).toEqual(["B"]);
    // original set is untouched (new Set each time)
    expect([...a]).toEqual(["A"]);
  });

  it("shapes the batch toolbar: counts, firable vs unfirable line_ids", () => {
    const view = selectionView(items, new Set(["A", "B", "C"]));
    expect(view.count).toBe(3);
    expect(view.skus.sort()).toEqual(["A", "B", "C"]);
    // A is unfired with a line_id → firable; C has no line_id → excluded.
    expect(view.firableLineIds).toEqual(["L1"]);
    expect(view.canFire).toBe(true);
    // B is fired with a line_id → unfirable.
    expect(view.unfirableLineIds).toEqual(["L2"]);
    expect(view.canUnfire).toBe(true);
  });

  it("empty selection has no batch affordances", () => {
    const view = selectionView(items, new Set());
    expect(view.count).toBe(0);
    expect(view.canFire).toBe(false);
    expect(view.canUnfire).toBe(false);
  });

  it("prunes selected skus no longer in the cart", () => {
    const pruned = pruneSelection(new Set(["A", "Z"]), items);
    expect([...pruned]).toEqual(["A"]);
  });

  it("selectedItems returns the cart items whose sku is selected", () => {
    expect(selectedItems(items, new Set(["A", "C"])).map((i) => i.sku)).toEqual(["A", "C"]);
    expect(selectedItems(items, new Set())).toEqual([]);
    expect(selectedItems(items, new Set(["Z"]))).toEqual([]);
  });
});

describe("presentation/receipt — print shaping (D3)", () => {
  const snap: PosReceiptSnapshot = {
    orderRef: "PED-1",
    tabDisplay: "1007",
    customerName: "João",
    items: [
      { name: "Croissant", qty: 2, price_q: 1300, discountPct: 0 },
      { name: "Café", qty: 1, price_q: 1000, discountPct: 10 },
    ],
    totalDisplay: "R$ 35,00",
    payments: [{ method: "cash", amount_q: 3500 }],
    fulfillmentLabel: "Retirada",
    printedAtMs: 0,
  };

  it("applies per-line discount to the net line total", () => {
    expect(receiptLineTotalQ(snap.items[0]!)).toBe(2600); // no discount
    expect(receiptLineTotalQ(snap.items[1]!)).toBe(900); // 10% off 1000
  });

  it("shapes receipt lines with unit and net total displays", () => {
    const lines = receiptLines(snap);
    expect(lines[0]).toMatchObject({ name: "Croissant", qty: 2, totalDisplay: formatBRL(2600), discountPct: 0 });
    expect(lines[1]).toMatchObject({ name: "Café", totalDisplay: formatBRL(900), discountPct: 10 });
  });

  it("labels payments from the method projection", () => {
    const methods = [{ ref: "cash", label: "Dinheiro", icon: "", requires_change: true }] as any;
    expect(receiptPayments(snap, methods)).toEqual([{ label: "Dinheiro", amountDisplay: formatBRL(3500) }]);
  });
});
