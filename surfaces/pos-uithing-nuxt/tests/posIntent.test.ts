import { describe, expect, it } from "vitest";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

import { buildAdminLoginUrl, isOperatorAccessError, statusCodeFromError } from "../app/utils/operatorAccess";
import {
  POS_SALE_INTENT_VERSION,
  actionHref,
  buildPosSaleIntent,
  cartTotalQ,
  concreteActionHref,
} from "../app/utils/posIntent";
import {
  draftAssociationTargetStates,
  requiresOpenTabForCart,
  requiresTabBeforeSave,
  tabRefMaxLength,
  tabRefPlaceholder,
} from "../app/utils/posTabLifecycle";
import {
  csrfTokenFromCookieHeader,
  mergeSetCookieIntoCookieHeader,
} from "../server/utils/djangoProxy";

describe("POS sale intent", () => {
  it("serializes cart state into the canonical POS intent contract", () => {
    const payload = buildPosSaleIntent({
      tabRef: "00001007",
      tabSessionKey: "session-1",
      customerName: "Ana",
      customerRef: "CUST-1",
      customerPhone: "(43) 99999-0000",
      customerTaxId: "123.456.789-01",
      customerEmail: "ana@example.com",
      customerMemoryAction: "",
      fulfillmentType: "delivery",
      deliveryAddress: "Rua A, 10 - Centro",
      deliveryAddressStructured: {
        formatted_address: "Rua A, 10 - Centro",
        route: "Rua A",
        street_number: "10",
        neighborhood: "Centro",
        city: "Londrina",
        state_code: "PR",
        postal_code: "86000-000",
        latitude: -23.3,
        longitude: -51.1,
        place_id: "ChIJ-pos",
        reference: "",
      },
      deliveryComplement: "Sala 2",
      deliveryInstructions: "Portaria",
      deliveryDate: "2026-05-16",
      deliveryTimeSlot: "14:00-14:30",
      deliveryFeeQ: 300,
      orderNotes: "Portaria",
      paymentMethod: "cash",
      paymentCollection: "on_delivery",
      paymentTenders: [],
      tenderedAmountQ: null,
      issueFiscalDocument: false,
      receiptMode: "email",
      receiptEmail: "ana@example.com",
      manualDiscount: null,
      managerApproval: null,
      clientRequestId: "pos-uithing:test-1",
      items: [
        { sku: "PAO", name: "Pao", price_q: 1200, qty: 2, notes: "", is_d1: false },
      ],
    });

    expect(payload).toMatchObject({
      intent_version: POS_SALE_INTENT_VERSION,
      tab_ref: "00001007",
      tab_session_key: "session-1",
      fulfillment_type: "delivery",
      customer_ref: "CUST-1",
      delivery_address: "Rua A, 10 - Centro",
      delivery_address_structured: {
        formatted_address: "Rua A, 10 - Centro",
        route: "Rua A",
        street_number: "10",
        neighborhood: "Centro",
        city: "Londrina",
        state_code: "PR",
        postal_code: "86000-000",
        latitude: -23.3,
        longitude: -51.1,
        place_id: "ChIJ-pos",
        complement: "Sala 2",
        delivery_instructions: "Portaria",
        reference: "",
      },
      delivery_date: "2026-05-16",
      delivery_time_slot: "14:00-14:30",
      delivery_fee_q: 300,
      order_notes: "Portaria",
      payment_method: "cash",
      payment_collection: "on_delivery",
      customer_phone: "43999990000",
      customer_tax_id: "12345678901",
      receipt_mode: "email",
      receipt_email: "ana@example.com",
    });
    expect(payload.items).toEqual([
      { sku: "PAO", name: "Pao", qty: 2, unit_price_q: 1200, notes: "" },
    ]);
    expect(payload.items[0]).not.toHaveProperty("price_q");
  });

  it("uses projection actions instead of hardcoding mutation paths in state builders", () => {
    const actions = [
      {
        ref: "open_tab",
        kind: "mutation",
        label: "Abrir",
        priority: "secondary",
        enabled: true,
        reason: "",
        href: "/api/v1/backstage/pos/tabs/{tab_ref}/open/",
        method: "POST",
        payload_schema: {},
        idempotency: "none",
        confirmation: {},
      },
    ];

    expect(actionHref(actions, "missing", "/fallback/")).toBe("/fallback/");
    expect(concreteActionHref(actions, "open_tab", "/fallback/", { tab_ref: "00001007" })).toBe(
      "/api/v1/backstage/pos/tabs/00001007/open/",
    );
  });

  it("only computes local display totals from projected line prices", () => {
    expect(cartTotalQ([
      { sku: "A", name: "A", price_q: 500, qty: 2, notes: "", is_d1: false },
      { sku: "B", name: "B", price_q: 300, qty: 1, notes: "", is_d1: false },
    ])).toBe(1300);
  });

  it("does not replay saved tender lines unless split payment is explicit", () => {
    const staleTender = { method: "cash", amount_q: 1000, collection: "terminal" as const };
    const simple = buildPosSaleIntent(baseIntentState({
      paymentMethod: "cash",
      paymentTenders: [staleTender],
      tenderedAmountQ: null,
    }));

    expect(simple).not.toHaveProperty("payment_tenders");

    const mixed = buildPosSaleIntent(baseIntentState({
      paymentMethod: "mixed",
      paymentTenders: [staleTender],
      tenderedAmountQ: null,
    }));

    expect(mixed.payment_tenders).toEqual([staleTender]);
  });

  it("sends cash received amount only for terminal cash payments", () => {
    expect(buildPosSaleIntent(baseIntentState({
      paymentMethod: "pix",
      paymentCollection: "terminal",
      tenderedAmountQ: 2000,
    }))).not.toHaveProperty("tendered_amount_q");

    expect(buildPosSaleIntent(baseIntentState({
      paymentMethod: "cash",
      paymentCollection: "on_delivery",
      tenderedAmountQ: 2000,
    }))).not.toHaveProperty("tendered_amount_q");

    expect(buildPosSaleIntent(baseIntentState({
      paymentMethod: "cash",
      paymentCollection: "terminal",
      tenderedAmountQ: 2000,
    }))).toMatchObject({ tendered_amount_q: 2000 });
  });

  it("serializes manual discount as a canonical intent for backend review", () => {
    expect(buildPosSaleIntent(baseIntentState({
      manualDiscount: { type: "percent", value: "10", reason: "fidelidade" },
      managerApproval: { username: "gerente", password: "secret" },
    }))).toMatchObject({
      manual_discount: { type: "percent", value: "10", reason: "fidelidade" },
      manager_approval: { username: "gerente", password: "secret" },
    });
  });
});

describe("surface architecture guardrails", () => {
  it("drives POS tab association UX from the canonical tab lifecycle capability", () => {
    const capabilities = {
      tab_lifecycle: {
        requires_open_tab_for_cart: true,
        requires_tab_before_save: true,
        allows_direct_checkout_without_tab: true,
        tab_ref_max_length: 64,
        tab_ref_placeholder: "Mesa, nome ou referência",
        draft_association_target_states: ["empty"],
      },
    };

    expect(requiresOpenTabForCart(capabilities)).toBe(true);
    expect(requiresTabBeforeSave(capabilities)).toBe(true);
    expect(tabRefMaxLength(capabilities)).toBe(64);
    expect(tabRefPlaceholder(capabilities)).toBe("Mesa, nome ou referência");
    expect(draftAssociationTargetStates(capabilities)).toEqual(["empty"]);
    expect(requiresOpenTabForCart({ tab_lifecycle: { requires_open_tab_for_cart: false } })).toBe(false);
  });

  it("does not reach around POS projections to catalog, stock, or checkout contracts", () => {
    const sources = readSources(join(process.cwd(), "app"))
      .filter((entry) => !entry.path.includes(`${join("components", "Ui")}${"/"}`));
    const joined = sources.map((entry) => entry.content).join("\n");

    expect(joined).not.toContain("/api/v1/catalog");
    expect(joined).not.toContain("/api/v1/storefront");
    expect(joined).not.toContain("base_price_q");
    expect(joined).not.toContain("available_qty");
    expect(joined).not.toContain("Order.Status");
  });
});

describe("operator access", () => {
  it("recognizes Django/DRF auth failures as operator access states", () => {
    expect(statusCodeFromError({ statusCode: 403 })).toBe(403);
    expect(statusCodeFromError({ response: { status: 401 } })).toBe(401);
    expect(isOperatorAccessError({ statusCode: 403 })).toBe(true);
    expect(isOperatorAccessError({ response: { status: 401 } })).toBe(true);
    expect(isOperatorAccessError({ statusCode: 500 })).toBe(false);
  });

  it("builds an admin login URL without taking ownership of credentials", () => {
    expect(buildAdminLoginUrl({
      djangoPublicBaseUrl: "https://shop.example.com/",
      nextPath: "/pos/",
    })).toBe("https://shop.example.com/admin/login/?next=%2Fpos%2F");

    expect(buildAdminLoginUrl({
      djangoPublicBaseUrl: "http://127.0.0.1:8000",
      nextPath: "pos/",
    })).toBe("http://127.0.0.1:8000/admin/login/?next=%2Fpos%2F");

    expect(buildAdminLoginUrl({
      djangoPublicBaseUrl: "http://127.0.0.1:8000",
      nextPath: "/admin/",
    })).toBe("http://127.0.0.1:8000/admin/login/?next=%2Fadmin%2F");
  });

  it("preserves Django session cookies while refreshing CSRF state", () => {
    const cookie = "sessionid=session-123; csrftoken=old-token";
    expect(csrfTokenFromCookieHeader(cookie)).toBe("old-token");
    expect(mergeSetCookieIntoCookieHeader(cookie, "csrftoken=new-token; Path=/; SameSite=Lax")).toBe(
      "sessionid=session-123; csrftoken=new-token",
    );
    expect(mergeSetCookieIntoCookieHeader(cookie, "other=value=with-equals; Path=/")).toBe(
      "sessionid=session-123; csrftoken=old-token; other=value=with-equals",
    );
  });
});

function readSources(dir: string): Array<{ path: string; content: string }> {
  const entries: Array<{ path: string; content: string }> = [];
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    const stat = statSync(path);
    if (stat.isDirectory()) {
      entries.push(...readSources(path));
      continue;
    }
    if (/\.(ts|vue)$/.test(path)) {
      entries.push({ path, content: readFileSync(path, "utf8") });
    }
  }
  return entries;
}

function baseIntentState(overrides: Record<string, unknown> = {}) {
  return {
    tabRef: "00001007",
    tabSessionKey: "session-1",
    customerName: "",
    customerRef: "",
    customerPhone: "",
    customerTaxId: "",
    customerEmail: "",
    customerMemoryAction: "",
    fulfillmentType: "pickup",
    deliveryAddress: "",
    deliveryAddressStructured: {},
    deliveryComplement: "",
    deliveryInstructions: "",
    deliveryDate: "",
    deliveryTimeSlot: "",
    deliveryFeeQ: 0,
    orderNotes: "",
    paymentMethod: "cash",
    paymentCollection: "terminal",
    paymentTenders: [],
    tenderedAmountQ: null,
    issueFiscalDocument: false,
    receiptMode: "none",
    receiptEmail: "",
    manualDiscount: null,
    managerApproval: null,
    clientRequestId: "pos-uithing:test-base",
    items: [
      { sku: "PAO", name: "Pao", price_q: 1200, qty: 1, notes: "", is_d1: false },
    ],
    ...overrides,
  };
}
