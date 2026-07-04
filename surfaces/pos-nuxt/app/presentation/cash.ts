// Presentation — cash drawer shaping (spec §2.6, blind count).
//
// Pure transforms for the POS cash panel: the movement-kind labels, the
// opened-at formatting, and the terminal-occupied gate. The shift's full
// reconciliation report (expected vs counted, variance) lives in the backoffice
// (Unfold), NOT here — the POS never reveals the expected drawer, so the
// operator counts blind and the system computes the variance server-side.

import type { POSCashRuntimeProjection } from "~/types/pos";

const MOVEMENT_LABELS: Record<string, string> = {
  sangria: "Sangria",
  suprimento: "Suprimento",
  ajuste: "Ajuste",
};

export function movementLabel(kind: string): string {
  return MOVEMENT_LABELS[kind] || kind;
}

/**
 * Format the shift opening timestamp for the panel header (pt-BR, short). Falls
 * back to the raw string if it is not a parseable date, and to an em dash when
 * absent.
 */
export function formatOpenedAt(raw: string | null | undefined): string {
  if (!raw) return "—";
  const date = new Date(raw);
  return Number.isNaN(date.getTime())
    ? raw
    : date.toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

/**
 * Whether the terminal is held by another operator's open shift — the panel
 * blocks selling and tells the operator to use the right operator or close the
 * shift in the backoffice. Driven by the runtime Projection, never inferred.
 */
export function isTerminalOccupied(
  runtime: POSCashRuntimeProjection,
  hasOpenShift: boolean,
): boolean {
  return runtime.status === "terminal_occupied"
    || (!hasOpenShift && Boolean(runtime.blocking_operator_username));
}
