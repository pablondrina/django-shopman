// Operator alerts read-side. Polls the active alerts + counts and exposes ack.
// The operator hub is the natural home for alerts (failed payments, low stock,
// stale orders…). Polling only (no SSE) — alerts are low-frequency.
import type { AlertProjection, AlertsResponse } from "~/types/production";

export function useAlerts() {
  const { data, refresh } = useFetch<AlertsResponse>("/api/v1/backstage/alerts/", {
    key: "operator-alerts",
    server: true,
  });

  const alerts = computed<AlertProjection[]>(() => data.value?.alerts ?? []);
  const activeCount = computed(() => data.value?.counts?.active ?? 0);
  const criticalCount = computed(() => data.value?.counts?.critical ?? 0);

  useAdaptivePoll(refresh, () => 60_000);

  async function ack(pk: number): Promise<void> {
    try {
      await $fetch(`/api/v1/backstage/alerts/${pk}/ack/`, { method: "POST", body: {} });
      await refresh();
    } catch (err) {
      useSonner.error(httpErrorMessage(err, "Falha ao reconhecer o alerta."));
    }
  }

  return { alerts, activeCount, criticalCount, refresh, ack };
}
