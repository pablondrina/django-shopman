// Presentation — order board shaping. Pure transforms over the order queue
// projection (served by shopman/backstage/api/operations.py). The projection is
// already screen-ready (status_label, timer_class, next_action_label, can_* flags
// pre-resolved); this layer only derives the view shape, the functional-color tone,
// and the action affordances. No status arithmetic (the backend owns the lifecycle).
import type {
  OrderCardProjection,
  OrderTimerClass,
  TwoZoneQueueProjection,
} from "~/types/orders";

// ── Status tone (functional color; chrome stays neutral) ───────────────────

export type Tone = "info" | "warning" | "success" | "danger" | "neutral";

const STATUS_TONE: Record<string, Tone> = {
  new: "info",
  confirmed: "info",
  preparing: "warning",
  ready: "success",
  dispatched: "info",
  delivered: "success",
  completed: "success",
  cancelled: "danger",
  returned: "neutral",
};

export function statusTone(status: string): Tone {
  return STATUS_TONE[status] ?? "neutral";
}

/** Badge classes (border+tint+text) for a status tone. Calm by default; only
 *  danger/warning/success carry saturated meaning. */
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

// ── Timer tone (urgency of the elapsed clock) ──────────────────────────────

export type TimerTone = "ok" | "warning" | "late" | "muted";

export function timerTone(timerClass: OrderTimerClass): TimerTone {
  if (timerClass === "timer-urgent") return "late";
  if (timerClass === "timer-warning") return "warning";
  if (timerClass === "timer-muted") return "muted";
  return "ok";
}

/** Tonal chip classes for the live timer. */
export function timerChip(tone: TimerTone): string {
  switch (tone) {
    case "late":
      return "border-red-500/40 bg-red-500/10 text-red-700 dark:text-red-300";
    case "warning":
      return "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300";
    case "muted":
      return "border-transparent bg-transparent text-muted-foreground";
    default:
      return "border-border bg-muted text-muted-foreground";
  }
}

// ── Icon vocabulary ────────────────────────────────────────────────────────

/** Map the projection's Material-Symbol ligatures (channel + fulfillment) onto
 *  this surface's lucide vocabulary. The backend projection is surface-agnostic
 *  (it also feeds the Admin queue); owning the translation here keeps it that way. */
const MATERIAL_TO_LUCIDE: Record<string, string> = {
  language: "globe",
  chat: "message-circle",
  fastfood: "utensils-crossed",
  storefront: "store",
  shopping_bag: "shopping-bag",
  local_shipping: "bike",
  store: "store",
  restaurant: "utensils",
  takeout_dining: "shopping-bag",
  pedal_bike: "bike",
  two_wheeler: "bike",
};

export function lucideIcon(name: string): string {
  return MATERIAL_TO_LUCIDE[name] || name || "circle";
}

/** Split an order ref into the repetitive {channel-date-} prefix and the short
 *  CODE the operator actually calls (the suffix after the last hyphen). */
export function splitRef(ref: string): { prefix: string; code: string } {
  const i = ref.lastIndexOf("-");
  if (i < 0) return { prefix: "", code: ref };
  return { prefix: ref.slice(0, i + 1), code: ref.slice(i + 1) };
}

/** Elapsed seconds → compact label. Seconds only in the first minute, then whole
 *  minutes, then "1h 5m" — calmer and glanceable. */
export function elapsedLabel(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  return m % 60 ? `${h}h ${m % 60}m` : `${h}h`;
}

// ── Zones (Entrada / Preparo / Saída) ──────────────────────────────────────

export interface ZoneView {
  key: "entrada" | "preparo" | "saida";
  title: string;
  subtitle: string;
  icon: string;
  cards: OrderCardProjection[];
  count: number;
}

/** Group the two-zone queue projection into the three action columns the board
 *  renders. Saída merges retirada + delivery (ready) + delivery-in-transit. */
export function zonesView(queue: TwoZoneQueueProjection): ZoneView[] {
  const saida = [
    ...queue.saida_retirada,
    ...queue.saida_delivery,
    ...queue.saida_delivery_transit,
  ];
  return [
    {
      key: "entrada",
      title: "Entrada",
      subtitle: "Novos — confirmar ou recusar",
      icon: "lucide:inbox",
      cards: queue.entrada,
      count: queue.entrada.length,
    },
    {
      key: "preparo",
      title: "Preparo",
      subtitle: "Confirmados e em preparo",
      icon: "lucide:cooking-pot",
      cards: queue.preparo,
      count: queue.preparo.length,
    },
    {
      key: "saida",
      title: "Saída",
      subtitle: "Retirada, coleta e entrega",
      icon: "lucide:package-check",
      cards: saida,
      count: saida.length,
    },
  ];
}

// ── Action affordances ─────────────────────────────────────────────────────

export type AffordanceRef = "confirm" | "advance" | "reject" | "settle_cash";

export interface Affordance {
  ref: AffordanceRef;
  label: string;
  icon: string;
  priority: "primary" | "secondary" | "danger";
  /** Needs a typed reason/amount → the surface opens a small dialog first. */
  needsInput: boolean;
}

/** The actions a card offers, derived from the projection's pre-resolved flags.
 *  Order = visual priority (primary first). Mirrors the Admin action cell. */
export function cardAffordances(card: OrderCardProjection): Affordance[] {
  const out: Affordance[] = [];
  if (card.can_confirm) {
    out.push({ ref: "confirm", label: "Confirmar", icon: "lucide:check", priority: "primary", needsInput: false });
  } else if (card.can_advance && card.next_action_label) {
    out.push({ ref: "advance", label: card.next_action_label, icon: "lucide:arrow-right", priority: "primary", needsInput: false });
  }
  if (card.can_settle_delivery_cash) {
    out.push({ ref: "settle_cash", label: "Acerto dinheiro", icon: "lucide:banknote", priority: "secondary", needsInput: true });
  }
  if (card.can_confirm) {
    out.push({ ref: "reject", label: "Recusar", icon: "lucide:x", priority: "danger", needsInput: true });
  }
  return out;
}

/** Filter cards by a free-text query over ref, customer and items summary. */
export function matchesQuery(card: OrderCardProjection, rawQuery: string): boolean {
  const q = rawQuery.trim().toLowerCase();
  if (!q) return true;
  return [card.ref, card.customer_name, card.items_summary].join(" ").toLowerCase().includes(q);
}
