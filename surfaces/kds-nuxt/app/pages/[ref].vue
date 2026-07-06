<script setup lang="ts">
// Station board (Arc 2) — the core operator screen. Reads the canonical board
// projection + realtime (SSE + 15s poll) via useKdsBoard; renders prep tickets or
// expedition cards; the gestures (check item / finalize / dispatch) POST through
// the django proxy (CSRF handled there) and refresh. Status color is functional;
// chrome neutral.
import type { KDSExpeditionCardProjection, KDSTicketProjection } from "~/types/kds";
import { isExpeditionCard, splitRef } from "~/presentation/board";
import type { KDSDensity } from "~/components/KdsTicketCard.vue";

const route = useRoute();
const stationRef = computed(() => String(route.params.ref || ""));

// Write-side é otimista (toque instantâneo) e mora no composable, junto do estado.
const { view, pending, error, soundOn, soundBlocked, toggleSound, checkItem, finalize, expedite, recall, acknowledge } = useKdsBoard(stationRef.value);

// Recall: painel de concluídos recentes (desfazer finalização).
const recallOpen = ref(false);

// Relógio em tempo real (client-only; new Date() no SSR causaria mismatch).
const now = ref<Date | null>(null);
let clockTimer: ReturnType<typeof setInterval> | null = null;
const clockTime = computed(() => (now.value ? now.value.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }) : ""));
const clockSec = computed(() => (now.value ? String(now.value.getSeconds()).padStart(2, "0") : ""));
const clockDate = computed(() =>
  now.value ? now.value.toLocaleDateString("pt-BR", { weekday: "short", day: "2-digit", month: "short" }).replace(".", "") : "",
);
onMounted(() => {
  now.value = new Date();
  clockTimer = setInterval(() => (now.value = new Date()), 1000);
});
onBeforeUnmount(() => {
  if (clockTimer) clearInterval(clockTimer);
});

// Density (adjustable ticket size — KDS best practice). Persisted per terminal.
// A grade é auto-fill por largura MÍNIMA: os cards mantêm proporção RETRATO (colunas
// estreitas que empilham os itens em linhas) e enchem a tela em quantas colunas couber,
// sem depender de breakpoints. Densidade = quão estreito o card pode ser.
// `min` é a largura MÍNIMA que faz o REF + minutagem caberem com folga numa linha
// (nunca truncam). A grade preenche em quantas colunas couber a partir daí.
const DENSITIES: { key: KDSDensity; label: string; icon: string; min: number }[] = [
  { key: "compact", label: "Compacta", icon: "lucide:grid-3x3", min: 260 },
  { key: "cozy", label: "Padrão", icon: "lucide:layout-grid", min: 320 },
  { key: "roomy", label: "Ampla", icon: "lucide:square", min: 390 },
];
const density = ref<KDSDensity>("cozy");
const gridStyle = computed(() => {
  const min = DENSITIES.find((d) => d.key === density.value)?.min ?? 300;
  return { gridTemplateColumns: `repeat(auto-fill, minmax(min(100%, ${min}px), 1fr))` };
});

// Busca: filtra os cards por código, cliente ou item (útil pra consulta e na
// expedição; no preparo você faz o próximo). Contadores/all-day seguem o total da
// estação — a busca só filtra a grade.
const query = ref("");
function matchesQuery(card: KDSTicketProjection | KDSExpeditionCardProjection, q: string): boolean {
  const hay = [card.order_ref, card.customer_name, ...("items" in card ? card.items.map((i) => i.name) : [])].join(" ").toLowerCase();
  return hay.includes(q);
}
const filteredCards = computed(() => {
  const q = query.value.trim().toLowerCase();
  if (!q || !view.value) return view.value?.cards ?? [];
  return view.value.cards.filter((c) => matchesQuery(c, q));
});
function cycleDensity() {
  const i = DENSITIES.findIndex((d) => d.key === density.value);
  density.value = DENSITIES[(i + 1) % DENSITIES.length]!.key;
  if (import.meta.client) localStorage.setItem("kds.density", density.value);
}
onMounted(() => {
  const stored = localStorage.getItem("kds.density");
  if (stored === "compact" || stored === "cozy" || stored === "roomy") density.value = stored;
});

// Detail modal: the prep card is glanceable; tapping opens the work (items +
// finalize). The open ticket tracks live data (re-derived from the refreshed view).
const openTicketPk = ref<number | null>(null);
const openTicket = computed<KDSTicketProjection | null>(() => {
  const pk = openTicketPk.value;
  if (pk == null || !view.value) return null;
  const card = view.value.cards.find((c) => !isExpeditionCard(c) && c.pk === pk);
  return (card as KDSTicketProjection) ?? null;
});
function setModalOpen(value: boolean) {
  if (!value) openTicketPk.value = null;
}
function finalizeFromModal(pk: number) {
  finalize(pk); // otimista — fecha o modal na hora
  openTicketPk.value = null;
}

// Narrow the union for the template.
const asTicket = (c: KDSTicketProjection | KDSExpeditionCardProjection) => c as KDSTicketProjection;
const asExpedition = (c: KDSTicketProjection | KDSExpeditionCardProjection) => c as KDSExpeditionCardProjection;
</script>

<template>
  <main class="flex min-h-screen flex-col">
    <!-- context bar -->
    <header class="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-2 border-b bg-card px-4 py-2.5">
      <!-- Controle do rail (kit): a identidade/nav comum vive no OperatorRail à esquerda. -->
      <RailToggle />
      <div class="mr-auto min-w-0">
        <p class="text-[0.7rem] font-medium uppercase tracking-wider text-muted-foreground">
          {{ view?.isExpedition ? "Expedição" : "Estação KDS" }}
        </p>
        <h1 class="truncate text-lg font-bold leading-tight">{{ view?.instanceName || stationRef }}</h1>
      </div>

      <!-- relógio em tempo real -->
      <ClientOnly>
        <div v-if="now" class="flex flex-col items-end leading-none">
          <span class="text-lg font-bold tabular-nums">{{ clockTime }}<span class="text-sm font-medium text-muted-foreground">:{{ clockSec }}</span></span>
          <span class="text-[0.7rem] font-medium uppercase tracking-wider text-muted-foreground">{{ clockDate }}</span>
        </div>
      </ClientOnly>

      <!-- contadores: neutros e padronizados (cor reservada à urgência dos cards) -->
      <div v-if="view" class="flex items-baseline gap-1.5 rounded-md bg-muted px-2.5 py-1.5 text-sm">
        <span class="font-bold tabular-nums">{{ view.total }}</span>
        <span class="text-xs text-muted-foreground">ativos</span>
        <template v-if="view.counts.in_progress">
          <span class="text-muted-foreground/40">·</span>
          <span class="font-bold tabular-nums">{{ view.counts.in_progress }}</span>
          <span class="text-xs text-muted-foreground">em preparo</span>
        </template>
      </div>

      <!-- controles -->
      <div class="flex items-center gap-1.5">
        <div class="relative">
          <Icon name="lucide:search" class="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <input
            v-model="query"
            type="search"
            inputmode="search"
            placeholder="Buscar pedido…"
            class="h-9 w-36 rounded-md border bg-background pl-8 pr-7 text-sm outline-none transition focus:w-48 focus:ring-1 focus:ring-ring sm:w-44"
            aria-label="Buscar pedido por código, cliente ou item"
          />
          <button v-if="query" type="button" class="absolute right-1 top-1/2 grid size-6 -translate-y-1/2 place-items-center rounded text-muted-foreground transition hover:text-foreground" aria-label="Limpar busca" @click="query = ''">
            <Icon name="lucide:x" class="size-3.5" />
          </button>
        </div>
        <button type="button" class="grid size-9 place-items-center rounded-md border text-muted-foreground transition hover:bg-accent hover:text-foreground" :aria-label="`Densidade: ${density}`" title="Densidade da grade" @click="cycleDensity">
          <Icon :name="DENSITIES.find((d) => d.key === density)?.icon || 'lucide:layout-grid'" class="size-4" />
        </button>
        <button
          type="button"
          class="relative grid size-9 place-items-center rounded-md border transition hover:bg-accent hover:text-foreground"
          :class="soundOn && soundBlocked ? 'border-amber-500/50 text-amber-600 dark:text-amber-400' : 'text-muted-foreground'"
          :aria-label="soundOn && soundBlocked ? 'Som bloqueado — toque para ativar' : soundOn ? 'Som ativo' : 'Som desativado'"
          :title="soundOn && soundBlocked ? 'Som bloqueado — toque para ativar' : 'Som'"
          @click="toggleSound"
        >
          <Icon :name="soundOn ? 'lucide:volume-2' : 'lucide:volume-x'" class="size-4" />
          <span v-if="soundOn && soundBlocked" class="absolute -right-1 -top-1 size-2 rounded-full bg-amber-500" aria-hidden="true" />
        </button>
        <button v-if="view && !view.isExpedition && view.recentDone.length" type="button" class="relative grid size-9 place-items-center rounded-md border text-muted-foreground transition hover:bg-accent hover:text-foreground" aria-label="Concluídos recentes — reabrir" title="Concluídos recentes" @click="recallOpen = true">
          <Icon name="lucide:rotate-ccw" class="size-4" />
          <span class="absolute -right-1 -top-1 grid min-w-4 place-items-center rounded-full bg-foreground px-1 text-[0.6rem] font-bold tabular-nums text-background">{{ view.recentDone.length }}</span>
        </button>
        <NuxtLink to="/retirada" class="grid size-9 place-items-center rounded-md border text-muted-foreground transition hover:bg-accent hover:text-foreground" aria-label="Tela do cliente" title="Tela do cliente">
          <Icon name="lucide:monitor" class="size-4" />
        </NuxtLink>
      </div>
    </header>

    <!-- all-day: o que falta fazer somando os pedidos (mise en place / prep em lote).
         Bem legível — é uma das infos mais úteis da estação. -->
    <div v-if="view && !view.isExpedition && view.allDay.length" class="flex shrink-0 items-center gap-2.5 overflow-x-auto border-b bg-muted/40 px-4 py-2.5 no-scrollbar">
      <span class="flex shrink-0 items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-muted-foreground">
        <Icon name="lucide:clipboard-list" class="size-4" />
        A fazer
      </span>
      <span
        v-for="entry in view.allDay"
        :key="entry.name"
        class="inline-flex shrink-0 items-center gap-2 rounded-md border bg-background px-3 py-1.5"
      >
        <span class="text-base font-bold tabular-nums">{{ entry.qty }}×</span>
        <span class="text-sm font-medium">{{ entry.name }}</span>
      </span>
    </div>

    <section class="min-h-0 flex-1 overflow-auto p-3 md:p-4">
      <p v-if="pending && !view" class="text-sm text-muted-foreground">Carregando…</p>
      <!-- Erro com dados em cache NUNCA apaga o board: um blip de 1 poll não
           pode esconder os tickets da cozinha — banner acima, cards embaixo. -->
      <p v-if="error && !view" class="rounded-md border border-red-500/30 bg-red-500/5 p-4 text-sm text-red-700 dark:text-red-400">
        Falha ao carregar o board. Reconectando…
      </p>
      <p v-else-if="error && view" class="mb-3 rounded-md border border-amber-500/30 bg-amber-500/5 p-2 text-xs text-amber-700 dark:text-amber-400">
        Sem conexão — mostrando o último estado. Reconectando…
      </p>
      <template v-if="view">
        <!-- cancelled (loud — único lugar onde o vermelho é alerta de verdade) -->
        <div v-if="view.cancelled.length" class="mb-3 grid gap-2 md:grid-cols-2 xl:grid-cols-3">
          <article v-for="t in view.cancelled" :key="`x-${t.pk}`" class="flex items-start justify-between gap-3 rounded-md border border-l-4 border-l-red-500 bg-red-500/10 p-4">
            <div class="min-w-0">
              <div class="flex items-center gap-2 text-sm font-semibold text-red-400">
                <Icon name="lucide:ban" class="size-4 shrink-0" />
                Cancelado{{ t.cancelled_at_display ? ` às ${t.cancelled_at_display}` : "" }}
              </div>
              <div class="mt-1 break-words text-xl font-bold tabular-nums">{{ t.order_ref }}</div>
              <p v-if="t.customer_name" class="truncate text-sm text-muted-foreground">{{ t.customer_name }}</p>
            </div>
            <button
              type="button"
              class="flex shrink-0 items-center gap-1.5 rounded-md border border-red-500/40 px-3 py-2 text-sm font-semibold text-red-300 transition hover:bg-red-500/15 active:scale-[0.98]"
              aria-label="Dar baixa no cancelado"
              @click="acknowledge(t.pk)"
            >
              <Icon name="lucide:check" class="size-4" />
              Ciente
            </button>
          </article>
        </div>

        <!-- empty — estação zerada: estado calmo/acolhedor (omotenashi) -->
        <div v-if="!view.cards.length" class="grid place-items-center gap-3 rounded-md border border-dashed py-20 text-center">
          <div class="grid size-16 place-items-center rounded-full bg-green-500/10 text-green-400">
            <Icon name="lucide:coffee" class="size-8" />
          </div>
          <p class="text-2xl font-bold">Tudo em dia</p>
          <p class="max-w-sm text-base text-muted-foreground">
            Nenhum pedido na fila agora. Aproveite para respirar — a gente avisa quando o próximo chegar.
          </p>
        </div>

        <!-- busca sem resultado -->
        <div v-else-if="!filteredCards.length" class="grid place-items-center gap-2 rounded-md border border-dashed py-16 text-center">
          <Icon name="lucide:search-x" class="size-10 text-muted-foreground" />
          <p class="text-base font-semibold">Nenhum pedido para “{{ query.trim() }}”.</p>
          <button type="button" class="text-sm font-medium text-muted-foreground underline-offset-2 hover:underline" @click="query = ''">Limpar busca</button>
        </div>

        <!-- grade uniforme, auto-ordenada por urgência. O 1º card de preparo é o
             "próximo" — pintado ton sur ton (sem posição/tamanho especial). A ordem
             é indicada aqui na seção, não dentro do card. -->
        <template v-else>
          <p v-if="!view.isExpedition && !query" class="mb-2.5 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            <Icon name="lucide:arrow-down-wide-narrow" class="size-3.5" />
            Mais urgente primeiro — o destacado é o próximo
          </p>
          <TransitionGroup tag="div" name="kds-card" class="grid items-start gap-3" :style="gridStyle">
            <div v-for="(card, idx) in filteredCards" :key="card.pk">
              <KdsExpeditionCard
                v-if="isExpeditionCard(card)"
                :card="asExpedition(card)"
                :density="density"
                @action="(action) => expedite(card.pk, action)"
              />
              <KdsTicketCard
                v-else
                :ticket="asTicket(card)"
                :density="density"
                :next="!query && !view.isExpedition && idx === 0"
                @open="openTicketPk = card.pk"
                @check="(i, checked) => checkItem(card.pk, i, checked)"
                @done="finalize(card.pk)"
              />
            </div>
          </TransitionGroup>
        </template>
      </template>
    </section>

    <!-- detail modal (opened from a card) -->
    <KdsTicketModal
      :open="openTicket != null"
      :ticket="openTicket"
      @update:open="setModalOpen"
      @check-item="(idx, checked) => openTicket && checkItem(openTicket.pk, idx, checked)"
      @done="openTicket && finalizeFromModal(openTicket.pk)"
    />

    <!-- recall: concluídos recentes (desfazer finalização) -->
    <UiDialog :open="recallOpen" @update:open="recallOpen = Boolean($event)">
      <UiDialogContent class="flex max-h-[85vh] flex-col gap-0 overflow-hidden p-0 sm:max-w-md">
        <UiDialogTitle class="border-b px-5 py-4 text-lg font-bold">Concluídos recentes</UiDialogTitle>
        <UiDialogDescription class="sr-only">Reabra um pedido finalizado por engano (últimos 30 minutos).</UiDialogDescription>
        <div class="min-h-0 flex-1 overflow-y-auto p-3">
          <p v-if="!view || !view.recentDone.length" class="p-6 text-center text-sm text-muted-foreground">Nada concluído nos últimos 30 minutos.</p>
          <ul v-else class="flex flex-col gap-1.5">
            <li v-for="t in view.recentDone" :key="t.pk" class="flex items-center justify-between gap-3 rounded-md border p-3">
              <div class="min-w-0">
                <p class="truncate text-lg font-bold tabular-nums leading-tight">{{ splitRef(t.order_ref).code }}</p>
                <p class="truncate text-sm text-muted-foreground">
                  {{ t.customer_name || t.order_ref }}<template v-if="t.completed_at_display"> · {{ t.completed_at_display }}</template>
                </p>
              </div>
              <button
                type="button"
                class="flex shrink-0 items-center gap-1.5 rounded-md border px-3 py-2 text-sm font-semibold transition hover:bg-accent active:scale-[0.98]"
                @click="recall(t.pk)"
              >
                <Icon name="lucide:rotate-ccw" class="size-4" />
                Reabrir
              </button>
            </li>
          </ul>
        </div>
      </UiDialogContent>
    </UiDialog>
  </main>
</template>

<style scoped>
/* Transição da grade: ao finalizar, o card sai com um respiro (bump) e a fila desliza
   pra cima (FLIP) — o próximo "assume o foco" e sua cor pinta suave (via .transition do
   card). Novos pedidos entram com o mesmo respiro. */
.kds-card-move {
  transition: transform 0.35s cubic-bezier(0.2, 0, 0, 1);
}
.kds-card-enter-active,
.kds-card-leave-active {
  transition: opacity 0.28s ease, transform 0.28s ease;
}
.kds-card-enter-from,
.kds-card-leave-to {
  opacity: 0;
  transform: scale(0.96);
}

@media (prefers-reduced-motion: reduce) {
  .kds-card-move,
  .kds-card-enter-active,
  .kds-card-leave-active {
    transition: none;
  }
}
</style>
