<script setup lang="ts">
// Order board — the operator hub. Reads the two-zone queue projection + realtime
// (SSE + 30s poll) via useOrdersBoard; renders Entrada / Preparo / Saída columns of
// OrderCards; the gestures POST through the django proxy (CSRF handled there) and
// reconcile. Desktop-first (3 columns), responsive (stacks on tablet/phone).
import type { AffordanceRef, ZoneView } from "~/presentation/board";
import { matchesQuery } from "~/presentation/board";
import type { OrderCardProjection } from "~/types/orders";

const { zones, totalCount, pending, error, refresh, isBusy, confirm, advance, reject, settleCash } = useOrdersBoard();

// search filters the cards; counts follow the full queue.
const query = ref("");
function filteredCards(zone: ZoneView): OrderCardProjection[] {
  return zone.cards.filter((c) => matchesQuery(c, query.value));
}

const colorMode = useColorMode();
function toggleTheme() {
  colorMode.preference = colorMode.value === "dark" ? "light" : "dark";
}

// realtime clock (client-only; new Date() on SSR would mismatch).
const now = ref<Date | null>(null);
let clockTimer: ReturnType<typeof setInterval> | null = null;
const clockTime = computed(() => (now.value ? now.value.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }) : ""));
onMounted(() => {
  now.value = new Date();
  clockTimer = setInterval(() => (now.value = new Date()), 30_000);
});
onBeforeUnmount(() => { if (clockTimer) clearInterval(clockTimer); });

// reject dialog (needs a reason).
const rejectRef = ref<string | null>(null);
const rejectReason = ref("");
function openReject(ref_: string) { rejectRef.value = ref_; rejectReason.value = ""; }
async function confirmReject() {
  const ref_ = rejectRef.value;
  if (!ref_ || !rejectReason.value.trim()) return;
  const ok = await reject(ref_, rejectReason.value.trim());
  if (ok) rejectRef.value = null;
}

// settle-cash dialog (needs an amount).
const settleRef = ref<string | null>(null);
const settleAmount = ref("");
function openSettle(ref_: string) { settleRef.value = ref_; settleAmount.value = ""; }
async function confirmSettle() {
  const ref_ = settleRef.value;
  if (!ref_) return;
  const ok = await settleCash(ref_, settleAmount.value.trim());
  if (ok) settleRef.value = null;
}

function onAction(ref_: string, action: AffordanceRef) {
  if (action === "confirm") confirm(ref_);
  else if (action === "advance") advance(ref_);
  else if (action === "reject") openReject(ref_);
  else if (action === "settle_cash") openSettle(ref_);
}
</script>

<template>
  <main class="flex min-h-screen flex-col">
    <header class="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-2 border-b bg-card px-4 py-2.5">
      <span class="grid size-9 shrink-0 place-items-center rounded-md border bg-card text-foreground">
        <Icon name="lucide:clipboard-list" class="size-4" />
      </span>
      <div class="mr-auto min-w-0">
        <p class="text-[0.7rem] font-medium uppercase tracking-wider text-muted-foreground">Gestor</p>
        <h1 class="truncate text-lg font-bold leading-tight">Pedidos</h1>
      </div>

      <ClientOnly>
        <div v-if="now" class="hidden flex-col items-end leading-none sm:flex">
          <span class="text-lg font-bold tabular-nums">{{ clockTime }}</span>
          <span class="text-[0.7rem] font-medium uppercase tracking-wider text-muted-foreground">{{ totalCount }} ativos</span>
        </div>
      </ClientOnly>

      <div class="flex items-center gap-1.5">
        <div class="relative">
          <Icon name="lucide:search" class="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <input
            v-model="query"
            type="search"
            inputmode="search"
            placeholder="Buscar pedido…"
            class="h-9 w-36 rounded-md border bg-background pl-8 pr-7 text-sm outline-none transition focus:w-48 focus:ring-1 focus:ring-ring sm:w-44"
            aria-label="Buscar por código, cliente ou item"
          />
          <button v-if="query" type="button" class="absolute right-1 top-1/2 grid size-6 -translate-y-1/2 place-items-center rounded text-muted-foreground transition hover:text-foreground" aria-label="Limpar busca" @click="query = ''">
            <Icon name="lucide:x" class="size-3.5" />
          </button>
        </div>
        <button type="button" class="grid size-9 place-items-center rounded-md border text-muted-foreground transition hover:bg-accent hover:text-foreground" aria-label="Atualizar" title="Atualizar" @click="refresh()">
          <Icon name="lucide:refresh-cw" class="size-4" :class="pending ? 'animate-spin' : ''" />
        </button>
        <ClientOnly>
          <button type="button" class="grid size-9 place-items-center rounded-md border text-muted-foreground transition hover:bg-accent hover:text-foreground" :aria-label="colorMode.value === 'dark' ? 'Tema claro' : 'Tema escuro'" title="Tema" @click="toggleTheme">
            <Icon :name="colorMode.value === 'dark' ? 'lucide:sun' : 'lucide:moon'" class="size-4" />
          </button>
          <template #fallback>
            <span class="grid size-9 place-items-center rounded-md border text-muted-foreground"><Icon name="lucide:moon" class="size-4" /></span>
          </template>
        </ClientOnly>
      </div>
    </header>

    <section class="min-h-0 flex-1 overflow-auto p-3 md:p-4">
      <p v-if="pending && !zones.length" class="text-sm text-muted-foreground">Carregando…</p>
      <p v-else-if="error" class="rounded-md border border-red-500/30 bg-red-500/5 p-4 text-sm text-red-700 dark:text-red-400">
        Falha ao carregar a fila. Reconectando…
      </p>

      <div v-else class="grid gap-4 lg:grid-cols-3">
        <section v-for="zone in zones" :key="zone.key" class="flex min-w-0 flex-col gap-3">
          <div class="flex items-center gap-2 border-b pb-2">
            <Icon :name="zone.icon" class="size-4 text-muted-foreground" />
            <h2 class="text-sm font-bold uppercase tracking-wide">{{ zone.title }}</h2>
            <span class="grid min-w-5 place-items-center rounded-full bg-muted px-1.5 text-xs font-bold tabular-nums">{{ zone.count }}</span>
            <span class="ml-auto hidden truncate text-xs text-muted-foreground sm:block">{{ zone.subtitle }}</span>
          </div>

          <div v-if="!zone.cards.length" class="grid place-items-center gap-1.5 rounded-lg border border-dashed py-10 text-center text-muted-foreground">
            <Icon name="lucide:check-circle-2" class="size-6" />
            <p class="text-sm">Nada por aqui agora.</p>
          </div>

          <template v-else>
            <OrderCard
              v-for="card in filteredCards(zone)"
              :key="card.ref"
              :card="card"
              :busy="isBusy(card.ref)"
              @action="(action) => onAction(card.ref, action)"
            />
            <p v-if="query && !filteredCards(zone).length" class="rounded-md border border-dashed p-3 text-center text-xs text-muted-foreground">
              Nenhum resultado para “{{ query.trim() }}”.
            </p>
          </template>
        </section>
      </div>
    </section>

    <!-- reject dialog -->
    <UiDialog :open="rejectRef != null" @update:open="(v) => { if (!v) rejectRef = null }">
      <UiDialogContent class="sm:max-w-md">
        <UiDialogHeader>
          <UiDialogTitle>Recusar pedido {{ rejectRef }}</UiDialogTitle>
          <UiDialogDescription>Informe o motivo — o cliente é avisado.</UiDialogDescription>
        </UiDialogHeader>
        <textarea
          v-model="rejectReason"
          rows="3"
          placeholder="Motivo da recusa…"
          class="w-full rounded-md border bg-background p-2.5 text-sm outline-none focus:ring-1 focus:ring-ring"
          aria-label="Motivo da recusa"
        />
        <UiDialogFooter>
          <button type="button" class="rounded-md border px-3 py-2 text-sm font-medium transition hover:bg-accent" @click="rejectRef = null">Cancelar</button>
          <button
            type="button"
            :disabled="!rejectReason.trim()"
            class="rounded-md border border-transparent bg-red-600 px-3 py-2 text-sm font-semibold text-white transition hover:bg-red-700 disabled:opacity-50"
            @click="confirmReject"
          >
            Recusar pedido
          </button>
        </UiDialogFooter>
      </UiDialogContent>
    </UiDialog>

    <!-- settle-cash dialog -->
    <UiDialog :open="settleRef != null" @update:open="(v) => { if (!v) settleRef = null }">
      <UiDialogContent class="sm:max-w-sm">
        <UiDialogHeader>
          <UiDialogTitle>Acerto de dinheiro</UiDialogTitle>
          <UiDialogDescription>Valor recebido na entrega ({{ settleRef }}). Em branco usa o total do pedido.</UiDialogDescription>
        </UiDialogHeader>
        <input
          v-model="settleAmount"
          type="text"
          inputmode="decimal"
          placeholder="Ex.: 15,00"
          class="w-full rounded-md border bg-background p-2.5 text-sm outline-none focus:ring-1 focus:ring-ring"
          aria-label="Valor recebido"
        />
        <UiDialogFooter>
          <button type="button" class="rounded-md border px-3 py-2 text-sm font-medium transition hover:bg-accent" @click="settleRef = null">Cancelar</button>
          <button type="button" class="rounded-md border border-transparent bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90" @click="confirmSettle">
            Confirmar acerto
          </button>
        </UiDialogFooter>
      </UiDialogContent>
    </UiDialog>
  </main>
</template>
