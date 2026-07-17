// Gestão do dia — KPIs de produção (rendimento médio, capacidade %, atrasos).
// GET /api/v1/backstage/production/management/ para a data escolhida; vive na
// página /reports (persona GESTOR, perm fina backstage.view_production_reports).
import type { Ref } from "vue";
import type { ProductionManagementResponse } from "~/types/production";

export function useProductionManagement(selectedDate: Ref<string>) {
  const { data, pending, error, refresh } =
    useFetch<ProductionManagementResponse>(
      "/api/v1/backstage/production/management/",
      {
        key: "production-management",
        server: true,
        query: computed(() => ({ date: selectedDate.value })),
      },
    );

  const management = computed(() => data.value?.management ?? null);
  const lateOrders = computed(() => management.value?.late_orders ?? []);
  const forbidden = computed(() => httpError(error.value).status === 403);

  return { management, lateOrders, forbidden, pending, error, refresh };
}
