// O PAINEL — read-side da previsão da produção (estilo aeroporto).
// GET /api/v1/backstage/production/forecast/ e poll de 30s: o painel fica
// aberto o dia inteiro numa tela da loja, então ele se atualiza sozinho.
import type { ProductionForecastProjection, ProductionForecastResponse } from "~/types/production";

export function useProductionForecast() {
  const path = "/api/v1/backstage/production/forecast/";
  const selectedDate = ref(todayISO());

  const { data, pending, error, refresh } = useFetch<ProductionForecastResponse>(path, {
    key: "production-forecast",
    server: true,
    query: computed(() => ({ date: selectedDate.value })),
    onResponseError({ response }) {
      if (response.status === 401 || response.status === 403) refreshNuxtData("operator-session");
    },
  });

  const forecast = computed<ProductionForecastProjection | null>(() => data.value?.forecast ?? null);
  const rows = computed(() => forecast.value?.rows ?? []);

  useAdaptivePoll(refresh, () => 30_000);

  return { forecast, rows, selectedDate, pending, error, refresh };
}

function todayISO(): string {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}
