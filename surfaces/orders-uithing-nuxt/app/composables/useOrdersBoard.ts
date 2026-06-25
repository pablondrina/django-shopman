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

  async function act(ref_: string, action: string, body?: Record<string, unknown>): Promise<boolean> {
    if (busy.value.has(ref_)) return false;
    busy.value = new Set(busy.value).add(ref_);
    try {
      await $fetch(`/api/v1/backstage/orders/${encodeURIComponent(ref_)}/${action}/`, {
        method: "POST",
        body: body ?? {},
      });
      await refresh();
      return true;
    } catch (err: any) {
      useSonner.error(err?.data?.detail || "Falha na ação. Tente de novo.");
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

  return { queue, zones, totalCount, pending, error, refresh, isBusy, confirm, advance, reject, settleCash };
}
