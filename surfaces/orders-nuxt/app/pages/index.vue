<script setup lang="ts">
// Order board — the operator hub. Reads the two-zone queue projection + realtime
// (SSE + 30s poll) via useOrdersBoard; renders Entrada / Preparo / Saída columns of
// OrderCards; the gestures POST through the django proxy (CSRF handled there) and
// reconcile. Desktop-first (3 columns), responsive (stacks on tablet/phone).
import type { AffordanceRef, FulfillmentFilter, SortKey, ViewMode, ZoneView } from "~/presentation/board";
import {
  bulkableRefs,
  cardAffordances,
  channelLabel,
  channelOptions,
  elapsedLabel,
  flattenZones,
  fulfillmentCounts,
  lucideIcon,
  nextSort,
  realtimeIndicator,
  resolveShortcut,
  rowsToCsv,
  SORT_OPTIONS,
  splitRef,
  statusTone,
  timerChip,
  timerTone,
  toneBadge,
  triageCards,
} from "~/presentation/board";
import type { OrderCardProjection } from "~/types/orders";
import type { CancellationReason } from "~/composables/useOrdersBoard";

const { zones, preorders, realtime, pending, error, refresh, isBusy, actionError, clearActionError, confirm, advance, reject, fetchCancellationReasons, settleCash, assign, unassign, confirmMany, advanceMany } = useOrdersBoard();

// Sinal honesto de tempo-real vs poll (indicador de degradação do SSE).
const realtimeView = computed(() => realtimeIndicator(realtime.value));

// ── triage: search + channel filter + sort + view-mode (Arc 1) ──────────────
// query/channel are transient; sort/view persist per operator (cookie, SSR-safe).
const query = ref("");
const channel = ref("all");
const fulfillment = ref<FulfillmentFilter>("all");
const sort = useCookie<SortKey>("gestor-sort", { default: () => "arrival", sameSite: "lax" });
const viewMode = useCookie<ViewMode>("gestor-view", { default: () => "board", sameSite: "lax" });

const allCards = computed<OrderCardProjection[]>(() => zones.value.flatMap((z) => z.cards));
const channels = computed(() => channelOptions(allCards.value));
const fulfillment_ = computed(() => fulfillmentCounts(allCards.value));
const sortLabel = computed(() => SORT_OPTIONS.find((o) => o.key === sort.value)?.label ?? "Chegada");

function triaged(zone: ZoneView): OrderCardProjection[] {
  return triageCards(zone.cards, { query: query.value, channel: channel.value, sort: sort.value, fulfillment: fulfillment.value });
}
// flat rows for the dense table view, honouring the same triage + zone order.
const tableRows = computed(() =>
  flattenZones(zones.value.map((z) => ({ ...z, cards: triaged(z) }))),
);
// how many cards survive the current filters (for the "no results" affordance).
const visibleCount = computed(() => zones.value.reduce((n, z) => n + triaged(z).length, 0));
const hasFilter = computed(() => query.value.trim() !== "" || channel.value !== "all" || fulfillment.value !== "all");

// Encomendas (datas futuras) sob o mesmo triage do board (busca/canal/tipo);
// o sort não se aplica — a ordem canônica é a data combinada.
const triagedPreorders = computed(() =>
  preorders.value
    .map((group) => ({
      ...group,
      cards: triageCards(group.cards, { query: query.value, channel: channel.value, sort: "arrival", fulfillment: fulfillment.value }),
    }))
    .filter((group) => group.cards.length),
);
const preordersCount = computed(() => triagedPreorders.value.reduce((n, g) => n + g.cards.length, 0));

// ── bulk selection (Arc 4) ──────────────────────────────────────────────────
const selected = ref<Set<string>>(new Set());
const isSelected = (ref_: string) => selected.value.has(ref_);
function toggleSelect(ref_: string) {
  const next = new Set(selected.value);
  if (next.has(ref_)) next.delete(ref_);
  else next.add(ref_);
  selected.value = next;
}
function clearSelection() {
  selected.value = new Set();
}
// select-all over the currently visible (triaged) cards.
const visibleRefs = computed(() => tableRows.value.map((r) => r.card.ref));
const allVisibleSelected = computed(() => visibleRefs.value.length > 0 && visibleRefs.value.every((r) => selected.value.has(r)));
function toggleSelectAll() {
  selected.value = allVisibleSelected.value ? new Set() : new Set(visibleRefs.value);
}
const confirmableSel = computed(() => bulkableRefs(allCards.value, selected.value, "confirm"));
const advanceableSel = computed(() => bulkableRefs(allCards.value, selected.value, "advance"));
async function bulkConfirm() {
  await confirmMany(confirmableSel.value);
  clearSelection();
}
async function bulkAdvance() {
  await advanceMany(advanceableSel.value);
  clearSelection();
}

// sort menu (house pattern: button + backdrop + absolute panel).
const sortOpen = ref(false);
function pickSort(key: SortKey) {
  sort.value = key;
  sortOpen.value = false;
}

// keyboard shortcuts (Arc 3): / search · r refresh · v view · s sort · Esc clear.
// Pure mapping in resolveShortcut; here we run the effects and skip while typing.
const searchInput = ref<{ focus: () => void } | null>(null);
function onKeydown(e: KeyboardEvent) {
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  const el = e.target as HTMLElement | null;
  const typing = !!el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable);
  const shortcut = resolveShortcut(e.key);
  if (!shortcut) return;
  // While typing, only Escape (clear-filters / blur) is honoured.
  if (typing && shortcut !== "clear-filters") return;
  switch (shortcut) {
    case "focus-search":
      e.preventDefault();
      searchInput.value?.focus();
      break;
    case "refresh":
      refresh();
      break;
    case "toggle-view":
      viewMode.value = viewMode.value === "board" ? "table" : "board";
      break;
    case "cycle-sort":
      sort.value = nextSort(sort.value);
      break;
    case "clear-filters":
      query.value = "";
      channel.value = "all";
      fulfillment.value = "all";
      if (typing) (el as HTMLElement).blur();
      break;
  }
}
onMounted(() => window.addEventListener("keydown", onKeydown));
onBeforeUnmount(() => window.removeEventListener("keydown", onKeydown));

// reject dialog (needs a reason). For marketplace (iFood) orders the reason is a
// coded pick from the provider's live list; other channels use free text.
const rejectRef = ref<string | null>(null);
const rejectReason = ref("");
const rejectReasons = ref<CancellationReason[]>([]);
const rejectCode = ref("");
const rejectReasonsLoading = ref(false);
const isMarketplaceReject = computed(() => rejectReasons.value.length > 0);
const canConfirmReject = computed(() =>
  isMarketplaceReject.value ? rejectCode.value !== "" : rejectReason.value.trim() !== "",
);
async function openReject(ref_: string) {
  rejectRef.value = ref_;
  rejectReason.value = "";
  rejectCode.value = "";
  rejectReasons.value = [];
  rejectReasonsLoading.value = true;
  try {
    rejectReasons.value = await fetchCancellationReasons(ref_);
  } finally {
    rejectReasonsLoading.value = false;
  }
}
function onRejectCodeChange() {
  // Mirror the picked reason's text into the customer-facing reason.
  const picked = rejectReasons.value.find((r) => r.code === rejectCode.value);
  if (picked) rejectReason.value = picked.description;
}
async function confirmReject() {
  const ref_ = rejectRef.value;
  if (!ref_ || !canConfirmReject.value) return;
  const ok = await reject(ref_, rejectReason.value.trim() || "Pedido recusado", rejectCode.value);
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

// claim/release an order ("estou atendendo").
function onToggleAssign(card: OrderCardProjection) {
  if (card.assigned_operator) unassign(card.ref);
  else assign(card.ref);
}

// ── export / print (Arc 5) ───────────────────────────────────────────────
// CSV of the current (triaged) queue for a shift handover; print uses the
// browser dialog (the print stylesheet hides the chrome and shows the table).
function exportCsv() {
  const csv = rowsToCsv(tableRows.value);
  const blob = new Blob([`\uFEFF${csv}`], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const stamp = new Date().toISOString().slice(0, 16).replace("T", "-").replace(":", "h");
  const a = document.createElement("a");
  a.href = url;
  a.download = `pedidos-${stamp}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}
function printQueue() {
  window.print();
}
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col">
    <!-- work toolbar: search · channel chips · sort/view/actions -->
    <UiToolbar>
      <UiSearchInput
        ref="searchInput"
        :model-value="query"
        placeholder="Buscar pedido…"
        aria-label="Buscar por código, cliente ou item (atalho: /)"
        @update:model-value="(v) => (query = v)"
      />
      <div v-if="allCards.length" class="flex flex-wrap items-center gap-1.5">
        <UiFilterChip :active="channel === 'all'" :count="allCards.length" @click="channel = 'all'">
          Todos
        </UiFilterChip>
        <UiFilterChip
          v-for="opt in channels"
          :key="opt.ref"
          :active="channel === opt.ref"
          :count="opt.count"
          @click="channel = opt.ref"
        >
          <template #icon>
            <Icon :name="`lucide:${lucideIcon(allCards.find((c) => c.channel_ref === opt.ref)?.channel_icon || '')}`" class="size-3.5" />
          </template>
          {{ opt.label }}
        </UiFilterChip>
      </div>

      <!-- fulfillment axis: o que muda o FLUXO (rota vs balcão) -->
      <div v-if="allCards.length" class="flex items-center gap-1.5">
        <div class="h-5 w-px bg-border"></div>
        <UiFilterChip :active="fulfillment === 'delivery'" :count="fulfillment_.delivery" @click="fulfillment = fulfillment === 'delivery' ? 'all' : 'delivery'">
          <template #icon><Icon name="lucide:bike" class="size-3.5" /></template>
          Entrega
        </UiFilterChip>
        <UiFilterChip :active="fulfillment === 'pickup'" :count="fulfillment_.pickup" @click="fulfillment = fulfillment === 'pickup' ? 'all' : 'pickup'">
          <template #icon><Icon name="lucide:shopping-bag" class="size-3.5" /></template>
          Retirada
        </UiFilterChip>
      </div>

      <template #end>
        <!-- Sinal de tempo-real: bolinha verde SÓ quando o SSE está vivo (honesto);
             senão, sinal neutro de que o board ainda atualiza sozinho a cada 30s. -->
        <span class="inline-flex items-center gap-1.5 text-xs text-muted-foreground" role="status" :title="realtimeView.title">
          <span class="size-1.5 rounded-full" :class="realtimeView.dotClass" />
          <span class="hidden md:inline">{{ realtimeView.label }}</span>
        </span>
        <AlertsBell />

        <!-- sort -->
        <div class="relative">
          <button
            type="button"
            class="inline-flex h-9 items-center gap-1.5 rounded-md border px-2.5 text-xs font-medium text-muted-foreground transition hover:bg-accent hover:text-foreground"
            aria-haspopup="menu"
            :aria-expanded="sortOpen"
            title="Ordenar (atalho: s)"
            @click="sortOpen = !sortOpen"
          >
            <Icon name="lucide:arrow-up-down" class="size-3.5" />
            <span class="hidden sm:inline">{{ sortLabel }}</span>
          </button>
          <div v-if="sortOpen" class="fixed inset-0 z-40" @click="sortOpen = false" />
          <div v-if="sortOpen" class="absolute right-0 z-50 mt-1 w-44 overflow-hidden rounded-md border bg-card py-1 shadow-lg" role="menu">
            <button
              v-for="opt in SORT_OPTIONS"
              :key="opt.key"
              type="button"
              role="menuitemradio"
              :aria-checked="sort === opt.key"
              class="flex w-full items-center justify-between px-3 py-1.5 text-left text-xs transition hover:bg-accent"
              @click="pickSort(opt.key)"
            >
              {{ opt.label }}
              <Icon v-if="sort === opt.key" name="lucide:check" class="size-3.5 text-primary" />
            </button>
          </div>
        </div>

        <UiIconButton icon="lucide:download" label="Exportar CSV" @click="exportCsv" />
        <UiIconButton icon="lucide:printer" label="Imprimir fila" @click="printQueue" />

        <!-- view-mode -->
        <div class="inline-flex h-9 items-center rounded-md border p-0.5">
          <button
            type="button"
            class="grid size-8 place-items-center rounded transition"
            :class="viewMode === 'board' ? 'bg-accent text-foreground' : 'text-muted-foreground hover:text-foreground'"
            aria-label="Ver em colunas"
            title="Colunas (atalho: v)"
            @click="viewMode = 'board'"
          >
            <Icon name="lucide:columns-3" class="size-4" />
          </button>
          <button
            type="button"
            class="grid size-8 place-items-center rounded transition"
            :class="viewMode === 'table' ? 'bg-accent text-foreground' : 'text-muted-foreground hover:text-foreground'"
            aria-label="Ver em tabela"
            title="Tabela (atalho: v)"
            @click="viewMode = 'table'"
          >
            <Icon name="lucide:table-2" class="size-4" />
          </button>
        </div>

        <UiIconButton icon="lucide:refresh-cw" label="Atualizar (atalho: r)" :spinning="pending" @click="refresh()" />
      </template>
    </UiToolbar>

    <!-- bulk action bar -->
    <div v-if="selected.size" class="flex shrink-0 flex-wrap items-center gap-2 border-b bg-primary/10 px-4 py-2 text-sm print:hidden">
      <Icon name="lucide:check-square" class="size-4 text-primary" />
      <span class="font-semibold">{{ selected.size }} selecionado{{ selected.size > 1 ? "s" : "" }}</span>
      <div class="ml-auto flex items-center gap-1.5">
        <button
          v-if="confirmableSel.length"
          type="button"
          class="inline-flex items-center gap-1.5 rounded-md border border-transparent bg-primary px-2.5 py-1.5 text-xs font-semibold text-primary-foreground transition hover:bg-primary/90"
          @click="bulkConfirm"
        >
          <Icon name="lucide:check" class="size-3.5" /> Confirmar {{ confirmableSel.length }}
        </button>
        <button
          v-if="advanceableSel.length"
          type="button"
          class="inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-xs font-semibold transition hover:bg-accent"
          @click="bulkAdvance"
        >
          <Icon name="lucide:arrow-right" class="size-3.5" /> Avançar {{ advanceableSel.length }}
        </button>
        <button type="button" class="rounded-md border px-2.5 py-1.5 text-xs font-medium text-muted-foreground transition hover:bg-accent" @click="clearSelection">
          Limpar
        </button>
      </div>
    </div>

    <section class="min-h-0 flex-1 overflow-auto p-3 md:p-4">
      <p v-if="pending && !zones.length" class="text-sm text-muted-foreground">Carregando…</p>
      <p v-else-if="error" class="rounded-md border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive dark:text-orange-400">
        Falha ao carregar a fila. Reconectando…
      </p>

      <template v-else>
        <!-- no results across all zones for the active filters -->
        <p v-if="hasFilter && !visibleCount" class="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground">
          Nenhum pedido para os filtros atuais.
          <button type="button" class="ml-1 font-medium text-primary hover:underline" @click="query = ''; channel = 'all'; fulfillment = 'all'">Limpar filtros</button>
        </p>

        <!-- board view (clean, default) -->
        <div v-else-if="viewMode === 'board'" class="grid gap-4 lg:grid-cols-3">
          <section v-for="zone in zones" :key="zone.key" class="flex min-w-0 flex-col gap-3">
            <div class="flex items-center gap-2 border-b pb-2">
              <Icon :name="zone.icon" class="size-4 text-muted-foreground" />
              <h2 class="text-sm font-bold uppercase tracking-wide">{{ zone.title }}</h2>
              <span class="grid min-w-5 place-items-center rounded-full bg-muted px-1.5 text-xs font-bold tabular-nums">{{ triaged(zone).length }}</span>
              <span class="ml-auto hidden truncate text-xs text-muted-foreground sm:block">{{ zone.subtitle }}</span>
            </div>

            <div v-if="!triaged(zone).length" class="grid place-items-center gap-1.5 rounded-lg border border-dashed py-10 text-center text-muted-foreground">
              <Icon name="lucide:check-circle-2" class="size-6" />
              <p class="text-sm">Nada por aqui agora.</p>
            </div>

            <OrderCard
              v-for="card in triaged(zone)"
              v-else
              :key="card.ref"
              :card="card"
              :busy="isBusy(card.ref)"
              :error="actionError(card.ref)"
              :selected="isSelected(card.ref)"
              @action="(action) => onAction(card.ref, action)"
              @dismiss-error="clearActionError(card.ref)"
              @toggle-select="toggleSelect(card.ref)"
              @toggle-assign="onToggleAssign(card)"
            />
          </section>
        </div>

        <!-- dense table view (power-user) -->
        <div v-else class="overflow-x-auto rounded-lg border bg-card">
          <table class="w-full border-collapse text-sm">
            <thead>
              <tr class="text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground [&>th]:sticky [&>th]:top-0 [&>th]:z-20 [&>th]:border-b [&>th]:bg-card">
                <th class="w-9 px-3 py-2">
                  <button
                    type="button"
                    class="grid size-4 place-items-center rounded border transition"
                    :class="allVisibleSelected ? 'border-primary bg-primary text-primary-foreground' : 'border-muted-foreground/40 hover:border-primary'"
                    :aria-label="allVisibleSelected ? 'Desmarcar todos' : 'Selecionar todos'"
                    :aria-pressed="allVisibleSelected"
                    @click="toggleSelectAll"
                  >
                    <Icon v-if="allVisibleSelected" name="lucide:check" class="size-3" />
                  </button>
                </th>
                <th class="px-3 py-2">Código</th>
                <th class="px-3 py-2">Etapa</th>
                <th class="px-3 py-2">Canal</th>
                <th class="px-3 py-2">Cliente</th>
                <th class="hidden px-3 py-2 lg:table-cell">Itens</th>
                <th class="px-3 py-2 text-right">Total</th>
                <th class="px-3 py-2 text-right">Tempo</th>
                <th class="px-3 py-2 text-right">Ações</th>
              </tr>
            </thead>
            <tbody>
              <template v-for="row in tableRows" :key="row.card.ref">
              <tr class="transition hover:bg-accent/40" :class="[actionError(row.card.ref) ? '' : 'border-b last:border-0', isSelected(row.card.ref) ? 'bg-primary/5' : '']">
                <td class="px-3 py-2">
                  <button
                    type="button"
                    class="grid size-4 place-items-center rounded border transition"
                    :class="isSelected(row.card.ref) ? 'border-primary bg-primary text-primary-foreground' : 'border-muted-foreground/40 hover:border-primary'"
                    :aria-label="isSelected(row.card.ref) ? 'Desmarcar pedido' : 'Selecionar pedido'"
                    :aria-pressed="isSelected(row.card.ref)"
                    @click="toggleSelect(row.card.ref)"
                  >
                    <Icon v-if="isSelected(row.card.ref)" name="lucide:check" class="size-3" />
                  </button>
                </td>
                <td class="px-3 py-2">
                  <NuxtLink :to="`/${row.card.ref}`" class="font-bold tabular-nums hover:underline" :aria-label="`Abrir pedido ${row.card.ref}`">
                    {{ splitRef(row.card.ref).code }}
                  </NuxtLink>
                </td>
                <td class="px-3 py-2">
                  <span class="inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium" :class="toneBadge(statusTone(row.card.status))">
                    {{ row.card.status_label }}
                  </span>
                </td>
                <td class="px-3 py-2">
                  <span class="inline-flex items-center gap-1 text-xs text-muted-foreground">
                    <Icon :name="`lucide:${lucideIcon(row.card.channel_icon)}`" class="size-3.5" />
                    {{ channelLabel(row.card.channel_ref) }}
                  </span>
                </td>
                <td class="max-w-40 px-3 py-2">
                  <span class="block truncate">{{ row.card.customer_name }}</span>
                  <span v-if="row.card.assigned_operator" class="mt-0.5 inline-flex items-center gap-1 text-xs text-primary">
                    <Icon name="lucide:user-check" class="size-3" />{{ row.card.assigned_operator }}
                  </span>
                </td>
                <td class="hidden max-w-56 truncate px-3 py-2 text-muted-foreground lg:table-cell">{{ row.card.items_summary }}</td>
                <td class="whitespace-nowrap px-3 py-2 text-right font-semibold tabular-nums">{{ row.card.total_display }}</td>
                <td class="px-3 py-2 text-right">
                  <span class="inline-flex items-center rounded border px-1.5 py-0.5 text-xs tabular-nums" :class="timerChip(timerTone(row.card.timer_class))">
                    {{ elapsedLabel(row.card.elapsed_seconds) }}
                  </span>
                </td>
                <td class="px-3 py-2">
                  <div class="flex items-center justify-end gap-1">
                    <button
                      type="button"
                      :disabled="isBusy(row.card.ref)"
                      class="grid size-7 place-items-center rounded border transition disabled:opacity-50"
                      :class="row.card.assigned_operator ? 'border-primary/40 bg-primary/10 text-primary' : 'text-muted-foreground hover:bg-accent'"
                      :aria-label="row.card.assigned_operator ? `Atendido por ${row.card.assigned_operator} — liberar` : 'Atender'"
                      :title="row.card.assigned_operator ? `${row.card.assigned_operator} — liberar` : 'Atender'"
                      @click="onToggleAssign(row.card)"
                    >
                      <Icon :name="row.card.assigned_operator ? 'lucide:user-check' : 'lucide:user-plus'" class="size-3.5" />
                    </button>
                    <button
                      v-for="a in cardAffordances(row.card)"
                      :key="a.ref"
                      type="button"
                      :disabled="isBusy(row.card.ref)"
                      class="grid size-7 place-items-center rounded border transition disabled:opacity-50"
                      :class="a.priority === 'primary' ? 'border-transparent bg-primary text-primary-foreground hover:bg-primary/90' : a.priority === 'danger' ? 'border-destructive/40 text-destructive hover:bg-destructive/10 dark:text-orange-300' : 'hover:bg-accent'"
                      :aria-label="a.label"
                      :title="a.label"
                      @click="onAction(row.card.ref, a.ref)"
                    >
                      <Icon :name="a.icon" class="size-3.5" />
                    </button>
                  </div>
                </td>
              </tr>
              <!-- action error sub-row: the backend's specific reason, inline -->
              <tr v-if="actionError(row.card.ref)" class="border-b last:border-0">
                <td colspan="9" class="px-3 pb-2">
                  <div class="flex items-start gap-1.5 rounded-md border border-destructive/40 bg-destructive/10 px-2 py-1.5 text-xs text-destructive dark:text-orange-300" role="alert">
                    <Icon name="lucide:alert-triangle" class="mt-px size-3.5 shrink-0" />
                    <span class="min-w-0 flex-1">{{ actionError(row.card.ref) }}</span>
                    <button type="button" class="shrink-0 rounded p-0.5 transition hover:bg-destructive/20" aria-label="Dispensar aviso" @click="clearActionError(row.card.ref)">
                      <Icon name="lucide:x" class="size-3.5" />
                    </button>
                  </div>
                </td>
              </tr>
              </template>
            </tbody>
          </table>
        </div>

        <!-- Encomendas: pedidos confirmados para datas futuras, fora das colunas
             do dia. Agrupadas pela data combinada; no dia, o despertador devolve
             o pedido ao fluxo normal do board. -->
        <section v-if="preordersCount" class="mt-6" data-preorders-section>
          <div class="flex items-center gap-2 border-b pb-2">
            <Icon name="lucide:calendar-clock" class="size-4 text-muted-foreground" />
            <h2 class="text-sm font-bold uppercase tracking-wide">Encomendas</h2>
            <span class="grid min-w-5 place-items-center rounded-full bg-muted px-1.5 text-xs font-bold tabular-nums">{{ preordersCount }}</span>
            <span class="ml-auto hidden truncate text-xs text-muted-foreground sm:block">Confirmadas para os próximos dias</span>
          </div>
          <div class="mt-3 grid gap-4 lg:grid-cols-3">
            <div v-for="group in triagedPreorders" :key="group.date" class="flex min-w-0 flex-col gap-3">
              <h3 class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{{ group.label }}</h3>
              <OrderCard
                v-for="card in group.cards"
                :key="card.ref"
                :card="card"
                :busy="isBusy(card.ref)"
                :error="actionError(card.ref)"
                :selected="isSelected(card.ref)"
                @action="(action) => onAction(card.ref, action)"
                @dismiss-error="clearActionError(card.ref)"
                @toggle-select="toggleSelect(card.ref)"
                @toggle-assign="onToggleAssign(card)"
              />
            </div>
          </div>
        </section>
      </template>
    </section>

    <!-- reject dialog -->
    <UiDialog :open="rejectRef != null" @update:open="(v) => { if (!v) rejectRef = null }">
      <UiDialogContent class="sm:max-w-md">
        <UiDialogHeader>
          <UiDialogTitle>Recusar pedido {{ rejectRef }}</UiDialogTitle>
          <UiDialogDescription>
            {{ isMarketplaceReject ? "Escolha o motivo exigido pelo iFood — ele é enviado ao marketplace." : "Informe o motivo — o cliente é avisado." }}
          </UiDialogDescription>
        </UiDialogHeader>
        <p v-if="rejectReasonsLoading" class="text-sm text-muted-foreground">Carregando motivos do iFood…</p>
        <!-- Marketplace (iFood): coded reason picker from the provider's live list -->
        <select
          v-else-if="isMarketplaceReject"
          v-model="rejectCode"
          class="w-full rounded-md border bg-background p-2.5 text-sm outline-none focus:ring-1 focus:ring-ring"
          aria-label="Motivo do cancelamento (iFood)"
          @change="onRejectCodeChange"
        >
          <option value="" disabled>Selecione o motivo…</option>
          <option v-for="r in rejectReasons" :key="r.code" :value="r.code">{{ r.description }}</option>
        </select>
        <!-- Other channels: free-text reason -->
        <textarea
          v-else
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
            :disabled="!canConfirmReject"
            class="rounded-md border border-transparent bg-destructive px-3 py-2 text-sm font-semibold text-white transition hover:bg-destructive/90 disabled:opacity-50"
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
