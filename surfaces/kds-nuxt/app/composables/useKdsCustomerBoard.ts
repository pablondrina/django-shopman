// Customer pickup board read-side (Arc 4). Public endpoint (no auth) —
// GET /api/v1/backstage/kds/cliente/ → orders split into preparing / ready, with
// privacy-safe refs only. Polls every 10s (mirrors the HTMX board); SSE
// same-origin via BFF (/sse/orders) is best-effort, poll covers the gaps.
import type {
  KDSCustomerStatusProjection,
  KDSCustomerStatusResponse,
} from "~/types/kds";

export function useKdsCustomerBoard() {
  const config = useRuntimeConfig();
  const { data, pending, error, refresh } = useFetch<KDSCustomerStatusResponse>(
    "/api/v1/backstage/kds/cliente/",
    { key: "kds-customer-board" },
  );
  const status = computed<KDSCustomerStatusProjection | null>(
    () => data.value?.status ?? null,
  );

  // `realtime` diz HONESTAMENTE se o painel está recebendo push (SSE) ou só fazendo poll —
  // a bolinha verde "ao vivo" só acende quando o EventSource conecta de fato (onopen).
  const realtime = ref<"connecting" | "live" | "polling">("polling");
  let pollTimer: ReturnType<typeof setInterval> | null = null;
  let source: EventSource | null = null;

  function connectSse() {
    if (source) return;
    // Same-origin sempre: o BFF (server/routes/sse/orders.ts) faz streaming do
    // eventstream do Django, em dev e em prod — nada de gate por origem.
    const url = ssePath("/sse/orders", config.app.baseURL);
    try {
      realtime.value = "connecting";
      source = new EventSource(url, {
        withCredentials: true,
      });
      ["message", "backstage-orders-update"].forEach((name) =>
        source!.addEventListener(name, () => refresh()),
      );
      source.onopen = () => {
        realtime.value = "live";
      };
      // Erro/desconexão → cai pro poll; o EventSource auto-reconecta e o onopen volta a "live".
      source.onerror = () => {
        realtime.value = "polling";
      };
    } catch {
      source = null;
      realtime.value = "polling";
    }
  }

  onMounted(() => {
    pollTimer = setInterval(() => refresh(), 10_000);
    connectSse();
  });
  onBeforeUnmount(() => {
    if (pollTimer) clearInterval(pollTimer);
    if (source) {
      source.close();
      source = null;
    }
  });

  return { status, realtime, pending, error, refresh };
}
