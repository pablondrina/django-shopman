// Presentation — KDS board shaping (Arc 2). Pure transforms over the board
// Projection (served by shopman/backstage/api/kds.py). The projection is already
// screen-ready (timer_class, status_label, all_checked pre-resolved); this layer
// only derives the view shape + the functional-color tone for the semaphore. No
// time/SLA arithmetic (the backend owns elapsed/target/timer_class).
import type {
  KDSBoardProjection,
  KDSExpeditionCardProjection,
  KDSTicketProjection,
  KDSTimerClass,
} from "~/types/kds";

/** Functional tone for a ticket's urgency (cor só onde tem significado). */
export type KDSTone = "ok" | "warning" | "late";

export function ticketTone(timerClass: KDSTimerClass): KDSTone {
  if (timerClass === "timer-late") return "late";
  if (timerClass === "timer-warning") return "warning";
  return "ok";
}

/** Left-accent classes for the card by tone — Tailwind status colors (verde=ok,
 *  âmbar=atenção, vermelho=atrasado), o mesmo idioma do PDV/KDS-HTMX. */
export function toneAccent(tone: KDSTone): string {
  if (tone === "late") return "border-l-red-500";
  if (tone === "warning") return "border-l-amber-500";
  return "border-l-green-500";
}

/** Type guard: expedition boards hold expedition cards, prep boards hold tickets. */
export function isExpeditionCard(
  card: KDSTicketProjection | KDSExpeditionCardProjection,
): card is KDSExpeditionCardProjection {
  return "fulfillment_label" in card && !("items" in card);
}

export interface KDSBoardView {
  instanceRef: string;
  instanceName: string;
  isExpedition: boolean;
  /** Active cards in projection order (prep tickets or expedition cards). */
  cards: (KDSTicketProjection | KDSExpeditionCardProjection)[];
  cancelled: KDSTicketProjection[];
  counts: Record<string, number>;
  total: number;
}

export function boardView(board: KDSBoardProjection): KDSBoardView {
  return {
    instanceRef: board.instance_ref,
    instanceName: board.instance_name,
    isExpedition: board.is_expedition,
    cards: [...board.tickets],
    cancelled: [...board.cancelled_tickets],
    counts: board.counts || {},
    total: board.counts?.total ?? board.tickets.length,
  };
}

/** Elapsed seconds → "Ns" / "Nm" compact label for the timer chip. */
export function elapsedLabel(seconds: number): string {
  if (seconds < 60) return `${Math.max(0, Math.round(seconds))}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return s ? `${m}m ${s}s` : `${m}m`;
}
