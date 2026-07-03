import { describe, expect, it } from "vitest";

import {
  alertTarget,
  elapsedLabel,
  matchesRowQuery,
  parseShortage,
  rowCommitments,
  rowCommittedUnits,
  rowHasActivity,
  startableWorkOrder,
  timerChip,
  timerTone,
} from "../app/presentation/production";
import type {
  ProductionMatrixRowProjection,
  WorkOrderCardProjection,
} from "../app/types/production";

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
  it("timerChip carries saturated meaning only when late/warning", () => {
    expect(timerChip("late")).toContain("red");
    expect(timerChip("ok")).toContain("muted");
  });
});

describe("elapsedLabel", () => {
  it("formats elapsed compactly", () => {
    expect(elapsedLabel(45)).toBe("45s");
    expect(elapsedLabel(90)).toBe("1m");
    expect(elapsedLabel(65 * 60)).toBe("1h 5m");
    expect(elapsedLabel(120 * 60)).toBe("2h");
  });
});

describe("grid helpers", () => {
  it("rowHasActivity is true with orders or a suggestion", () => {
    expect(rowHasActivity(row())).toBe(false);
    expect(rowHasActivity(row({ planned_orders: [wo()] }))).toBe(true);
    expect(rowHasActivity(row({ suggestion: { recipe_pk: 5, recipe_ref: "p", recipe_name: "P", base_usages: [], output_sku: "PAO", quantity: "10", committed: "0", avg_demand: "5", confidence: "Alta", sample_size: 3, high_demand_applied: false, explanation_parts: [] } }))).toBe(true);
  });
  it("matchesRowQuery filters on sku + name + WO refs (alert deep-link)", () => {
    expect(matchesRowQuery(row(), "")).toBe(true);
    expect(matchesRowQuery(row(), "franc")).toBe(true);
    expect(matchesRowQuery(row(), "bolo")).toBe(false);
    expect(matchesRowQuery(row({ planned_orders: [wo()] }), "wo-010")).toBe(true);
  });
  it("rowCommitments dedupes order refs across open WOs", () => {
    const commitment = (ref: string) => ({ ref, status: "confirmed", status_label: "Confirmado", qty_required: "5" });
    const r = row({
      planned_orders: [wo({ order_commitments: [commitment("O-1"), commitment("O-2")] })],
      started_orders: [wo({ pk: 11, ref: "WO-011", order_commitments: [commitment("O-1")] })],
    });
    expect(rowCommitments(r).map((c) => c.ref)).toEqual(["O-1", "O-2"]);
    expect(rowCommitments(row())).toEqual([]);
  });
  it("alertTarget routes production alerts to the stage where they resolve", () => {
    expect(alertTarget({ type: "production_late", order_ref: "WO-1" })).toEqual({ to: "/", q: "WO-1" });
    expect(alertTarget({ type: "production_stock_short", order_ref: "WO-1" })).toEqual({ to: "/expedicao", q: "WO-1" });
    expect(alertTarget({ type: "production_forgotten", order_ref: "WO-2" })).toEqual({ to: "/planejamento", q: "WO-2" });
    expect(alertTarget({ type: "production_low_yield", order_ref: "WO-3" })).toBeNull();
    expect(alertTarget({ type: "stock_low", order_ref: "" })).toBeNull();
  });
  it("rowCommittedUnits sums committed quantities across linked orders", () => {
    const commitment = (ref: string, qty: string) => ({ ref, status: "confirmed", status_label: "Confirmado", qty_required: qty });
    const r = row({
      planned_orders: [wo({ order_commitments: [commitment("O-1", "4"), commitment("O-2", "2,5")] })],
      started_orders: [wo({ pk: 11, ref: "WO-011", order_commitments: [commitment("O-1", "4")] })],
    });
    expect(rowCommittedUnits(r)).toBe(6.5);
    expect(rowCommittedUnits(row())).toBe(0);
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
