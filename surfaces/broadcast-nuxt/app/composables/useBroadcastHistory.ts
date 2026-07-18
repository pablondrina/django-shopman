// Histórico — o que já saiu, com o resultado de cada plataforma.
//
// Sem poll: histórico é passado, não muda sozinho na tela. Quem quer o agora
// olha o painel.
import type { HistoryResponse } from "~/types/broadcast";

export function useBroadcastHistory() {
  const { data, refresh, pending, error } = useFetch<HistoryResponse>(
    "/api/v1/backstage/broadcast/history/",
    { key: "broadcast-history", server: true },
  );

  return {
    posts: computed(() => data.value?.posts ?? []),
    loading: pending,
    error,
    refresh,
  };
}
