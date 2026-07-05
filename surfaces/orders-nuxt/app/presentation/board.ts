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
 *  minutes, then "1h 5m", then days ("4d 23h") — calmer and glanceable. Capar em
 *  dias evita o "119h" que grita sem informar. */
export function elapsedLabel(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return m % 60 ? `${h}h ${m % 60}m` : `${h}h`;
  const d = Math.floor(h / 24);
  return h % 24 ? `${d}d ${h % 24}h` : `${d}d`;
}

/**
 * Countdown regressivo até o prazo da confirmação otimista.
 * Retorna "" quando não há prazo; "0:00" quando já venceu; senão "M:SS".
 * Puro e testável — o card passa um `nowMs` que tica no cliente.
 */
export function confirmationRemainingLabel(deadlineIso: string, nowMs: number): string {
  if (!deadlineIso) return "";
  const deadlineMs = Date.parse(deadlineIso);
  if (Number.isNaN(deadlineMs)) return "";
  const left = Math.max(0, Math.round((deadlineMs - nowMs) / 1000));
  const m = Math.floor(left / 60);
  return `${m}:${String(left % 60).padStart(2, "0")}`;
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

// ── Triage: channel filter, sort, view-mode (Arc 1) ─────────────────────────

/** Friendly channel labels. Unknown channels fall back to a capitalised ref so
 *  a new channel never renders blank. */
const CHANNEL_LABEL: Record<string, string> = {
  web: "Loja online",
  whatsapp: "WhatsApp",
  ifood: "iFood",
  pdv: "PDV",
  pos: "PDV",
};

export function channelLabel(ref: string): string {
  if (CHANNEL_LABEL[ref]) return CHANNEL_LABEL[ref];
  return ref ? ref.charAt(0).toUpperCase() + ref.slice(1) : "—";
}

export interface ChannelOption {
  ref: string;
  label: string;
  count: number;
}

/** Distinct channels present in the queue, with counts, for the filter control.
 *  Derived from the data so the control only ever offers channels that exist. */
export function channelOptions(cards: OrderCardProjection[]): ChannelOption[] {
  const counts = new Map<string, number>();
  for (const c of cards) counts.set(c.channel_ref, (counts.get(c.channel_ref) ?? 0) + 1);
  return [...counts.entries()]
    .map(([ref, count]) => ({ ref, label: channelLabel(ref), count }))
    .sort((a, b) => a.label.localeCompare(b.label, "pt-BR"));
}

/** `"all"` (or empty) matches everything; otherwise exact channel match. */
export function matchesChannel(card: OrderCardProjection, channel: string): boolean {
  return !channel || channel === "all" || card.channel_ref === channel;
}

// Fulfillment é o eixo que muda o FLUXO (rota vs balcão) — por isso é filtro de
// primeira classe no board, ao lado do canal (que é só a origem).
export type FulfillmentFilter = "all" | "delivery" | "pickup";

/** `"all"` matches everything; senão bate o fulfillment_type do card. */
export function matchesFulfillment(card: OrderCardProjection, mode: FulfillmentFilter): boolean {
  return mode === "all" || card.fulfillment_type === mode;
}

export type RealtimeState = "connecting" | "live" | "polling";

export interface RealtimeIndicatorView {
  label: string;
  /** true SÓ quando o SSE está aberto — a bolinha verde não mente. */
  live: boolean;
  dotClass: string;
  title: string;
}

/**
 * Como apresentar o estado de realtime do board (honestidade da resiliência): "ao vivo"
 * (verde) só com SSE aberto; caso contrário um sinal neutro de que o board ainda atualiza
 * sozinho, a cada 30s (poll) — nunca prometendo tempo-real que não há.
 */
export function realtimeIndicator(state: RealtimeState): RealtimeIndicatorView {
  if (state === "live") {
    return { label: "Ao vivo", live: true, dotClass: "bg-green-500", title: "Recebendo atualizações em tempo real" };
  }
  if (state === "connecting") {
    return { label: "Conectando…", live: false, dotClass: "bg-amber-500", title: "Estabelecendo tempo real; enquanto isso, atualiza a cada 30s" };
  }
  return { label: "Atualização automática", live: false, dotClass: "bg-muted-foreground/40", title: "Sem tempo real; o board atualiza sozinho a cada 30s" };
}

/** Contagem por fulfillment na fila corrente (para os selos dos filtros). */
export function fulfillmentCounts(cards: OrderCardProjection[]): { delivery: number; pickup: number } {
  let delivery = 0;
  let pickup = 0;
  for (const c of cards) { if (c.fulfillment_type === "delivery") delivery++; else pickup++; }
  return { delivery, pickup };
}

export type SortKey = "arrival" | "urgency" | "recent";

export interface SortOption {
  key: SortKey;
  label: string;
}

export const SORT_OPTIONS: SortOption[] = [
  { key: "arrival", label: "Chegada" },
  { key: "urgency", label: "Urgência" },
  { key: "recent", label: "Mais recentes" },
];

/** Order cards for display. `arrival` keeps the projection's own order (oldest
 *  first, as the backend serves it); `urgency` puts the longest-waiting on top;
 *  `recent` puts the newest arrivals on top. Pure — never mutates the input. */
export function sortCards(cards: OrderCardProjection[], key: SortKey): OrderCardProjection[] {
  const out = [...cards];
  if (key === "urgency") {
    out.sort((a, b) => b.elapsed_seconds - a.elapsed_seconds);
  } else if (key === "recent") {
    out.sort((a, b) => b.created_at_iso.localeCompare(a.created_at_iso));
  }
  return out;
}

/** Apply channel filter + free-text query + sort to one zone's cards. The board
 *  and the table both render through this, so they always agree. */
export function triageCards(
  cards: OrderCardProjection[],
  opts: { query: string; channel: string; sort: SortKey; fulfillment?: FulfillmentFilter },
): OrderCardProjection[] {
  const fulfillment = opts.fulfillment ?? "all";
  const filtered = cards.filter(
    (c) => matchesChannel(c, opts.channel) && matchesFulfillment(c, fulfillment) && matchesQuery(c, opts.query),
  );
  return sortCards(filtered, opts.sort);
}

export type ViewMode = "board" | "table";

export interface FlatRow {
  card: OrderCardProjection;
  zoneKey: ZoneView["key"];
  zoneTitle: string;
}

/** Flatten the three zones into one list (with the zone each card belongs to)
 *  for the dense table view. Preserves zone order, then per-zone order. */
export function flattenZones(zones: ZoneView[]): FlatRow[] {
  return zones.flatMap((z) => z.cards.map((card) => ({ card, zoneKey: z.key, zoneTitle: z.title })));
}

/** Serialise the (already triaged) queue rows to CSV — the operator's "saída"
 *  for a shift handover or a quick print. Pure so the columns/escaping are
 *  testable; the page owns the download. */
export function rowsToCsv(rows: FlatRow[]): string {
  const header = ["Codigo", "Etapa", "Canal", "Cliente", "Itens", "Total", "Tempo", "Atendente"];
  const esc = (v: unknown) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  const body = rows.map((r) =>
    [
      r.card.ref,
      r.zoneTitle,
      channelLabel(r.card.channel_ref),
      r.card.customer_name,
      r.card.items_summary,
      r.card.total_display,
      elapsedLabel(r.card.elapsed_seconds),
      r.card.assigned_operator,
    ]
      .map(esc)
      .join(","),
  );
  return [header.map(esc).join(","), ...body].join("\n");
}

// ── Keyboard shortcuts (Arc 3) ──────────────────────────────────────────────

export type BoardShortcut =
  | "focus-search"
  | "refresh"
  | "toggle-view"
  | "cycle-sort"
  | "clear-filters";

/** Map a keydown's `key` to a board shortcut, or null if none. Pure so the
 *  mapping is testable; the page owns the side effects (focus, refresh, …) and
 *  the "ignore while typing" guard. */
export function resolveShortcut(key: string): BoardShortcut | null {
  switch (key) {
    case "/":
      return "focus-search";
    case "r":
    case "R":
      return "refresh";
    case "v":
    case "V":
      return "toggle-view";
    case "s":
    case "S":
      return "cycle-sort";
    case "Escape":
      return "clear-filters";
    default:
      return null;
  }
}

/** Cycle the sort key in the order the control lists them. */
export function nextSort(current: SortKey): SortKey {
  const i = SORT_OPTIONS.findIndex((o) => o.key === current);
  return SORT_OPTIONS[(i + 1) % SORT_OPTIONS.length]!.key;
}

// ── Bulk actions (Arc 4) ────────────────────────────────────────────────────

export type BulkAction = "confirm" | "advance";

/** Refs among the selected cards that can take the given bulk action right now,
 *  read from the projection's pre-resolved flags (the backend owns the gate, as
 *  always). Pure → the batch bar's enabled/count state is testable. */
export function bulkableRefs(
  cards: OrderCardProjection[],
  selected: ReadonlySet<string>,
  action: BulkAction,
): string[] {
  const can = action === "confirm" ? (c: OrderCardProjection) => c.can_confirm : (c: OrderCardProjection) => c.can_advance;
  return cards.filter((c) => selected.has(c.ref) && can(c)).map((c) => c.ref);
}
