// Painel do Broadcast — leitura do board + as decisões do card.
//
// ADR-016 (SSE-first): o push do canal pessoal (`/sse/notifications`) só avisa
// que chegou coisa nova; a VERDADE é sempre o refetch do board. O poll fica
// como rede de segurança em cadência calma.
import type { BoardResponse, BroadcastPost, PostEdits } from "~/types/broadcast";

const POLL_MS = 60_000;

export function useBroadcastBoard() {
  const { data, refresh, pending, error } = useFetch<BoardResponse>(
    "/api/v1/backstage/broadcast/",
    { key: "broadcast-board", server: true },
  );

  const board = computed(() => data.value?.board);
  const pendingPosts = computed<BroadcastPost[]>(() => board.value?.pending ?? []);
  const recentPosts = computed<BroadcastPost[]>(() => board.value?.recent ?? []);
  const stats = computed(() => board.value?.stats);

  let pollTimer: ReturnType<typeof setInterval> | null = null;
  onMounted(() => {
    pollTimer = setInterval(() => refresh(), POLL_MS);
  });
  onBeforeUnmount(() => {
    if (pollTimer) clearInterval(pollTimer);
  });

  // Push pessoal: post novo pedindo revisão chega aqui antes do poll.
  useUserNotifications(() => refresh());

  async function approve(pk: number, edits: PostEdits = {}): Promise<boolean> {
    return decide(pk, "approve", edits, edits.publish_at ? "Post agendado." : "Post publicado.");
  }

  async function discard(pk: number): Promise<boolean> {
    return decide(pk, "discard", {}, "Post descartado.");
  }

  async function decide(
    pk: number,
    action: "approve" | "discard",
    body: PostEdits,
    okMessage: string,
  ): Promise<boolean> {
    try {
      await $fetch(`/api/v1/backstage/broadcast/posts/${pk}/${action}/`, {
        method: "POST",
        body,
      });
      useSonner.success(okMessage);
      await refresh();
      return true;
    } catch (err) {
      useSonner.error(httpErrorMessage(err, "Não foi possível concluir. Tente de novo."));
      // Refetch mesmo no erro: quem falhou por expiração precisa sumir do painel.
      await refresh();
      return false;
    }
  }

  async function saveDraft(pk: number, edits: PostEdits): Promise<boolean> {
    try {
      await $fetch(`/api/v1/backstage/broadcast/posts/${pk}/`, { method: "PATCH", body: edits });
      useSonner.success("Rascunho salvo.");
      await refresh();
      return true;
    } catch (err) {
      useSonner.error(httpErrorMessage(err, "Não foi possível salvar."));
      return false;
    }
  }

  return {
    board,
    pendingPosts,
    recentPosts,
    stats,
    loading: pending,
    error,
    refresh,
    approve,
    discard,
    saveDraft,
  };
}
