import { describe, expect, it } from "vitest";

import {
  cardAffordances,
  elapsedLabel,
  lucideIcon,
  matchesQuery,
  splitRef,
  statusTone,
  timerTone,
  toneBadge,
  zonesView,
} from "../app/presentation/board";
import type { OrderCardProjection, TwoZoneQueueProjection } from "../app/types/orders";

const card = (over: Partial<OrderCardProjection> = {}): OrderCardProjection => ({
  ref: "WEB-20260625-0007",
  status: "confirmed",
  status_label: "Confirmado",
  status_color: "",
  channel_ref: "web",
  channel_icon: "language",
  customer_name: "Ana",
  created_at_display: "08:00",
  created_at_iso: "",
  server_now_iso: "",
  elapsed_seconds: 30,
  timer_class: "timer-ok",
  items_summary: "2× Pão · 1× Café",
  items_count: 3,
  total_display: "R$ 15,00",
  fulfillment_icon: "storefront",
  fulfillment_label: "Retirada",
  can_confirm: false,
  can_advance: true,
  next_status: "preparing",
  next_action_label: "Iniciar preparo",
  payment_method: "cash",
  payment_method_label: "Dinheiro",
  payment_status: "pending",
  payment_pending: true,
  can_settle_delivery_cash: false,
  fiscal_status_label: "",
  fiscal_status: "",
  has_notes: false,
  awaiting_work_orders: [],
  ...over,
});

describe("statusTone", () => {
  it("maps lifecycle statuses to functional tones", () => {
    expect(statusTone("new")).toBe("info");
    expect(statusTone("preparing")).toBe("warning");
    expect(statusTone("ready")).toBe("success");
    expect(statusTone("cancelled")).toBe("danger");
    expect(statusTone("whatever")).toBe("neutral");
  });
  it("toneBadge returns a class string per tone", () => {
    expect(toneBadge("danger")).toContain("red");
    expect(toneBadge("neutral")).toContain("muted");
  });
});

describe("timerTone", () => {
  it("maps timer_class to urgency", () => {
    expect(timerTone("timer-ok")).toBe("ok");
    expect(timerTone("timer-warning")).toBe("warning");
    expect(timerTone("timer-urgent")).toBe("late");
    expect(timerTone("timer-muted")).toBe("muted");
  });
});

describe("lucideIcon", () => {
  it("translates Material ligatures to lucide names", () => {
    expect(lucideIcon("language")).toBe("globe");
    expect(lucideIcon("local_shipping")).toBe("bike");
  });
  it("passes through unknown names and falls back to circle", () => {
    expect(lucideIcon("rocket")).toBe("rocket");
    expect(lucideIcon("")).toBe("circle");
  });
});

describe("splitRef", () => {
  it("splits a ref into prefix + short code", () => {
    expect(splitRef("WEB-20260625-0007")).toEqual({ prefix: "WEB-20260625-", code: "0007" });
    expect(splitRef("ABC")).toEqual({ prefix: "", code: "ABC" });
  });
});

describe("elapsedLabel", () => {
  it("formats seconds, minutes and hours compactly", () => {
    expect(elapsedLabel(45)).toBe("45s");
    expect(elapsedLabel(90)).toBe("1m");
    expect(elapsedLabel(3 * 60)).toBe("3m");
    expect(elapsedLabel(65 * 60)).toBe("1h 5m");
    expect(elapsedLabel(120 * 60)).toBe("2h");
  });
});

describe("zonesView", () => {
  const queue = (): TwoZoneQueueProjection => ({
    entrada: [card({ ref: "A", status: "new" })],
    preparing_count: 1,
    preparo: [card({ ref: "B" }), card({ ref: "C" })],
    saida_retirada: [card({ ref: "D", status: "ready" })],
    saida_delivery: [card({ ref: "E", status: "ready" })],
    saida_delivery_transit: [card({ ref: "F", status: "dispatched" })],
    saida_delivery_count: 2,
    saida_count: 3,
    total_count: 6,
  });

  it("groups the two-zone queue into three columns with merged Saída", () => {
    const zones = zonesView(queue());
    expect(zones.map((z) => z.key)).toEqual(["entrada", "preparo", "saida"]);
    expect(zones[0]!.count).toBe(1);
    expect(zones[1]!.count).toBe(2);
    expect(zones[2]!.count).toBe(3); // retirada + delivery + transit
    expect(zones[2]!.cards.map((c) => c.ref)).toEqual(["D", "E", "F"]);
  });
});

describe("cardAffordances", () => {
  it("offers confirm + reject for a new order", () => {
    const refs = cardAffordances(card({ can_confirm: true, can_advance: false })).map((a) => a.ref);
    expect(refs).toContain("confirm");
    expect(refs).toContain("reject");
    expect(refs).not.toContain("advance");
  });
  it("offers advance for a confirmed order", () => {
    const refs = cardAffordances(card({ can_confirm: false, can_advance: true })).map((a) => a.ref);
    expect(refs).toEqual(["advance"]);
  });
  it("adds settle_cash when delivery cash is collectable", () => {
    const refs = cardAffordances(card({ can_settle_delivery_cash: true })).map((a) => a.ref);
    expect(refs).toContain("settle_cash");
  });
});

describe("matchesQuery", () => {
  it("matches on ref, customer and items; empty query matches all", () => {
    const c = card();
    expect(matchesQuery(c, "")).toBe(true);
    expect(matchesQuery(c, "ana")).toBe(true);
    expect(matchesQuery(c, "0007")).toBe(true);
    expect(matchesQuery(c, "café")).toBe(true);
    expect(matchesQuery(c, "pizza")).toBe(false);
  });
});
