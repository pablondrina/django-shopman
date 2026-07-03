// Presentation — production grid shaping. Pure transforms over the production
// projections (served by shopman/backstage/projections/production.py). The
// projections are already screen-ready (status_label, timer_class, step state,
// can_* flags pre-resolved); this layer only derives the view shape and the
// functional-color tone. No lifecycle arithmetic (the backend owns the
// WorkOrder lifecycle).
import type {
  OrderCommitmentProjection,
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
// ── Elapsed helper ──────────────────────────────────────────────────────────

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

// ── Datas (chips Hoje · Amanhã · dia-da-semana + data cheia fixa) ──────────

const WEEKDAYS_PT = ["Domingo", "Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado"];
const MONTHS_PT = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];

function parseISODate(iso: string): Date | null {
  const [y, m, d] = iso.split("-").map(Number);
  if (!y || !m || !d) return null;
  return new Date(y, m - 1, d);
}

/** "2026-07-04" → "Sábado" — rótulo do chip quando a data foi escolhida à mão. */
export function weekdayLabel(iso: string): string {
  const date = parseISODate(iso);
  return date ? WEEKDAYS_PT[date.getDay()]! : "";
}

/** "2026-07-04" → "04 jul 2026" — a data cheia, sempre no mesmo lugar. */
export function fullDateLabel(iso: string): string {
  const date = parseISODate(iso);
  if (!date) return "";
  return `${String(date.getDate()).padStart(2, "0")} ${MONTHS_PT[date.getMonth()]} ${date.getFullYear()}`;
}

/** Segundos restantes → "12:34" (contagem regressiva do timer do forno). */
export function countdownLabel(secondsLeft: number): string {
  const s = Math.max(0, Math.round(secondsLeft));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

// ── Production grid shaping ────────────────────────────────────────────────

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
 *  - late → Produção (o lote vivo está lá);
 *  - stock_short → Expedição (a falha aconteceu ao expedir);
 *  - forgotten → Planejamento (a WO nunca saiu do planejado);
 *  - low_yield/others → sem destino (a WO já saiu das grades). */
export function alertTarget(alert: { type: string; order_ref: string }): { to: string; q: string } | null {
  if (!alert.order_ref) return null;
  if (alert.type === "production_late") return { to: "/", q: alert.order_ref };
  if (alert.type === "production_stock_short") return { to: "/expedicao", q: alert.order_ref };
  if (alert.type === "production_forgotten") return { to: "/planejamento", q: alert.order_ref };
  return null;
}

/** Whether a planning row can be started (has a planned order and no started yet). */
export function startableWorkOrder(row: ProductionMatrixRowProjection): WorkOrderCardProjection | null {
  return row.planned_orders[0] ?? null;
}

/** Order commitments across a row's open WOs, deduped by order ref.
 *  The committed-units chip and its detail list render from this. */
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

/** UNIDADES da SKU comprometidas com pedidos (o que importa na bancada —
 *  "quantas dessas já têm dono"), somadas sobre os pedidos vinculados. */
export function rowCommittedUnits(row: ProductionMatrixRowProjection): number {
  return rowCommitments(row).reduce(
    (total, commitment) => total + (parseFloat(commitment.qty_required.replace(",", ".")) || 0),
    0,
  );
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
