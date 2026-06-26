// Order board read-side. Single source for the live queue:
//   - useFetch the canonical two-zone projection (GET /api/v1/backstage/orders/);
//   - poll every 30s as a robust fallback (mirrors the Admin queue `every 30s`);
//   - SSE realtime: EventSource on /gestor/events/orders/ → refresh on push.
// Writes go through the django proxy (CSRF handled there) and reconcile via refresh.
// SSE/poll are client-only (EventSource is a browser API).
import type { OrderQueueResponse, TwoZoneQueueProjection } from "~/types/orders";
import { zonesView, type ZoneView } from "~/presentation/board";

export function useOrdersBoard() {
  const config = useRuntimeConfig();
  const path = "/api/v1/backstage/orders/";

  // useFetch (not useAsyncData) so the SSR payload transfers reliably (POS gotcha).
  const { data, pending, error, refresh } = useFetch<OrderQueueResponse>(path, {
    key: "orders-queue",
    server: true,
  });

  const queue = computed<TwoZoneQueueProjection | null>(() => data.value?.queue ?? null);
  const zones = computed<ZoneView[]>(() => (queue.value ? zonesView(queue.value) : []));
  const totalCount = computed(() => queue.value?.total_count ?? 0);

  // Realtime + polling (client only).
  let pollTimer: ReturnType<typeof setInterval> | null = null;
  let source: EventSource | null = null;

  function connectSse() {
    if (source) return;
    const base = String(config.public.djangoPublicBaseUrl || "").replace(/\/$/, "");
    // EventSource needs same-origin. In prod the Gestor is served on its own host
    // proxying Django, so it connects; in dev it's a different origin (:3004 vs
    // Django :8000) → skip and let the 30s poll carry realtime.
    if (!base || new URL(base).origin !== window.location.origin) return;
    const url = `${base}/gestor/events/orders/`;
    try {
      source = new EventSource(url, { withCredentials: true });
      const onPush = () => refresh();
      ["message", "backstage-orders-update"].forEach((name) => source!.addEventListener(name, onPush));
      source.onerror = () => { /* EventSource auto-reconnects; poll covers gaps. */ };
    } catch {
      source = null; // SSE unavailable → polling carries it.
    }
  }

  onMounted(() => {
    pollTimer = setInterval(() => refresh(), 30_000);
    connectSse();
  });
  onBeforeUnmount(() => {
    if (pollTimer) clearInterval(pollTimer);
    if (source) { source.close(); source = null; }
  });

  // ── write-side: per-ref in-flight guard + reconcile ──────────────────────
  // Order actions move a card across zones, so an optimistic local move is fragile;
  // instead we mark the ref busy (disables its buttons), POST, then refresh to the
  // server truth. Local + fast, so the refresh feels instant.
  const busy = ref<Set<string>>(new Set());
  const isBusy = (ref_: string) => busy.value.has(ref_);

  // Per-ref action error: the backend's specific, operator-facing reason
  // (e.g. "Pagamento ainda não foi confirmado…"). Kept inline on the card/row —
  // a toast is transient and easy to miss; this persists until dismissed, the
  // next attempt, or a refresh that drops the card.
  const actionErrors = ref<Map<string, string>>(new Map());
  const actionError = (ref_: string) => actionErrors.value.get(ref_) ?? "";
  function setActionError(ref_: string, message: string) {
    const next = new Map(actionErrors.value);
    next.set(ref_, message);
    actionErrors.value = next;
  }
  function clearActionError(ref_: string) {
    if (!actionErrors.value.has(ref_)) return;
    const next = new Map(actionErrors.value);
    next.delete(ref_);
    actionErrors.value = next;
  }

  async function act(ref_: string, action: string, body?: Record<string, unknown>): Promise<boolean> {
    if (busy.value.has(ref_)) return false;
    clearActionError(ref_); // a fresh attempt clears the previous reason
    busy.value = new Set(busy.value).add(ref_);
    try {
      await $fetch(`/api/v1/backstage/orders/${encodeURIComponent(ref_)}/${action}/`, {
        method: "POST",
        body: body ?? {},
      });
      await refresh();
      return true;
    } catch (err: any) {
      const message = err?.data?.detail || "Falha na ação. Tente de novo.";
      setActionError(ref_, message);
      useSonner.error(message);
      return false;
    } finally {
      const next = new Set(busy.value);
      next.delete(ref_);
      busy.value = next;
    }
  }

  const confirm = (ref_: string) => act(ref_, "confirm");
  const advance = (ref_: string) => act(ref_, "advance");
  const reject = (ref_: string, reason: string) => act(ref_, "reject", { reason });
  const settleCash = (ref_: string, amount: string) => act(ref_, "settle-delivery-cash", { amount });
  const assign = (ref_: string) => act(ref_, "assign");
  const unassign = (ref_: string) => act(ref_, "unassign");

  // Bulk action over many refs: fire all POSTs, capture per-ref failures inline,
  // then refresh once (not per order). Returns how many failed.
  async function actMany(refs: string[], action: string): Promise<number> {
    const targets = refs.filter((r) => !busy.value.has(r));
    if (!targets.length) return 0;
    busy.value = new Set([...busy.value, ...targets]);
    targets.forEach((r) => clearActionError(r));
    let failures = 0;
    await Promise.all(
      targets.map(async (r) => {
        try {
          await $fetch(`/api/v1/backstage/orders/${encodeURIComponent(r)}/${action}/`, { method: "POST", body: {} });
        } catch (err: any) {
          failures += 1;
          setActionError(r, err?.data?.detail || "Falha na ação.");
        }
      }),
    );
    const next = new Set(busy.value);
    targets.forEach((r) => next.delete(r));
    busy.value = next;
    await refresh();
    if (failures) useSonner.error(`${failures} pedido(s) não puderam ser atualizados.`);
    return failures;
  }
  const confirmMany = (refs: string[]) => actMany(refs, "confirm");
  const advanceMany = (refs: string[]) => actMany(refs, "advance");

  return { queue, zones, totalCount, pending, error, refresh, isBusy, actionError, clearActionError, confirm, advance, reject, settleCash, assign, unassign, confirmMany, advanceMany };
}
