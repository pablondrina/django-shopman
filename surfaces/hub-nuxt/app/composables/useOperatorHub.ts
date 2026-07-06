import type { HubResponse, HubTileProjection, OperatorHubProjection } from "~/types/hub";

/**
 * Read-side da Central: um único fetch da projection do launcher (`{ hub }`) + as fatias
 * que a tela consome (tiles + nome do operador). Espelha o padrão `usePosTerminal` — SSR
 * pronta (reload cai na tela certa); erro (401) sobe o gate de login na shell.
 */
export async function useOperatorHub() {
  const apiPath = useHubApiPath();
  const requestHeaders = import.meta.server ? useRequestHeaders(["cookie"]) : undefined;

  const { data, pending, error, refresh } = await useFetch<HubResponse>(
    () => apiPath("/api/v1/backstage/hub/"),
    { credentials: "include", headers: requestHeaders },
  );

  const hub = computed<OperatorHubProjection | null>(() => data.value?.hub ?? null);
  const tiles = computed<HubTileProjection[]>(() => hub.value?.tiles ?? []);
  const operatorName = computed(() => hub.value?.operator_name ?? "");

  return { data, hub, tiles, operatorName, pending, error, refresh };
}
