// Presentation — fechamento do DIA (contagem cega de sobras/perdas).
//
// Transforms puras sobre a DayClosingProjection. As BADGES derivam de
// `classification` AQUI (a projection carrega badge_css/badge_label do Admin;
// a superfície não consome — cada app decide a própria pele). "D-1" é jargão
// interno: o rótulo visível é sempre "Ontem".

import type {
  ClosingItemProjection,
  ClosingPendingProduction,
  ClosingProductionRow,
} from "~/types/closing";

export interface ClosingBadge {
  label: string;
  css: string;
}

export function closingBadge(classification: string): ClosingBadge {
  if (classification === "d1") {
    return { label: "Ontem", css: "border-warning/50 bg-warning/10 text-amber-700 dark:text-amber-400" };
  }
  if (classification === "loss") {
    return { label: "Perda", css: "border-destructive/50 bg-destructive/10 text-destructive" };
  }
  return { label: "Neutro", css: "border-border bg-muted text-muted-foreground" };
}

/** Linhas da tabela "Produção do dia" (SKU · planejado · feito · perda). */
export function productionRows(
  summary: Record<string, ClosingProductionRow> | null | undefined,
): Array<{ sku: string; planned: number; finished: number; loss: number }> {
  if (!summary) return [];
  return Object.entries(summary)
    .map(([recipeRef, row]) => ({
      sku: row.output_sku || recipeRef,
      planned: row.planned ?? 0,
      finished: row.finished ?? 0,
      loss: row.loss ?? 0,
    }))
    .sort((a, b) => a.sku.localeCompare(b.sku));
}

/** Status da produção pendente, marcando atraso como o Admin fazia. */
export function pendingStatusDisplay(row: ClosingPendingProduction): string {
  return row.is_overdue ? `${row.status_label} (atrasada)` : row.status_label;
}

/** Contagem cega: só dígitos (quantidades inteiras, nunca negativas). */
export function sanitizeQtyInput(raw: string): string {
  return raw.replace(/\D/g, "");
}

/** O formulário só envia quando TODO item tem uma contagem explícita. */
export function allQuantitiesFilled(
  items: ClosingItemProjection[],
  inputs: Record<string, string>,
): boolean {
  if (!items.length) return false;
  return items.every((item) => /^\d+$/.test((inputs[item.sku] ?? "").trim()));
}

/** Payload do POST: { sku: "qty" } com tudo validado. */
export function buildQuantitiesPayload(
  items: ClosingItemProjection[],
  inputs: Record<string, string>,
): Record<string, string> {
  const payload: Record<string, string> = {};
  for (const item of items) {
    payload[item.sku] = String(parseInt((inputs[item.sku] ?? "0").trim() || "0", 10));
  }
  return payload;
}
