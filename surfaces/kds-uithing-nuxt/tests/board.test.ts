import { describe, expect, it } from "vitest";

import {
  boardView,
  elapsedLabel,
  isExpeditionCard,
  ticketTone,
  toneAccent,
} from "../app/presentation/board";
import type { KDSBoardProjection, KDSExpeditionCardProjection, KDSTicketProjection } from "../app/types/kds";

const ticket = (over: Partial<KDSTicketProjection> = {}): KDSTicketProjection => ({
  pk: 1,
  order_ref: "PDV-1",
  channel_icon: "store",
  customer_name: "Ana",
  fulfillment_icon: "bag",
  created_at_display: "08:00",
  elapsed_seconds: 30,
  target_seconds: 600,
  timer_class: "timer-ok",
  items: [{ sku: "x", name: "Pão", qty: 2, notes: "", checked: false, stock_warning: "" }],
  status: "in_progress",
  all_checked: false,
  status_label: "",
  is_cancelled: false,
  cancelled_at_display: "",
  ...over,
});

const expedition = (): KDSExpeditionCardProjection => ({
  pk: 9,
  ref: "WHATS-9",
  channel_icon: "store",
  customer_name: "Beto",
  fulfillment_icon: "bike",
  fulfillment_label: "Entrega",
  is_delivery: true,
  units_count: "3",
  line_count: 2,
  total_display: "R$ 30,00",
});

describe("kds board presentation", () => {
  it("maps timer class to a functional tone + accent", () => {
    expect(ticketTone("timer-late")).toBe("late");
    expect(ticketTone("timer-warning")).toBe("warning");
    expect(ticketTone("timer-ok")).toBe("ok");
    expect(toneAccent("late")).toContain("red");
    expect(toneAccent("warning")).toContain("amber");
    expect(toneAccent("ok")).toContain("green");
  });

  it("guards expedition cards from prep tickets", () => {
    expect(isExpeditionCard(expedition())).toBe(true);
    expect(isExpeditionCard(ticket())).toBe(false);
  });

  it("shapes the board view + counts", () => {
    const board: KDSBoardProjection = {
      instance_ref: "cafes",
      instance_name: "Cafés",
      instance_type: "prep",
      is_expedition: false,
      tickets: [ticket(), ticket({ pk: 2 })],
      counts: { total: 2, pending: 1, in_progress: 1 },
      cancelled_tickets: [ticket({ pk: 3, is_cancelled: true })],
    };
    const view = boardView(board);
    expect(view.instanceName).toBe("Cafés");
    expect(view.cards).toHaveLength(2);
    expect(view.cancelled).toHaveLength(1);
    expect(view.total).toBe(2);
  });

  it("formats elapsed seconds compactly", () => {
    expect(elapsedLabel(45)).toBe("45s");
    expect(elapsedLabel(90)).toBe("1m 30s");
    expect(elapsedLabel(120)).toBe("2m");
  });
});
