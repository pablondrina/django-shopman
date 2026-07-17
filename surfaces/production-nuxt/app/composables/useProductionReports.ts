// Relatórios de produção — read-side da página /reports (persona GESTOR).
// GET /api/v1/backstage/production/reports/ com os filtros da tela; o payload
// traz as três visões de uma vez (histórico, produtividade por operador e
// desperdício por ficha) + as opções de filtro (fichas/postos). O CSV NÃO passa
// por aqui: é um `<a href>` direto ao endpoint com `format=csv` (reportsCsvUrl).
// 403 é um estado LEGÍTIMO (operador de chão sem a perm fina de gestor) — a
// página o trata com calma; por isso este fetch não aciona operatorSessionOnError.
import type { Ref } from "vue";
import type { ProductionReportsResponse } from "~/types/production";
import {
  type ReportFiltersQuery,
  reportsCsvUrl,
  reportsQuery,
} from "~/presentation/reports";

export function useProductionReports(filters: Ref<ReportFiltersQuery>) {
  const { data, pending, error, refresh } = useFetch<ProductionReportsResponse>(
    "/api/v1/backstage/production/reports/",
    {
      key: "production-reports",
      server: true,
      query: computed(() => reportsQuery(filters.value)),
    },
  );

  const reports = computed(() => data.value?.reports ?? null);
  const historyRows = computed(() => reports.value?.history_rows ?? []);
  const operatorRows = computed(() => reports.value?.operator_rows ?? []);
  const wasteRows = computed(() => reports.value?.waste_rows ?? []);
  const availableRecipes = computed(() => reports.value?.available_recipes ?? []);
  const availablePositions = computed(
    () => reports.value?.available_positions ?? [],
  );
  const forbidden = computed(() => httpError(error.value).status === 403);
  const csvUrl = computed(() => reportsCsvUrl(filters.value));

  return {
    reports,
    historyRows,
    operatorRows,
    wasteRows,
    availableRecipes,
    availablePositions,
    forbidden,
    csvUrl,
    pending,
    error,
    refresh,
  };
}
