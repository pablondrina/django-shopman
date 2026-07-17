// Sonda de acesso do gestor: decide se a entrada "Relatórios" aparece na nav.
// A permissão fina (backstage.view_production_reports) vive no backend; em vez
// de duplicar a regra aqui, a nav consulta a própria API (a mesma que a página
// /reports usa) — respondeu 200, o item aparece; 403 (operador de chão), some.
// Sondagem barata: o payload de gestão do dia é pequeno e o useFetch com key
// única deduplica entre as telas que renderizam o cabeçalho.
import type { ProductionManagementResponse } from "~/types/production";

export function useReportsAccess() {
  const { data, error } = useFetch<ProductionManagementResponse>(
    "/api/v1/backstage/production/management/",
    { key: "production-reports-access", server: true },
  );

  const allowed = computed(
    () => !!data.value?.management && !error.value,
  );

  return { allowed };
}
