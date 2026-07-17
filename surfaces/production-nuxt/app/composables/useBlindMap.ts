// Mapa código-cego ↔ preparo — SÓ na página /reports (persona GESTOR).
// GET /api/v1/backstage/production/weighing/blind-map/ para a data escolhida.
// As telas de chão (mise-en-place, board) são CEGAS por design: as etiquetas
// circulam apenas com o código do dia, e quem correlaciona é esta visão de
// gestor (gated por backstage.view_production_reports no backend).
import type { Ref } from "vue";
import type { ProductionBlindMapResponse } from "~/types/production";

export function useBlindMap(selectedDate: Ref<string>) {
  const { data, pending, error, refresh } = useFetch<ProductionBlindMapResponse>(
    "/api/v1/backstage/production/weighing/blind-map/",
    {
      key: "production-blind-map",
      server: true,
      query: computed(() => ({ date: selectedDate.value })),
    },
  );

  const blindMap = computed(() => data.value?.blind_map ?? null);
  const rows = computed(() => blindMap.value?.rows ?? []);

  return { blindMap, rows, pending, error, refresh };
}
