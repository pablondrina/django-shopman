import { describe, expect, it } from "vitest";

import {
  allDayCounts,
  boardView,
  elapsedLabel,
  isExpeditionCard,
  itemProgress,
  lucideIcon,
  slaPercent,
  sortByUrgency,
  splitRef,
  targetLabel,
  ticketTone,
  toneBar,
  toneNextSurface,
  toneTimer,
} from "../app/presentation/board";
import type {
  KDSBoardProjection,
  KDSExpeditionCardProjection,
  KDSTicketProjection,
} from "../app/types/kds";

const ticket = (
  over: Partial<KDSTicketProjection> = {},
): KDSTicketProjection => ({
  pk: 1,
  order_ref: "PDV-1",
  channel_icon: "store",
  customer_name: "Ana",
  fulfillment_icon: "bag",
  created_at_display: "08:00",
  elapsed_seconds: 30,
  target_seconds: 600,
  timer_class: "timer-ok",
  items: [
    {
      sku: "x",
      name: "Pão",
      qty: 2,
      notes: "",
      checked: false,
      stock_warning: "",
    },
  ],
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
  it("maps timer class to a functional tone", () => {
    expect(ticketTone("timer-late")).toBe("late");
    expect(ticketTone("timer-warning")).toBe("warning");
    expect(ticketTone("timer-ok")).toBe("ok");
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

  it("formats elapsed compactly — seconds only in the first minute, then whole minutes", () => {
    expect(elapsedLabel(45)).toBe("45s");
    expect(elapsedLabel(90)).toBe("1m"); // sem tique-taque depois do 1º minuto
    expect(elapsedLabel(120)).toBe("2m");
    expect(elapsedLabel(3600)).toBe("1h");
    expect(elapsedLabel(7200)).toBe("2h");
    expect(elapsedLabel(9000)).toBe("2h 30m");
  });

  it("maps Material-Symbol icon names onto lucide, with a safe fallback", () => {
    expect(lucideIcon("local_shipping")).toBe("bike");
    expect(lucideIcon("storefront")).toBe("store");
    expect(lucideIcon("fastfood")).toBe("utensils-crossed");
    expect(lucideIcon("store")).toBe("store"); // already lucide → passthrough
    expect(lucideIcon("")).toBe("circle"); // empty → fallback
  });

  it("labels the target SLA compactly", () => {
    expect(targetLabel(600)).toBe("10m");
    expect(targetLabel(720)).toBe("12m");
    expect(targetLabel(5400)).toBe("1h 30m");
    expect(targetLabel(3600)).toBe("1h");
  });

  it("fills the time-to-SLA bar (elapsed vs target, clamped 0–100)", () => {
    expect(slaPercent(0, 600)).toBe(0);
    expect(slaPercent(300, 600)).toBe(50);
    expect(slaPercent(600, 600)).toBe(100);
    expect(slaPercent(1200, 600)).toBe(100); // overdue pins full; tone escalates
    expect(slaPercent(60, 0)).toBe(0); // no target → no bar
  });

  it("maps tone to a solid bar fill and a tonal timer chip", () => {
    expect(toneBar("late")).toContain("red");
    expect(toneBar("warning")).toContain("amber");
    expect(toneBar("ok")).not.toMatch(/red|amber|green/); // no prazo = cinza calmo
    expect(toneTimer("late")).toContain("red");
    expect(toneTimer("ok")).toContain("muted-foreground");
  });

  it("paints the next-card surface ton sur ton (neutral when on-time)", () => {
    expect(toneNextSurface("late")).toContain("red");
    expect(toneNextSurface("warning")).toContain("amber");
    expect(toneNextSurface("ok")).not.toMatch(/red|amber|green/);
  });

  it("auto-sorts prep tickets by urgency (late first, then oldest)", () => {
    const ok = ticket({ pk: 1, timer_class: "timer-ok", elapsed_seconds: 10 });
    const lateNew = ticket({
      pk: 2,
      timer_class: "timer-late",
      elapsed_seconds: 100,
    });
    const lateOld = ticket({
      pk: 3,
      timer_class: "timer-late",
      elapsed_seconds: 500,
    });
    const warn = ticket({
      pk: 4,
      timer_class: "timer-warning",
      elapsed_seconds: 50,
    });
    const sorted = sortByUrgency([ok, lateNew, warn, lateOld]);
    expect(sorted.map((c) => (c as KDSTicketProjection).pk)).toEqual([
      3, 2, 4, 1,
    ]);
  });

  it("splits the ref into a recessive prefix + the hero code", () => {
    expect(splitRef("IFOOD-260606-2L8Y")).toEqual({
      prefix: "IFOOD-260606-",
      code: "2L8Y",
    });
    expect(splitRef("PDV-260606-NMEQ")).toEqual({
      prefix: "PDV-260606-",
      code: "NMEQ",
    });
    expect(splitRef("SEMTRACO")).toEqual({ prefix: "", code: "SEMTRACO" });
  });

  it("reports item progress (done/total)", () => {
    expect(
      itemProgress([{ checked: true }, { checked: false }, { checked: false }]),
    ).toEqual({ done: 1, total: 3 });
  });

  it("aggregates all-day counts of unchecked items", () => {
    const t1 = ticket({
      pk: 1,
      items: [
        {
          sku: "a",
          name: "Baguete",
          qty: 2,
          notes: "",
          checked: false,
          stock_warning: "",
        },
        {
          sku: "b",
          name: "Café",
          qty: 1,
          notes: "",
          checked: true,
          stock_warning: "",
        },
      ],
    });
    const t2 = ticket({
      pk: 2,
      items: [
        {
          sku: "a",
          name: "Baguete",
          qty: 3,
          notes: "",
          checked: false,
          stock_warning: "",
        },
      ],
    });
    const allDay = allDayCounts([t1, t2]);
    expect(allDay).toEqual([{ name: "Baguete", qty: 5 }]); // café excluded (checked)
  });
});
