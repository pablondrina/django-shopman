import { describe, expect, it } from "vitest";

import {
  bulkableRefs,
  cardAffordances,
  channelLabel,
  channelOptions,
  elapsedLabel,
  flattenZones,
  lucideIcon,
  fulfillmentCounts,
  matchesChannel,
  matchesFulfillment,
  matchesQuery,
  nextSort,
  resolveShortcut,
  rowsToCsv,
  sortCards,
  splitRef,
  statusTone,
  timerTone,
  toneBadge,
  triageCards,
  zonesView,
  confirmationRemainingLabel,
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
  fulfillment_type: "pickup",
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
  assigned_operator: "",
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

describe("channelLabel", () => {
  it("maps known channels and capitalises unknowns", () => {
    expect(channelLabel("web")).toBe("Loja online");
    expect(channelLabel("ifood")).toBe("iFood");
    expect(channelLabel("pdv")).toBe("PDV");
    expect(channelLabel("kiosk")).toBe("Kiosk");
    expect(channelLabel("")).toBe("—");
  });
});

describe("channelOptions", () => {
  it("returns distinct channels with counts, sorted by label", () => {
    const opts = channelOptions([
      card({ channel_ref: "web" }),
      card({ channel_ref: "web" }),
      card({ channel_ref: "ifood" }),
    ]);
    expect(opts).toEqual([
      { ref: "ifood", label: "iFood", count: 1 },
      { ref: "web", label: "Loja online", count: 2 },
    ]);
  });
});

describe("matchesChannel", () => {
  it("treats empty/all as match-all, else exact", () => {
    const c = card({ channel_ref: "whatsapp" });
    expect(matchesChannel(c, "")).toBe(true);
    expect(matchesChannel(c, "all")).toBe(true);
    expect(matchesChannel(c, "whatsapp")).toBe(true);
    expect(matchesChannel(c, "web")).toBe(false);
  });
});

describe("sortCards", () => {
  const a = card({ ref: "A", elapsed_seconds: 10, created_at_iso: "2026-06-26T08:00:00Z" });
  const b = card({ ref: "B", elapsed_seconds: 300, created_at_iso: "2026-06-26T07:00:00Z" });
  const c = card({ ref: "C", elapsed_seconds: 60, created_at_iso: "2026-06-26T09:00:00Z" });

  it("arrival keeps input order and does not mutate", () => {
    const input = [a, b, c];
    expect(sortCards(input, "arrival").map((x) => x.ref)).toEqual(["A", "B", "C"]);
    expect(input.map((x) => x.ref)).toEqual(["A", "B", "C"]);
  });
  it("urgency puts the longest-waiting first", () => {
    expect(sortCards([a, b, c], "urgency").map((x) => x.ref)).toEqual(["B", "C", "A"]);
  });
  it("recent puts the newest arrival first", () => {
    expect(sortCards([a, b, c], "recent").map((x) => x.ref)).toEqual(["C", "A", "B"]);
  });
});

describe("triageCards", () => {
  it("composes channel filter + query + sort", () => {
    const rows = [
      card({ ref: "A", channel_ref: "web", customer_name: "Ana", elapsed_seconds: 10 }),
      card({ ref: "B", channel_ref: "ifood", customer_name: "Ana", elapsed_seconds: 99 }),
      card({ ref: "C", channel_ref: "web", customer_name: "Bia", elapsed_seconds: 50 }),
    ];
    const out = triageCards(rows, { query: "ana", channel: "web", sort: "urgency" });
    expect(out.map((x) => x.ref)).toEqual(["A"]);
  });
});

describe("resolveShortcut", () => {
  it("maps keys to board shortcuts (case-insensitive for letters)", () => {
    expect(resolveShortcut("/")).toBe("focus-search");
    expect(resolveShortcut("r")).toBe("refresh");
    expect(resolveShortcut("R")).toBe("refresh");
    expect(resolveShortcut("v")).toBe("toggle-view");
    expect(resolveShortcut("s")).toBe("cycle-sort");
    expect(resolveShortcut("Escape")).toBe("clear-filters");
    expect(resolveShortcut("x")).toBeNull();
  });
});

describe("nextSort", () => {
  it("cycles arrival → urgency → recent → arrival", () => {
    expect(nextSort("arrival")).toBe("urgency");
    expect(nextSort("urgency")).toBe("recent");
    expect(nextSort("recent")).toBe("arrival");
  });
});

describe("bulkableRefs", () => {
  const rows = [
    card({ ref: "A", can_confirm: true, can_advance: false }),
    card({ ref: "B", can_confirm: false, can_advance: true }),
    card({ ref: "C", can_confirm: true, can_advance: false }),
  ];
  it("returns selected refs eligible for confirm", () => {
    expect(bulkableRefs(rows, new Set(["A", "B"]), "confirm")).toEqual(["A"]);
  });
  it("returns selected refs eligible for advance", () => {
    expect(bulkableRefs(rows, new Set(["A", "B", "C"]), "advance")).toEqual(["B"]);
  });
  it("ignores unselected cards", () => {
    expect(bulkableRefs(rows, new Set(["C"]), "confirm")).toEqual(["C"]);
    expect(bulkableRefs(rows, new Set(), "confirm")).toEqual([]);
  });
});

describe("rowsToCsv", () => {
  it("writes a header + one row per card, escaping quotes", () => {
    const rows = [
      { card: card({ ref: "A", customer_name: 'Ana "Bela"', assigned_operator: "Léo" }), zoneKey: "entrada" as const, zoneTitle: "Entrada" },
    ];
    const csv = rowsToCsv(rows);
    const [header, line] = csv.split("\n");
    expect(header).toContain("Codigo");
    expect(header).toContain("Atendente");
    expect(line).toContain('"A"');
    expect(line).toContain('"Ana ""Bela"""'); // doubled quotes
    expect(line).toContain('"Léo"');
  });
  it("is just a header when there are no rows", () => {
    expect(rowsToCsv([]).split("\n")).toHaveLength(1);
  });
});

describe("flattenZones", () => {
  it("flattens zones preserving order and tagging the zone", () => {
    const zones = zonesView({
      entrada: [card({ ref: "A", status: "new" })],
      preparing_count: 1,
      preparo: [card({ ref: "B" })],
      saida_retirada: [card({ ref: "C", status: "ready" })],
      saida_delivery: [],
      saida_delivery_transit: [],
      saida_delivery_count: 0,
      saida_count: 1,
      total_count: 3,
    });
    const flat = flattenZones(zones);
    expect(flat.map((r) => r.card.ref)).toEqual(["A", "B", "C"]);
    expect(flat.map((r) => r.zoneKey)).toEqual(["entrada", "preparo", "saida"]);
  });
});

describe("fulfillment axis", () => {
  it("matchesFulfillment: 'all' passa tudo; senão bate o tipo", () => {
    const del = card({ fulfillment_type: "delivery" });
    const pick = card({ fulfillment_type: "pickup" });
    expect(matchesFulfillment(del, "all")).toBe(true);
    expect(matchesFulfillment(del, "delivery")).toBe(true);
    expect(matchesFulfillment(del, "pickup")).toBe(false);
    expect(matchesFulfillment(pick, "pickup")).toBe(true);
  });
  it("fulfillmentCounts conta entrega vs retirada", () => {
    const cards = [
      card({ fulfillment_type: "delivery" }),
      card({ fulfillment_type: "delivery" }),
      card({ fulfillment_type: "pickup" }),
    ];
    expect(fulfillmentCounts(cards)).toEqual({ delivery: 2, pickup: 1 });
  });
});

describe("elapsedLabel — dias", () => {
  it("cap em dias em vez de horas gigantes", () => {
    expect(elapsedLabel(3600 * 25)).toBe("1d 1h");
    expect(elapsedLabel(3600 * 24 * 4 + 3600 * 23)).toBe("4d 23h");
    expect(elapsedLabel(3600 * 48)).toBe("2d");
  });
});

describe("confirmationRemainingLabel", () => {
  it("empty when no deadline", () => {
    expect(confirmationRemainingLabel("", Date.now())).toBe("");
    expect(confirmationRemainingLabel("not-a-date", Date.now())).toBe("");
  });
  it("formats M:SS remaining", () => {
    const now = Date.parse("2026-07-04T12:00:00Z");
    expect(confirmationRemainingLabel("2026-07-04T12:02:34Z", now)).toBe("2:34");
    expect(confirmationRemainingLabel("2026-07-04T12:00:09Z", now)).toBe("0:09");
  });
  it("clamps to 0:00 once past", () => {
    const now = Date.parse("2026-07-04T12:05:00Z");
    expect(confirmationRemainingLabel("2026-07-04T12:00:00Z", now)).toBe("0:00");
  });
});
