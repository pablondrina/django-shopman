<script setup lang="ts">
// Station board (Arc 2) — the core operator screen. Reads the canonical board
// projection + realtime (SSE + 15s poll) via useKdsBoard; renders prep tickets or
// expedition cards; the gestures (check item / finalize / dispatch) POST through
// the django proxy (CSRF handled there) and refresh. Status color is functional;
// chrome neutral.
import type { KDSExpeditionCardProjection, KDSTicketProjection } from "~/types/kds";
import { isExpeditionCard } from "~/presentation/board";

const route = useRoute();
const stationRef = computed(() => String(route.params.ref || ""));

const { view, pending, error, refresh, soundOn, toggleSound } = useKdsBoard(stationRef.value);

const busy = ref(false);
async function write(path: string, body?: Record<string, unknown>) {
  if (busy.value) return;
  busy.value = true;
  try {
    await $fetch(path, { method: "POST", body: body ?? {} });
    await refresh();
  } catch {
    /* surface lightly; the board refresh reconciles on next poll/SSE */
  } finally {
    busy.value = false;
  }
}
const checkItem = (pk: number, index: number, checked: boolean) =>
  write(`/api/v1/backstage/kds/tickets/${pk}/items/`, { index, checked });
const finalize = (pk: number) => write(`/api/v1/backstage/kds/tickets/${pk}/done/`);
const expedite = (pk: number, action: "dispatch" | "complete") =>
  write(`/api/v1/backstage/kds/expedition/${pk}/action/`, { action });

// Narrow the union for the template.
const asTicket = (c: KDSTicketProjection | KDSExpeditionCardProjection) => c as KDSTicketProjection;
const asExpedition = (c: KDSTicketProjection | KDSExpeditionCardProjection) => c as KDSExpeditionCardProjection;
</script>

<template>
  <main class="flex min-h-screen flex-col">
    <!-- context bar -->
    <header class="flex shrink-0 flex-wrap items-center gap-3 border-b bg-card px-4 py-3">
      <NuxtLink to="/" class="grid size-9 place-items-center rounded-md border text-muted-foreground transition hover:bg-accent" aria-label="Trocar de estação">
        <Icon name="lucide:grid-2x2" class="size-4" />
      </NuxtLink>
      <div class="min-w-0">
        <p class="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {{ view?.isExpedition ? "Expedição" : "Estação KDS" }}
        </p>
        <h1 class="truncate text-xl font-semibold leading-tight">{{ view?.instanceName || stationRef }}</h1>
      </div>
      <div class="ml-auto flex items-center gap-2">
        <span v-if="view" class="rounded-full bg-muted px-2 py-0.5 text-xs font-semibold tabular-nums text-muted-foreground">
          {{ view.total }} ativos
        </span>
        <span v-if="view?.counts.pending" class="rounded-full bg-cyan-500/10 px-2 py-0.5 text-xs font-semibold text-cyan-700 dark:text-cyan-400">
          {{ view.counts.pending }} pendentes
        </span>
        <span v-if="view?.counts.in_progress" class="rounded-full bg-amber-500/10 px-2 py-0.5 text-xs font-semibold text-amber-700 dark:text-amber-400">
          {{ view.counts.in_progress }} em preparo
        </span>
        <button type="button" class="grid size-9 place-items-center rounded-md border text-muted-foreground transition hover:bg-accent" :aria-label="soundOn ? 'Som ativo' : 'Som desativado'" @click="toggleSound">
          <Icon :name="soundOn ? 'lucide:volume-2' : 'lucide:volume-x'" class="size-4" />
        </button>
        <NuxtLink to="/cliente" class="grid size-9 place-items-center rounded-md border text-muted-foreground transition hover:bg-accent" aria-label="Tela do cliente">
          <Icon name="lucide:monitor" class="size-4" />
        </NuxtLink>
      </div>
    </header>

    <section class="min-h-0 flex-1 overflow-auto p-3 md:p-4">
      <p v-if="pending && !view" class="text-sm text-muted-foreground">Carregando…</p>
      <p v-else-if="error" class="rounded-md border border-red-500/30 bg-red-500/5 p-4 text-sm text-red-700 dark:text-red-400">
        Falha ao carregar o board. Reconectando…
      </p>
      <template v-else-if="view">
        <!-- cancelled (loud) -->
        <div v-if="view.cancelled.length" class="mb-3 grid gap-2 md:grid-cols-2 xl:grid-cols-3">
          <article v-for="t in view.cancelled" :key="`x-${t.pk}`" class="rounded-md border border-l-4 border-l-red-500 bg-red-500/5 p-4">
            <div class="flex items-center gap-2 text-sm font-semibold text-red-700 dark:text-red-400">
              <Icon name="lucide:ban" class="size-4" />
              Cancelado{{ t.cancelled_at_display ? ` às ${t.cancelled_at_display}` : "" }}
            </div>
            <div class="mt-1 truncate text-xl font-bold tabular-nums">{{ t.order_ref }}</div>
            <p v-if="t.customer_name" class="truncate text-sm text-muted-foreground">{{ t.customer_name }}</p>
          </article>
        </div>

        <!-- empty -->
        <div v-if="!view.cards.length" class="grid place-items-center rounded-md border border-dashed py-16 text-center">
          <Icon name="lucide:check-check" class="mb-3 size-10 text-muted-foreground" />
          <p class="text-base font-semibold">Nenhum pedido ativo nesta estação.</p>
        </div>

        <!-- cards -->
        <div v-else class="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          <template v-for="card in view.cards" :key="card.pk">
            <KdsExpeditionCard
              v-if="isExpeditionCard(card)"
              :card="asExpedition(card)"
              :busy="busy"
              @action="(action) => expedite(card.pk, action)"
            />
            <KdsTicketCard
              v-else
              :ticket="asTicket(card)"
              :busy="busy"
              @check-item="(idx, checked) => checkItem(card.pk, idx, checked)"
              @done="finalize(card.pk)"
            />
          </template>
        </div>
      </template>
    </section>
  </main>
</template>
