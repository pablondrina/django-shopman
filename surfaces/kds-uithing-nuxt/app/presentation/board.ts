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

const TONE_RANK: Record<KDSTone, number> = { late: 0, warning: 1, ok: 2 };

/** Auto-sort prep tickets by urgency (KDS best practice — work on what's due
 *  first): late before warning before ok, then oldest first within a tone.
 *  Expedition boards keep projection order. */
export function sortByUrgency(
  cards: (KDSTicketProjection | KDSExpeditionCardProjection)[],
): (KDSTicketProjection | KDSExpeditionCardProjection)[] {
  if (cards.some(isExpeditionCard)) return [...cards];
  return [...(cards as KDSTicketProjection[])].sort((a, b) => {
    const ra = TONE_RANK[ticketTone(a.timer_class)];
    const rb = TONE_RANK[ticketTone(b.timer_class)];
    return ra !== rb ? ra - rb : b.elapsed_seconds - a.elapsed_seconds;
  });
}

export interface KDSAllDayCount { name: string; qty: number }

/** "All-day" aggregate (KDS best practice — mise en place / batch prep): how many
 *  of each item are still to make across all active prep tickets (unchecked only). */
export function allDayCounts(
  cards: (KDSTicketProjection | KDSExpeditionCardProjection)[],
): KDSAllDayCount[] {
  const counts = new Map<string, number>();
  for (const card of cards) {
    if (isExpeditionCard(card)) continue;
    for (const item of card.items) {
      if (item.checked) continue;
      counts.set(item.name, (counts.get(item.name) || 0) + item.qty);
    }
  }
  return [...counts.entries()]
    .map(([name, qty]) => ({ name, qty }))
    .sort((a, b) => b.qty - a.qty);
}

export interface KDSBoardView {
  instanceRef: string;
  instanceName: string;
  isExpedition: boolean;
  /** Active cards, auto-sorted by urgency (prep) / projection order (expedition). */
  cards: (KDSTicketProjection | KDSExpeditionCardProjection)[];
  cancelled: KDSTicketProjection[];
  allDay: KDSAllDayCount[];
  counts: Record<string, number>;
  total: number;
}

export function boardView(board: KDSBoardProjection): KDSBoardView {
  const cards = sortByUrgency(board.tickets);
  return {
    instanceRef: board.instance_ref,
    instanceName: board.instance_name,
    isExpedition: board.is_expedition,
    cards,
    cancelled: [...board.cancelled_tickets],
    allDay: allDayCounts(cards),
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
