// Presentation — production board shaping. Pure transforms over the production
// projections (served by shopman/backstage/projections/production.py). The
// projections are already screen-ready (status_label, timer_class, step state,
// can_* flags pre-resolved); this layer only derives the view shape, the
// functional-color tone, and the action affordances. No lifecycle arithmetic
// (the backend owns the WorkOrder lifecycle).
import type {
  OrderCommitmentProjection,
  ProductionKDSCardProjection,
  ProductionMatrixRowProjection,
  ProductionShortageError,
  ProductionTimerClass,
  WorkOrderCardProjection,
} from "~/types/production";

// ── Timer tone (urgency of the started clock) ──────────────────────────────

export type TimerTone = "ok" | "warning" | "late";

export function timerTone(timerClass: ProductionTimerClass): TimerTone {
  if (timerClass === "timer-late") return "late";
  if (timerClass === "timer-warning") return "warning";
  return "ok";
}

/** Tonal chip classes for the live timer. Calm by default; only warning/late
 *  carry saturated meaning. */
export function timerChip(tone: TimerTone): string {
  switch (tone) {
    case "late":
      return "border-red-500/40 bg-red-500/10 text-red-700 dark:text-red-300";
    case "warning":
      return "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300";
    default:
      return "border-border bg-muted text-muted-foreground";
  }
}

/** Progress-bar fill class for a timer tone (the step progress within a card). */
export function timerBar(tone: TimerTone): string {
  switch (tone) {
    case "late":
      return "bg-red-500";
    case "warning":
      return "bg-amber-500";
    default:
      return "bg-primary";
  }
}

// ── Status tone (WorkOrder lifecycle on the planning board) ─────────────────

export type Tone = "info" | "warning" | "success" | "danger" | "neutral";

const WO_STATUS_TONE: Record<string, Tone> = {
  planned: "info",
  started: "warning",
  finished: "success",
  void: "danger",
};

export function statusTone(status: string): Tone {
  return WO_STATUS_TONE[status] ?? "neutral";
}

export function toneBadge(tone: Tone): string {
  switch (tone) {
    case "danger":
      return "border-red-500/40 bg-red-500/10 text-red-700 dark:text-red-300";
    case "warning":
      return "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300";
    case "success":
      return "border-green-600/40 bg-green-600/10 text-green-700 dark:text-green-300";
    case "info":
      return "border-blue-500/40 bg-blue-500/10 text-blue-700 dark:text-blue-300";
    default:
      return "border-border bg-muted text-muted-foreground";
  }
}

// ── Ref + elapsed helpers ──────────────────────────────────────────────────

/** Split a WO ref (e.g. "WO-001") into the {prefix-} and the short code. */
export function splitRef(ref: string): { prefix: string; code: string } {
  const i = ref.lastIndexOf("-");
  if (i < 0) return { prefix: "", code: ref };
  return { prefix: ref.slice(0, i + 1), code: ref.slice(i + 1) };
}

/** Elapsed seconds → compact label. Seconds in the first minute, then whole
 *  minutes, then "1h 5m". */
export function elapsedLabel(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  return m % 60 ? `${h}h ${m % 60}m` : `${h}h`;
}

// ── Live floor affordances (advance step / finish / void) ──────────────────

export type FloorAffordanceRef = "advance_step" | "finish" | "void";

export interface FloorAffordance {
  ref: FloorAffordanceRef;
  label: string;
  icon: string;
  priority: "primary" | "secondary" | "danger";
}

/** The actions a started-WO card offers on the live floor, from the projection's
 *  pre-resolved flags. Order = visual priority. */
export function kdsCardAffordances(card: ProductionKDSCardProjection): FloorAffordance[] {
  const out: FloorAffordance[] = [];
  const hasNextStep = card.total_steps > 0 && Boolean(card.next_step_name);
  if (hasNextStep) {
    out.push({ ref: "advance_step", label: "Avançar passo", icon: "lucide:chevrons-right", priority: "secondary" });
  }
  if (card.can_finish) {
    out.push({ ref: "finish", label: "Concluir", icon: "lucide:check", priority: "primary" });
  }
  out.push({ ref: "void", label: "Estornar", icon: "lucide:x", priority: "danger" });
  return out;
}

/** Filter live-floor cards by a free-text query over ref, SKU, recipe, operator. */
export function matchesKdsQuery(card: ProductionKDSCardProjection, rawQuery: string): boolean {
  const q = rawQuery.trim().toLowerCase();
  if (!q) return true;
  return [card.ref, card.output_sku, card.recipe_name, card.operator_ref].join(" ").toLowerCase().includes(q);
}

// ── Planning matrix shaping ────────────────────────────────────────────────

/** Whether a matrix row has anything actionable/visible (avoids empty noise). */
export function rowHasActivity(row: ProductionMatrixRowProjection): boolean {
  return (
    row.planned_orders.length > 0 ||
    row.started_orders.length > 0 ||
    row.finished_orders.length > 0 ||
    row.suggestion != null
  );
}

/** Filter matrix rows by a free-text query over SKU + recipe name + WO refs.
 *  Refs matter for alert deep-links ("WO-2026-00042" lands on its row). */
export function matchesRowQuery(row: ProductionMatrixRowProjection, rawQuery: string): boolean {
  const q = rawQuery.trim().toLowerCase();
  if (!q) return true;
  const refs = [...row.planned_orders, ...row.started_orders, ...row.finished_orders].map((wo) => wo.ref);
  return [row.output_sku, row.recipe_name, ...refs].join(" ").toLowerCase().includes(q);
}

// ── Alert deep-links ───────────────────────────────────────────────────────

/** Where an operator alert resolves, if anywhere in this app.
 *  - late/stock_short → live floor (the WO is started, on screen);
 *  - forgotten → planning matrix (the WO is planned);
 *  - low_yield/others → no target (the WO already left both boards). */
export function alertTarget(alert: { type: string; order_ref: string }): { to: string; q: string } | null {
  if (!alert.order_ref) return null;
  if (alert.type === "production_late" || alert.type === "production_stock_short") {
    return { to: "/", q: alert.order_ref };
  }
  if (alert.type === "production_forgotten") {
    return { to: "/planejamento", q: alert.order_ref };
  }
  return null;
}

/** Whether a planning row can be started (has a planned order and no started yet). */
export function startableWorkOrder(row: ProductionMatrixRowProjection): WorkOrderCardProjection | null {
  return row.planned_orders[0] ?? null;
}

/** Order commitments across a row's open WOs, deduped by order ref.
 *  The matrix chip ("N pedidos") and its detail list render from this. */
export function rowCommitments(row: ProductionMatrixRowProjection): OrderCommitmentProjection[] {
  const seen = new Set<string>();
  const out: OrderCommitmentProjection[] = [];
  for (const wo of [...row.planned_orders, ...row.started_orders]) {
    for (const commitment of wo.order_commitments ?? []) {
      if (seen.has(commitment.ref)) continue;
      seen.add(commitment.ref);
      out.push(commitment);
    }
  }
  return out;
}

// ── Shortage envelope parsing ──────────────────────────────────────────────

/** Pull the structured shortage error out of a proxied 409 response body, if any.
 *  The floor app renders the material/order shortage modal from this. */
export function parseShortage(errorBody: unknown): ProductionShortageError | null {
  const error = (errorBody as { error?: unknown })?.error;
  if (!error || typeof error !== "object") return null;
  const code = (error as { code?: string }).code;
  if (code === "material_shortage" || code === "order_shortage") {
    return error as ProductionShortageError;
  }
  return null;
}
