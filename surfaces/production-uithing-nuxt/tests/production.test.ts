import { describe, expect, it } from "vitest";

import {
  elapsedLabel,
  kdsCardAffordances,
  matchesKdsQuery,
  matchesRowQuery,
  parseShortage,
  rowHasActivity,
  splitRef,
  startableWorkOrder,
  statusTone,
  timerBar,
  timerChip,
  timerTone,
  toneBadge,
} from "../app/presentation/production";
import type {
  ProductionKDSCardProjection,
  ProductionMatrixRowProjection,
  WorkOrderCardProjection,
} from "../app/types/production";

const kdsCard = (over: Partial<ProductionKDSCardProjection> = {}): ProductionKDSCardProjection => ({
  pk: 1,
  ref: "WO-001",
  output_sku: "PAO-FRANCES",
  recipe_name: "Pão Francês",
  started_qty: "100",
  operator_ref: "user:ana",
  position_ref: "forno",
  started_at_display: "08:00",
  elapsed_seconds: 120,
  elapsed_minutes: 2,
  target_seconds: 1800,
  timer_class: "timer-ok",
  current_step: "Mistura",
  current_step_index: 1,
  total_steps: 2,
  current_step_name: "Mistura",
  step_progress_pct: 40,
  next_step_name: "Forno",
  time_remaining_min: 5,
  can_finish: true,
  ...over,
});

const wo = (over: Partial<WorkOrderCardProjection> = {}): WorkOrderCardProjection => ({
  pk: 10,
  ref: "WO-010",
  recipe_pk: 5,
  recipe_ref: "pao",
  recipe_name: "Pão",
  base_usages: [],
  output_sku: "PAO",
  status: "planned",
  status_label: "Planejado",
  status_color: "",
  planned_qty: "50",
  started_qty: "0",
  finished_qty: "0",
  yield_rate: "",
  loss: "",
  operator_ref: "",
  position_ref: "forno",
  target_date_display: "25/06/2026",
  started_at_display: "",
  created_at_display: "07:00",
  progress_pct: 0,
  committed_qty: "0",
  order_commitments: [],
  can_void: true,
  ...over,
});

const row = (over: Partial<ProductionMatrixRowProjection> = {}): ProductionMatrixRowProjection => ({
  recipe_pk: 5,
  output_sku: "PAO",
  recipe_name: "Pão Francês",
  base_usages: [],
  suggestion: null,
  planned_orders: [],
  started_orders: [],
  finished_orders: [],
  planned_qty: "0",
  started_qty: "0",
  finished_qty: "0",
  loss_qty: "0",
  ...over,
});

describe("timerTone / chips", () => {
  it("maps timer_class to urgency", () => {
    expect(timerTone("timer-ok")).toBe("ok");
    expect(timerTone("timer-warning")).toBe("warning");
    expect(timerTone("timer-late")).toBe("late");
  });
  it("timerChip/timerBar carry saturated meaning only when late/warning", () => {
    expect(timerChip("late")).toContain("red");
    expect(timerChip("ok")).toContain("muted");
    expect(timerBar("warning")).toContain("amber");
    expect(timerBar("ok")).toContain("primary");
  });
});

describe("statusTone", () => {
  it("maps WorkOrder lifecycle to tones", () => {
    expect(statusTone("planned")).toBe("info");
    expect(statusTone("started")).toBe("warning");
    expect(statusTone("finished")).toBe("success");
    expect(statusTone("void")).toBe("danger");
    expect(statusTone("whatever")).toBe("neutral");
  });
  it("toneBadge returns a class per tone", () => {
    expect(toneBadge("success")).toContain("green");
    expect(toneBadge("neutral")).toContain("muted");
  });
});

describe("splitRef / elapsedLabel", () => {
  it("splits a WO ref into prefix + code", () => {
    expect(splitRef("WO-001")).toEqual({ prefix: "WO-", code: "001" });
    expect(splitRef("ABC")).toEqual({ prefix: "", code: "ABC" });
  });
  it("formats elapsed compactly", () => {
    expect(elapsedLabel(45)).toBe("45s");
    expect(elapsedLabel(90)).toBe("1m");
    expect(elapsedLabel(65 * 60)).toBe("1h 5m");
    expect(elapsedLabel(120 * 60)).toBe("2h");
  });
});

describe("kdsCardAffordances", () => {
  it("offers advance + finish + void for a started WO with steps", () => {
    const refs = kdsCardAffordances(kdsCard()).map((a) => a.ref);
    expect(refs).toEqual(["advance_step", "finish", "void"]);
  });
  it("drops advance when there is no next step", () => {
    const refs = kdsCardAffordances(kdsCard({ total_steps: 0, next_step_name: "" })).map((a) => a.ref);
    expect(refs).toEqual(["finish", "void"]);
  });
  it("drops finish when the operator cannot finish", () => {
    const refs = kdsCardAffordances(kdsCard({ can_finish: false })).map((a) => a.ref);
    expect(refs).toEqual(["advance_step", "void"]);
  });
});

describe("matchesKdsQuery", () => {
  it("matches on ref, sku, recipe, operator; empty matches all", () => {
    const c = kdsCard();
    expect(matchesKdsQuery(c, "")).toBe(true);
    expect(matchesKdsQuery(c, "pao")).toBe(true);
    expect(matchesKdsQuery(c, "ana")).toBe(true);
    expect(matchesKdsQuery(c, "001")).toBe(true);
    expect(matchesKdsQuery(c, "croissant")).toBe(false);
  });
});

describe("matrix helpers", () => {
  it("rowHasActivity is true with orders or a suggestion", () => {
    expect(rowHasActivity(row())).toBe(false);
    expect(rowHasActivity(row({ planned_orders: [wo()] }))).toBe(true);
    expect(rowHasActivity(row({ suggestion: { recipe_pk: 5, recipe_ref: "p", recipe_name: "P", base_usages: [], output_sku: "PAO", quantity: "10", committed: "0", avg_demand: "5", confidence: "Alta" } }))).toBe(true);
  });
  it("matchesRowQuery filters on sku + name", () => {
    expect(matchesRowQuery(row(), "")).toBe(true);
    expect(matchesRowQuery(row(), "franc")).toBe(true);
    expect(matchesRowQuery(row(), "bolo")).toBe(false);
  });
  it("startableWorkOrder returns the first planned WO or null", () => {
    expect(startableWorkOrder(row())).toBeNull();
    expect(startableWorkOrder(row({ planned_orders: [wo()] }))?.pk).toBe(10);
  });
});

describe("parseShortage", () => {
  it("extracts a material shortage envelope", () => {
    const s = parseShortage({ error: { code: "material_shortage", work_order_ref: "WO-1", missing: [] } });
    expect(s?.code).toBe("material_shortage");
  });
  it("extracts an order shortage envelope", () => {
    const s = parseShortage({ error: { code: "order_shortage", work_order_ref: "WO-1", required: "12", requested: "8", order_refs: [] } });
    expect(s?.code).toBe("order_shortage");
  });
  it("returns null for non-shortage errors", () => {
    expect(parseShortage({ detail: "boom" })).toBeNull();
    expect(parseShortage(null)).toBeNull();
    expect(parseShortage({ error: { code: "other" } })).toBeNull();
  });
});
