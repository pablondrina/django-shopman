import { describe, expect, it } from "vitest";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

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
  tabCodeMaxDigits,
} from "../app/utils/posTabLifecycle";

describe("POS sale intent", () => {
  it("serializes cart state into the canonical POS intent contract", () => {
    const payload = buildPosSaleIntent({
      tabCode: "00001007",
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
      tab_code: "00001007",
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
        href: "/api/v1/backstage/pos/tabs/{tab_code}/open/",
        method: "POST",
        payload_schema: {},
        idempotency: "none",
        confirmation: {},
      },
    ];

    expect(actionHref(actions, "missing", "/fallback/")).toBe("/fallback/");
    expect(concreteActionHref(actions, "open_tab", "/fallback/", { tab_code: "00001007" })).toBe(
      "/api/v1/backstage/pos/tabs/00001007/open/",
    );
  });

  it("only computes local display totals from projected line prices", () => {
    expect(cartTotalQ([
      { sku: "A", name: "A", price_q: 500, qty: 2, notes: "", is_d1: false },
      { sku: "B", name: "B", price_q: 300, qty: 1, notes: "", is_d1: false },
    ])).toBe(1300);
  });
});

describe("surface architecture guardrails", () => {
  it("drives POS tab association UX from the canonical tab lifecycle capability", () => {
    const capabilities = {
      tab_lifecycle: {
        requires_open_tab_for_cart: true,
        requires_tab_before_save: true,
        allows_direct_checkout_without_tab: true,
        tab_code_max_digits: 6,
        draft_association_target_states: ["empty"],
      },
    };

    expect(requiresOpenTabForCart(capabilities)).toBe(true);
    expect(requiresTabBeforeSave(capabilities)).toBe(true);
    expect(tabCodeMaxDigits(capabilities)).toBe(6);
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
