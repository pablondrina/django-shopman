<script setup lang="ts">
// Um post, sozinho na tela — destino do link da notificação acionável
// (``UserNotification.action_url`` = /broadcast/posts/<pk>/).
//
// O gestor recebe o aviso no celular, toca e cai direto na decisão. Mesmo card
// do painel: uma única forma de decidir, um único lugar para acertar.
import type { BroadcastPost, PostEdits } from "~/types/broadcast";

const route = useRoute();
const pk = computed(() => Number(route.params.id));

const { data, refresh, pending, error } = await useFetch<{ post: BroadcastPost }>(
  () => `/api/v1/backstage/broadcast/posts/${pk.value}/`,
  { key: () => `broadcast-post-${pk.value}` },
);
const { platforms } = useBroadcastRules();

const post = computed(() => data.value?.post);
const busy = ref(false);
const confirmingDiscard = ref(false);

async function decide(action: "approve" | "discard", body: PostEdits = {}) {
  busy.value = true;
  try {
    await $fetch(`/api/v1/backstage/broadcast/posts/${pk.value}/${action}/`, {
      method: "POST",
      body,
    });
    useSonner.success(
      action === "discard" ? "Post descartado."
      : body.publish_at ? "Post agendado."
      : "Post publicado.",
    );
    await navigateTo("/");
  } catch (err) {
    useSonner.error(httpErrorMessage(err, "Não foi possível concluir. Tente de novo."));
    await refresh();
  } finally {
    busy.value = false;
  }
}

useHead({ title: "Post · Broadcast" });
</script>

<template>
  <main class="mx-auto w-full max-w-2xl flex-1 px-4 py-6">
    <NuxtLink
      to="/"
      class="mb-4 inline-flex items-center gap-1.5 text-sm text-muted-foreground transition hover:text-foreground"
    >
      <Icon name="lucide:arrow-left" class="size-4" />
      Voltar ao painel
    </NuxtLink>

    <div v-if="pending && !post" class="h-64 animate-pulse rounded-xl bg-muted" aria-busy="true"></div>

    <div
      v-else-if="error || !post"
      class="rounded-xl border border-dashed border-border bg-card/50 px-6 py-10 text-center"
    >
      <Icon name="lucide:search-x" class="mx-auto size-8 text-muted-foreground" />
      <p class="mt-2 font-semibold">Não encontramos este post</p>
      <p class="mt-1 text-sm text-muted-foreground">
        Ele pode ter expirado ou já ter sido decidido por outra pessoa.
      </p>
      <NuxtLink
        to="/"
        class="mt-3 inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm font-medium transition hover:bg-muted"
      >
        Ver o painel
      </NuxtLink>
    </div>

    <template v-else>
      <!-- Já decidido: mostra o estado em vez de oferecer botões que não valem mais -->
      <div
        v-if="post.status !== 'pending_review'"
        class="mb-4 rounded-lg border border-border bg-muted/40 px-4 py-3 text-sm"
      >
        <p class="font-semibold">Este post já foi decidido.</p>
        <p class="mt-0.5 text-muted-foreground">
          Situação: {{ post.status_label }}<template v-if="post.approved_by">
            · por {{ post.approved_by }}</template>
        </p>
      </div>

      <BroadcastPostCard
        v-if="post.status === 'pending_review'"
        :post="post"
        :platform-options="platforms"
        :busy="busy"
        @approve="(_, edits) => decide('approve', edits)"
        @discard="confirmingDiscard = true"
      />

      <article v-else class="rounded-xl border border-border bg-card p-4">
        <p class="whitespace-pre-line text-sm">{{ post.body }}</p>
      </article>
    </template>

    <UiDialog :open="confirmingDiscard" @update:open="(v) => (confirmingDiscard = v)">
      <UiDialogContent class="sm:max-w-md">
        <UiDialogHeader>
          <UiDialogTitle>Descartar este post?</UiDialogTitle>
          <UiDialogDescription>
            Ele não vai para nenhuma plataforma e não volta para a fila.
          </UiDialogDescription>
        </UiDialogHeader>
        <UiDialogFooter>
          <button
            type="button"
            class="rounded-md border border-border px-3 py-2 text-sm font-medium transition hover:bg-muted"
            @click="confirmingDiscard = false"
          >
            Manter na fila
          </button>
          <button
            type="button"
            class="rounded-md bg-destructive px-3 py-2 text-sm font-semibold text-destructive-foreground transition hover:bg-destructive/90"
            @click="confirmingDiscard = false; decide('discard')"
          >
            Descartar
          </button>
        </UiDialogFooter>
      </UiDialogContent>
    </UiDialog>
  </main>
</template>
