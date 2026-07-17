// Presentation — relatório de sessão de caixa (leituras X/Z + histórico).
//
// Transforms puras sobre a CashSessionReport: horário/período do turno, o
// sinal do movimento de gaveta (entrada/saída) e o display assinado. BLIND: o
// contrato nunca traz o esperado da gaveta; nada aqui deriva ou reconstitui a
// conferência (espírito do comentário em presentation/cash.ts).

import type { CashMovementRow, ShiftReading } from "~/types/cashReport";
import { formatBRL } from "~/utils/posIntent";

/** Hora curta (pt-BR) de um ISO datetime; "" quando ausente ou inválido. */
export function timeDisplay(raw: string | null | undefined): string {
  if (!raw) return "";
  const date = new Date(raw);
  return Number.isNaN(date.getTime())
    ? ""
    : date.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

/** Período do turno: "08:02 às 12:30" fechado, "desde 08:02" aberto. */
export function shiftPeriodDisplay(reading: Pick<ShiftReading, "opened_at" | "closed_at">): string {
  const opened = timeDisplay(reading.opened_at);
  const closed = timeDisplay(reading.closed_at);
  if (!opened) return "";
  return closed ? `${opened} às ${closed}` : `desde ${opened}`;
}

/**
 * Direção do movimento na gaveta: suprimento entra, sangria sai, ajuste segue
 * o sinal (positivo = sobra registrada, negativo = falta).
 */
export function movementFlow(movement: Pick<CashMovementRow, "kind" | "amount_q">): "in" | "out" {
  if (movement.kind === "suprimento") return "in";
  if (movement.kind === "ajuste") return movement.amount_q >= 0 ? "in" : "out";
  return "out";
}

/** Valor do movimento com sinal explícito: "+R$ 10,00" / "-R$ 20,00". */
export function signedMovementDisplay(movement: Pick<CashMovementRow, "kind" | "amount_q">): string {
  const sign = movementFlow(movement) === "in" ? "+" : "-";
  return `${sign}${formatBRL(Math.abs(movement.amount_q))}`;
}

/** Título da leitura: X (parcial, turno aberto) ou Z (turno fechado). */
export function readingTitle(reading: Pick<ShiftReading, "status" | "shift_id">): string {
  return reading.status === "open"
    ? `Leitura X · turno #${reading.shift_id}`
    : `Leitura Z · turno #${reading.shift_id}`;
}
