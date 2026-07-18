<script setup lang="ts">
// Painel do Broadcast — a fila de decisões do gestor.
//
// Ordem deliberada: primeiro o que PEDE decisão (pendentes), depois o que já
// saiu. Números do dia por último: contexto, não protagonista.
import { audienceSummary, postOutcome, shortDateTime } from "~/presentation/broadcast";
import type { PostEdits } from "~/types/broadcast";

// Mesma leitura do histórico: sucesso PARCIAL não se disfarça de pendente.
// Se o Google saiu e o Instagram falhou, a linha precisa chamar atenção.
const OUTCOME_META = {
  published: { icon: "lucide:check-circle-2", class: "text-emerald-600" },
  partial: { icon: "lucide:alert-circle", class: "text-amber-600" },
  failed: { icon: "lucide:x-circle", class: "text-destructive" },
  pending: { icon: "lucide:clock", class: "text-muted-foreground" },
} as const;

const { pendingPosts, recentPosts, stats, loading, error, refresh, approve, discard } =
  useBroadcastBoard();
const { platforms } = useBroadcastRules();

const busyPk = ref<number | null>(null);
const discarding = ref<number | null>(null);

async function onApprove(pk: number, edits: PostEdits) {
  busyPk.value = pk;
  await approve(pk, edits);
  busyPk.value = null;
}

async function confirmDiscard() {
  const pk = discarding.value;
  if (pk === null) return;
  busyPk.value = pk;
  discarding.value = null;
  await discard(pk);
  busyPk.value = null;
}

useHead({ title: "Painel · Broadcast" });
</script>

<template>
  <main class="mx-auto w-full max-w-4xl flex-1 px-4 py-6">
    <div class="mb-5 flex items-center gap-3">
      <h1 class="text-xl font-bold">Painel</h1>
      <button
        type="button"
        class="ml-auto inline-flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-sm text-muted-foreground transition hover:bg-muted"
        @click="refresh()"
      >
        <Icon name="lucide:refresh-cw" class="size-3.5" />
        Atualizar
      </button>
    </div>

    <!-- Números do dia -->
    <section v-if="stats" class="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4" aria-label="Números de hoje">
      <div class="rounded-lg border border-border bg-card px-3 py-2.5">
        <p class="text-2xl font-bold">{{ stats.pending_count }}</p>
        <p class="text-xs text-muted-foreground">aguardando você</p>
      </div>
      <div class="rounded-lg border border-border bg-card px-3 py-2.5">
        <p class="text-2xl font-bold">{{ stats.published_today }}</p>
        <p class="text-xs text-muted-foreground">publicados hoje</p>
      </div>
      <div class="rounded-lg border border-border bg-card px-3 py-2.5">
        <p class="text-2xl font-bold">{{ stats.audience_reached_today }}</p>
        <p class="text-xs text-muted-foreground">clientes alcançados</p>
      </div>
      <div
        class="rounded-lg border px-3 py-2.5"
        :class="stats.failed_today > 0 ? 'border-destructive/40 bg-destructive/5' : 'border-border bg-card'"
      >
        <p class="text-2xl font-bold" :class="stats.failed_today > 0 ? 'text-destructive' : ''">
          {{ stats.failed_today }}
        </p>
        <p class="text-xs text-muted-foreground">falharam</p>
      </div>
    </section>

    <!-- Erro de carga: o painel não finge estar vazio quando não conseguiu ler -->
    <div
      v-if="error"
      class="mb-6 rounded-lg border border-destructive/40 bg-destructive/5 px-4 py-3 text-sm"
      role="alert"
    >
      <p class="font-semibold text-destructive">Não conseguimos carregar o painel.</p>
      <button type="button" class="mt-1 underline underline-offset-2" @click="refresh()">
        Tentar de novo
      </button>
    </div>

    <!-- Pendentes -->
    <section class="mb-8">
      <h2 class="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
        Aguardando decisão
      </h2>

      <div v-if="loading && pendingPosts.length === 0" class="space-y-3" aria-busy="true">
        <div v-for="n in 2" :key="n" class="h-48 animate-pulse rounded-xl bg-muted"></div>
      </div>

      <div
        v-else-if="pendingPosts.length === 0"
        class="rounded-xl border border-dashed border-border bg-card/50 px-6 py-10 text-center"
      >
        <Icon name="lucide:coffee" class="mx-auto size-8 text-muted-foreground" />
        <p class="mt-2 font-semibold">Nada esperando por você</p>
        <p class="mt-1 text-sm text-muted-foreground">
          Quando uma fornada terminar, o post aparece aqui para revisão.
        </p>
        <NuxtLink
          to="/rules"
          class="mt-3 inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm font-medium transition hover:bg-muted"
        >
          <Icon name="lucide:sliders-horizontal" class="size-4" />
          Ver as regras
        </NuxtLink>
      </div>

      <div v-else class="space-y-4">
        <BroadcastPostCard
          v-for="post in pendingPosts"
          :key="post.pk"
          :post="post"
          :platform-options="platforms"
          :busy="busyPk === post.pk"
          @approve="onApprove"
          @discard="(pk) => (discarding = pk)"
        />
      </div>
    </section>

    <!-- Publicados nas últimas 24h -->
    <section v-if="recentPosts.length > 0">
      <h2 class="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
        Últimas 24 horas
      </h2>
      <ul class="divide-y divide-border overflow-hidden rounded-xl border border-border bg-card">
        <li v-for="post in recentPosts" :key="post.pk" class="flex items-start gap-3 px-4 py-3">
          <Icon
            :name="OUTCOME_META[postOutcome(post.platform_results)].icon"
            class="mt-0.5 size-4 shrink-0"
            :class="OUTCOME_META[postOutcome(post.platform_results)].class"
          />
          <div class="min-w-0 flex-1">
            <p class="truncate text-sm">{{ post.body }}</p>
            <p class="mt-0.5 text-xs text-muted-foreground">
              {{ shortDateTime(post.published_at || post.created_at) }} ·
              {{ audienceSummary(post.audience) }}
            </p>
          </div>
        </li>
      </ul>
      <NuxtLink
        to="/history"
        class="mt-3 inline-flex items-center gap-1.5 text-sm text-muted-foreground underline underline-offset-2 hover:text-foreground"
      >
        Ver o histórico completo
        <Icon name="lucide:arrow-right" class="size-3.5" />
      </NuxtLink>
    </section>

    <!-- Descartar é irreversível: confirma antes -->
    <UiDialog :open="discarding !== null" @update:open="(v) => { if (!v) discarding = null }">
      <UiDialogContent class="sm:max-w-md">
        <UiDialogHeader>
          <UiDialogTitle>Descartar este post?</UiDialogTitle>
          <UiDialogDescription>
            Ele não vai para nenhuma plataforma e não volta para a fila. A fornada segue
            normalmente.
          </UiDialogDescription>
        </UiDialogHeader>
        <UiDialogFooter>
          <button
            type="button"
            class="rounded-md border border-border px-3 py-2 text-sm font-medium transition hover:bg-muted"
            @click="discarding = null"
          >
            Manter na fila
          </button>
          <button
            type="button"
            class="rounded-md bg-destructive px-3 py-2 text-sm font-semibold text-destructive-foreground transition hover:bg-destructive/90"
            @click="confirmDiscard"
          >
            Descartar
          </button>
        </UiDialogFooter>
      </UiDialogContent>
    </UiDialog>
  </main>
</template>
