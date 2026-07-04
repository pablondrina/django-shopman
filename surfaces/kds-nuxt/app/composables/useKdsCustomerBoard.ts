// Customer pickup board read-side (Arc 4). Public endpoint (no auth) —
// GET /api/v1/backstage/kds/cliente/ → orders split into preparing / ready, with
// privacy-safe refs only. Polls every 10s (mirrors the HTMX board); SSE on the
// orders channel is best-effort same-origin (prod), poll carries dev.
import type { KDSCustomerStatusProjection, KDSCustomerStatusResponse } from "~/types/kds";

export function useKdsCustomerBoard() {
  const config = useRuntimeConfig();
  const { data, pending, error, refresh } = useFetch<KDSCustomerStatusResponse>(
    "/api/v1/backstage/kds/cliente/",
    { key: "kds-customer-board" },
  );
  const status = computed<KDSCustomerStatusProjection | null>(() => data.value?.status ?? null);

  let pollTimer: ReturnType<typeof setInterval> | null = null;
  let source: EventSource | null = null;

  function connectSse() {
    if (source) return;
    const base = String(config.public.djangoPublicBaseUrl || "").replace(/\/$/, "");
    if (base && new URL(base).origin !== window.location.origin) return; // dev cross-origin → poll
    try {
      source = new EventSource(`${base}/gestor/events/orders/`, { withCredentials: true });
      ["message", "backstage-orders-update"].forEach((name) => source!.addEventListener(name, () => refresh()));
      source.onerror = () => { /* auto-reconnects; poll covers gaps */ };
    } catch {
      source = null;
    }
  }

  onMounted(() => {
    pollTimer = setInterval(() => refresh(), 10_000);
    connectSse();
  });
  onBeforeUnmount(() => {
    if (pollTimer) clearInterval(pollTimer);
    if (source) { source.close(); source = null; }
  });

  return { status, pending, error, refresh };
}
