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

/** Fill for the time-to-SLA bar by tone — o ÚNICO elemento de cor de urgência do
 *  card (cor + comprimento numa peça só, sem o "L" de duas barras). No prazo é um
 *  cinza calmo que só mostra o avanço até a meta; âmbar/vermelho acendem quando
 *  importa. Color só onde tem significado. */
export function toneBar(tone: KDSTone): string {
  if (tone === "late") return "bg-red-500";
  if (tone === "warning") return "bg-amber-500";
  return "bg-muted-foreground/30";
}

/** Superfície do card "PRÓXIMO" pintada ton sur ton no seu próprio tom do semáforo:
 *  fundo sóbrio + borda/ring no mesmo tom (a barra inferior viva continua como é).
 *  Não cria um significado de cor competindo — amplifica o que já existe ("é o
 *  próximo E está atrasado"). É o único card pintado da grade (os demais ficam
 *  neutros), então ele se destaca sem precisar de uma posição/tamanho especial. No
 *  prazo não tem cor de urgência → spotlight neutro elevado. Texto claro por cima. */
export function toneNextSurface(tone: KDSTone): string {
  if (tone === "late") return "bg-red-500/20 border-red-500/55 ring-red-500/45";
  if (tone === "warning") return "bg-amber-500/20 border-amber-500/55 ring-amber-500/45";
  return "bg-accent border-foreground/20 ring-foreground/20";
}

/** Tonal chip classes for the live timer (border+tint+text), shared by card+modal. */
export function toneTimer(tone: KDSTone): string {
  if (tone === "late") return "border-red-500/40 bg-red-500/15 text-red-300";
  if (tone === "warning") return "border-amber-500/40 bg-amber-500/15 text-amber-300";
  return "border-white/10 bg-white/5 text-muted-foreground";
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
  /** Concluídos recentes (≤30min) — para recall (desfazer finalização). */
  recentDone: KDSTicketProjection[];
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
    recentDone: [...(board.recent_done ?? [])],
    allDay: allDayCounts(cards),
    counts: board.counts || {},
    total: board.counts?.total ?? board.tickets.length,
  };
}

/** Map the projection's Material-Symbol icon names (channel + fulfillment) onto
 *  this surface's lucide vocabulary. The KDS Nuxt app renders lucide; the shared
 *  backend projection speaks Material (it also feeds the HTMX queue). Owning the
 *  translation here keeps the projection surface-agnostic. */
const MATERIAL_TO_LUCIDE: Record<string, string> = {
  language: "globe",
  chat: "message-circle",
  fastfood: "utensils-crossed",
  storefront: "store",
  shopping_bag: "shopping-bag",
  local_shipping: "bike",
};

export function lucideIcon(name: string): string {
  return MATERIAL_TO_LUCIDE[name] || name || "circle";
}

/** Split an order ref into the repetitive {channel-date-} prefix and the short
 *  CODE the kitchen actually calls (the suffix after the last hyphen). The code
 *  gets the visual weight; the prefix recedes. */
export function splitRef(ref: string): { prefix: string; code: string } {
  const i = ref.lastIndexOf("-");
  if (i < 0) return { prefix: "", code: ref };
  return { prefix: ref.slice(0, i + 1), code: ref.slice(i + 1) };
}

/** Total unchecked vs total item lines — for the minimal card's progress hint. */
export function itemProgress(items: { checked: boolean }[]): { done: number; total: number } {
  return { done: items.filter((i) => i.checked).length, total: items.length };
}

/** Elapsed seconds → compact timer label. Segundos só no 1º minuto ("45s"); a partir
 *  de 1 min some o tique-taque e mostra minutos inteiros ("24m"), depois "1h 5m" —
 *  mais calmo e glanceável numa cozinha (a barra de SLA já dá o "quão perto da meta"). */
export function elapsedLabel(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  return m % 60 ? `${h}h ${m % 60}m` : `${h}h`;
}

/** Compact target-SLA label ("alvo 12m") — recessive companion to the live timer
 *  so the operator reads elapsed *against* the promise, not in a vacuum. */
export function targetLabel(targetSeconds: number): string {
  const m = Math.max(0, Math.round(targetSeconds / 60));
  return m >= 60 ? `${Math.floor(m / 60)}h${m % 60 ? ` ${m % 60}m` : ""}` : `${m}m`;
}

/** Elapsed-vs-target fill for the time-to-SLA bar — the at-a-glance urgency cue
 *  winning KDS products lean on (Toast/Fresh). Clamped to 0–100 so the bar fills
 *  as the ticket approaches its promise and pins full once it's overdue; the tone
 *  (verde→âmbar→vermelho) carries the over-SLA escalation. */
export function slaPercent(elapsedSeconds: number, targetSeconds: number): number {
  if (targetSeconds <= 0) return 0;
  return Math.min(100, Math.max(0, (elapsedSeconds / targetSeconds) * 100));
}
