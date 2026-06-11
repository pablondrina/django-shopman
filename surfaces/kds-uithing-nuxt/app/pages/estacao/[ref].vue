<script setup lang="ts">
// Station board (Arc 2) — the core operator screen. Reads the canonical board
// projection + realtime (SSE + 15s poll) via useKdsBoard; renders prep tickets or
// expedition cards; the gestures (check item / finalize / dispatch) POST through
// the django proxy (CSRF handled there) and refresh. Status color is functional;
// chrome neutral.
import type { KDSExpeditionCardProjection, KDSTicketProjection } from "~/types/kds";
import { isExpeditionCard } from "~/presentation/board";
import type { KDSDensity } from "~/components/KdsTicketCard.vue";

const route = useRoute();
const stationRef = computed(() => String(route.params.ref || ""));

const { view, pending, error, refresh, soundOn, toggleSound } = useKdsBoard(stationRef.value);

// Density (adjustable text/ticket size — KDS best practice). Persisted per terminal.
const DENSITIES: { key: KDSDensity; label: string; icon: string; cols: string }[] = [
  { key: "compact", label: "Compacta", icon: "lucide:grid-3x3", cols: "grid-cols-2 md:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5" },
  { key: "cozy", label: "Padrão", icon: "lucide:layout-grid", cols: "grid-cols-1 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4" },
  { key: "roomy", label: "Ampla", icon: "lucide:square", cols: "grid-cols-1 md:grid-cols-2 xl:grid-cols-2 2xl:grid-cols-3" },
];
const density = ref<KDSDensity>("cozy");
const densityCols = computed(() => DENSITIES.find((d) => d.key === density.value)?.cols ?? DENSITIES[1]!.cols);
function cycleDensity() {
  const i = DENSITIES.findIndex((d) => d.key === density.value);
  density.value = DENSITIES[(i + 1) % DENSITIES.length]!.key;
  if (import.meta.client) localStorage.setItem("kds.density", density.value);
}
onMounted(() => {
  const stored = localStorage.getItem("kds.density");
  if (stored === "compact" || stored === "cozy" || stored === "roomy") density.value = stored;
});

const busy = ref(false);
async function write(path: string, body?: Record<string, unknown>) {
  if (busy.value) return;
  busy.value = true;
  try {
    await $fetch(path, { method: "POST", body: body ?? {} });
    await refresh();
  } catch (err: any) {
    // Surface the failure — a silent KDS write is dangerous (the operator thinks
    // it landed). The board refresh still reconciles to the true server state.
    useSonner.error(err?.data?.detail || "Falha na ação. Tente de novo.");
    await refresh();
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
        <button type="button" class="grid size-9 place-items-center rounded-md border text-muted-foreground transition hover:bg-accent" :aria-label="`Densidade: ${density}`" title="Densidade da grade" @click="cycleDensity">
          <Icon :name="DENSITIES.find((d) => d.key === density)?.icon || 'lucide:layout-grid'" class="size-4" />
        </button>
        <button type="button" class="grid size-9 place-items-center rounded-md border text-muted-foreground transition hover:bg-accent" :aria-label="soundOn ? 'Som ativo' : 'Som desativado'" @click="toggleSound">
          <Icon :name="soundOn ? 'lucide:volume-2' : 'lucide:volume-x'" class="size-4" />
        </button>
        <NuxtLink to="/cliente" class="grid size-9 place-items-center rounded-md border text-muted-foreground transition hover:bg-accent" aria-label="Tela do cliente">
          <Icon name="lucide:monitor" class="size-4" />
        </NuxtLink>
      </div>
    </header>

    <!-- all-day: o que falta fazer somando os pedidos (mise en place / prep em lote) -->
    <div v-if="view && !view.isExpedition && view.allDay.length" class="flex shrink-0 items-center gap-2 overflow-x-auto border-b bg-card/60 px-4 py-2 no-scrollbar">
      <span class="shrink-0 text-xs font-semibold uppercase tracking-wide text-muted-foreground">A fazer</span>
      <span
        v-for="entry in view.allDay"
        :key="entry.name"
        class="inline-flex shrink-0 items-center gap-1.5 rounded-full border bg-background px-2.5 py-1 text-sm"
      >
        <strong class="tabular-nums">{{ entry.qty }}×</strong>
        <span class="text-muted-foreground">{{ entry.name }}</span>
      </span>
    </div>

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

        <!-- cards (auto-sorted by urgency; density-adaptive grid) -->
        <div v-else class="grid items-start gap-3" :class="densityCols">
          <template v-for="card in view.cards" :key="card.pk">
            <KdsExpeditionCard
              v-if="isExpeditionCard(card)"
              :card="asExpedition(card)"
              :busy="busy"
              :density="density"
              @action="(action) => expedite(card.pk, action)"
            />
            <KdsTicketCard
              v-else
              :ticket="asTicket(card)"
              :busy="busy"
              :density="density"
              @check-item="(idx, checked) => checkItem(card.pk, idx, checked)"
              @done="finalize(card.pk)"
            />
          </template>
        </div>
      </template>
    </section>
  </main>
</template>
