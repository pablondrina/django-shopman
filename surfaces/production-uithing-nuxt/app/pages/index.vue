<script setup lang="ts">
// Produção — A GRADE (decisão Pablo 2026-07-03: substitui as antigas telas de
// planejamento e chão). SKU × Sugerido · Planejado · Iniciado · Concluído,
// nomenclatura e guardrails do OPERATION-DOMAIN-PLAN:
//   · colunas cortadas por permissão (faixas de papel — o board entrega
//     `access` por coluna);
//   · célula é BOTÃO, nunca tabela aberta: informar quantidade passa por um
//     overlay com confirmação explícita (à prova de toque enfarinhado), e cada
//     informe vira evento imutável no ledger (actor + timestamp → BI);
//   · a sequência de ataque é livre — o colaborador informa conforme faz.
// O detalhe vivo do lote iniciado (timer, etapa, avançar/estornar) mora no
// overlay da célula Iniciado — o antigo card do chão, condensado.
import {
  elapsedLabel,
  matchesRowQuery,
  rowCommitments,
  rowHasActivity,
  startableWorkOrder,
  timerChip,
  timerTone,
} from "~/presentation/production";
import type {
  ProductionKDSCardProjection,
  ProductionMatrixRowProjection,
  ProductionShortageError,
  ProductionSuggestionProjection,
} from "~/types/production";

const { board, rows, counts, dateDisplay, selectedDate, pending, error, refresh, isBusy, plan, start } =
  useProductionBoard();
const kds = useProductionKds();

const access = computed(() => board.value?.access ?? null);

const route = useRoute();
const query = ref(typeof route.query.q === "string" ? route.query.q : "");
watch(() => route.query.q, (q) => { if (typeof q === "string") query.value = q; });

// Horizonte: hoje / amanhã / qualquer data.
function isoFor(offsetDays: number): string {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}
const dateChips = [
  { iso: isoFor(0), label: "Hoje" },
  { iso: isoFor(1), label: "Amanhã" },
];

const showAll = ref(false);
const visibleRows = computed<ProductionMatrixRowProjection[]>(() =>
  rows.value
    .filter((r) => showAll.value || rowHasActivity(r))
    .filter((r) => matchesRowQuery(r, query.value)),
);

// ── Overlays (um por intenção; a célula só declara o que quer) ─────────────
const explaining = ref<ProductionSuggestionProjection | null>(null);
const planRow = ref<ProductionMatrixRowProjection | null>(null);
const planQty = ref("");
const startRow = ref<ProductionMatrixRowProjection | null>(null);
const startQty = ref("");
const startedRow = ref<ProductionMatrixRowProjection | null>(null);
const finishRow = ref<ProductionMatrixRowProjection | null>(null);
const finishQty = ref("");
const voidReason = ref("");
const voidConfirming = ref(false);
const commitmentsRow = ref<ProductionMatrixRowProjection | null>(null);
const shortage = ref<ProductionShortageError | null>(null);

const commitmentsList = computed(() =>
  commitmentsRow.value ? rowCommitments(commitmentsRow.value) : [],
);

// Card vivo do KDS para o lote iniciado da linha (timer/etapa/ações).
const startedCard = computed<ProductionKDSCardProjection | null>(() => {
  const wo = startedRow.value?.started_orders[0];
  if (!wo) return null;
  return kds.cards.value.find((c) => c.pk === wo.pk) ?? null;
});

function openPlan(row: ProductionMatrixRowProjection) {
  planRow.value = row;
  planQty.value = row.planned_qty !== "0" ? row.planned_qty : (row.suggestion?.quantity ?? "");
}

async function confirmPlan() {
  const row = planRow.value;
  if (!row || row.recipe_pk == null || !board.value || !planQty.value.trim()) return;
  const res = await plan(row.output_sku, {
    recipe_id: row.recipe_pk,
    quantity: planQty.value.trim(),
    target_date: board.value.selected_date,
    position_ref: board.value.selected_position_ref || undefined,
    source: row.suggestion && planQty.value.trim() === row.suggestion.quantity ? "suggested" : undefined,
  });
  if (res.ok) {
    planRow.value = null;
    useSonner.success(`Planejado: ${row.output_sku} × ${planQty.value.trim()}`);
  } else if (res.shortage) {
    planRow.value = null;
    shortage.value = res.shortage;
  }
}

function openStart(row: ProductionMatrixRowProjection) {
  startRow.value = row;
  startQty.value = startableWorkOrder(row)?.planned_qty ?? row.planned_qty;
}

async function confirmStart() {
  const row = startRow.value;
  const wo = row && startableWorkOrder(row);
  if (!row || !wo || !startQty.value.trim()) return;
  const res = await start(row.output_sku, wo.pk, startQty.value.trim());
  if (res.ok) {
    startRow.value = null;
    kds.refresh();
    useSonner.success(`Iniciado: ${row.output_sku} × ${startQty.value.trim()}`);
  }
}

function openFinish(row: ProductionMatrixRowProjection) {
  startedRow.value = null;
  finishRow.value = row;
  finishQty.value = row.started_qty !== "0" ? row.started_qty : row.planned_qty;
}

async function confirmFinish(force = false) {
  const row = finishRow.value;
  const wo = row?.started_orders[0];
  if (!row || !wo || !finishQty.value.trim()) return;
  const res = await kds.finish(wo.pk, finishQty.value.trim(), force);
  if (res.ok) {
    finishRow.value = null;
    refresh();
    useSonner.success(`Concluído: ${row.output_sku} × ${finishQty.value.trim()}`);
  } else if (res.shortage) {
    finishRow.value = null;
    shortage.value = res.shortage;
  }
}

async function overrideShortage() {
  const s = shortage.value;
  shortage.value = null;
  if (!s) return;
  const row = rows.value.find((r) =>
    r.started_orders.some((wo) => wo.ref === (s as { work_order_ref?: string }).work_order_ref),
  );
  if (row) {
    finishRow.value = row;
    await confirmFinish(true);
  }
}

async function confirmVoid() {
  const row = startedRow.value;
  const wo = row?.started_orders[0];
  if (!row || !wo) return;
  const res = await kds.voidOrder(wo.pk, voidReason.value.trim() || "Estornado pelo operador");
  if (res.ok) {
    startedRow.value = null;
    voidConfirming.value = false;
    voidReason.value = "";
    refresh();
    useSonner.success(`Estornado: ${row.output_sku}`);
  }
}

async function advanceStep() {
  const card = startedCard.value;
  if (!card) return;
  await kds.advanceStep(card.pk);
  refresh();
}

function cellQty(value: string): string {
  return value === "0" ? "—" : value;
}
</script>

<template>
  <main class="flex min-h-screen flex-col">
    <ProductionHeader
      v-model:query="query"
      title="Produção"
      :count="counts?.started ?? 0"
      count-label="em produção"
      :pending="pending"
      @refresh="refresh(); kds.refresh();"
    />

    <section class="min-h-0 flex-1 overflow-auto p-3 md:p-4">
      <div class="mb-3 flex flex-wrap items-center gap-3">
        <div class="flex items-center gap-1 rounded-lg border bg-background p-0.5" role="group" aria-label="Data da produção">
          <button
            v-for="chip in dateChips"
            :key="chip.iso"
            type="button"
            class="rounded-md px-2.5 py-1.5 text-sm font-medium transition"
            :class="selectedDate === chip.iso ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-accent hover:text-foreground'"
            :aria-pressed="selectedDate === chip.iso"
            @click="selectedDate = chip.iso"
          >
            {{ chip.label }}
          </button>
          <input
            v-model="selectedDate"
            type="date"
            class="h-8 rounded-md border-0 bg-transparent px-1.5 text-sm text-muted-foreground outline-none focus:ring-1 focus:ring-ring"
            aria-label="Outra data"
          />
        </div>
        <span class="text-sm text-muted-foreground">{{ dateDisplay }}</span>
        <span v-if="counts" class="text-sm tabular-nums text-muted-foreground">
          Plan {{ counts.planned_qty }} · Inic {{ counts.started_qty }} · Concl {{ counts.finished_qty }}
        </span>
        <label class="ml-auto inline-flex cursor-pointer items-center gap-2 text-sm text-muted-foreground">
          <input v-model="showAll" type="checkbox" class="size-4 rounded border" />
          Mostrar todas as receitas
        </label>
      </div>

      <p v-if="pending && !rows.length" class="text-sm text-muted-foreground">Carregando…</p>
      <p v-else-if="error" class="rounded-md border border-red-500/30 bg-red-500/5 p-4 text-sm text-red-700 dark:text-red-400">
        Falha ao carregar a produção. Reconectando…
      </p>

      <div v-else-if="!visibleRows.length" class="grid place-items-center gap-2 rounded-lg border border-dashed py-16 text-center text-muted-foreground">
        <Icon name="lucide:layout-grid" class="size-8" />
        <p class="text-base font-medium">Nada em produção nesta data.</p>
        <button type="button" class="text-sm text-primary underline-offset-2 hover:underline" @click="showAll = true">
          Ver todas as receitas para planejar
        </button>
      </div>

      <div v-else class="overflow-hidden rounded-lg border">
        <table class="w-full text-sm">
          <thead class="bg-muted/50 text-left text-xs uppercase tracking-wide text-muted-foreground">
            <tr>
              <th class="px-3 py-2 font-semibold">Produto</th>
              <th v-if="access?.can_view_suggested" class="px-3 py-2 text-right font-semibold">Sugerido</th>
              <th v-if="access?.can_view_planned" class="px-3 py-2 text-right font-semibold">Planejado</th>
              <th v-if="access?.can_view_started" class="px-3 py-2 text-right font-semibold">Iniciado</th>
              <th v-if="access?.can_view_finished" class="px-3 py-2 text-right font-semibold">Concluído</th>
            </tr>
          </thead>
          <tbody class="divide-y">
            <tr v-for="row in visibleRows" :key="row.output_sku" class="hover:bg-muted/30">
              <td class="px-3 py-2">
                <p class="font-bold">{{ row.output_sku }}</p>
                <p class="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <span class="truncate">{{ row.recipe_name }}</span>
                  <button
                    v-if="rowCommitments(row).length"
                    type="button"
                    class="inline-flex shrink-0 items-center gap-1 rounded-md border border-primary/30 bg-primary/5 px-1.5 py-0.5 text-[0.7rem] font-medium text-primary transition hover:bg-primary/10"
                    :aria-label="`Ver ${rowCommitments(row).length} pedidos vinculados a ${row.output_sku}`"
                    @click="commitmentsRow = row"
                  >
                    <Icon name="lucide:shopping-bag" class="size-3" />
                    {{ rowCommitments(row).length }}
                  </button>
                </p>
              </td>

              <!-- Sugerido: leitura + explicação ("por que este número?") -->
              <td v-if="access?.can_view_suggested" class="px-3 py-2 text-right">
                <button
                  v-if="row.suggestion"
                  type="button"
                  class="group inline-flex flex-col items-end rounded-md px-1.5 py-0.5 transition hover:bg-accent"
                  :aria-label="`Por que ${row.suggestion.quantity} de ${row.recipe_name}?`"
                  @click="explaining = row.suggestion"
                >
                  <span class="inline-flex items-center gap-1 tabular-nums text-muted-foreground">
                    {{ row.suggestion.quantity }}
                    <Icon name="lucide:info" class="size-3 text-muted-foreground/60 transition group-hover:text-foreground" />
                  </span>
                </button>
                <span v-else class="text-muted-foreground">—</span>
              </td>

              <!-- Planejado: botão → overlay de quantidade -->
              <td v-if="access?.can_view_planned" class="px-3 py-2 text-right">
                <button
                  v-if="access?.can_edit_planned && row.recipe_pk != null"
                  type="button"
                  class="min-w-14 rounded-md border px-2 py-1 text-right font-semibold tabular-nums transition hover:bg-accent disabled:opacity-50"
                  :class="row.planned_qty !== '0' ? 'text-blue-700 dark:text-blue-300' : 'text-muted-foreground'"
                  :disabled="isBusy(row.output_sku)"
                  :aria-label="`Planejar ${row.output_sku} (atual: ${row.planned_qty})`"
                  @click="openPlan(row)"
                >
                  {{ cellQty(row.planned_qty) }}
                </button>
                <span v-else class="font-semibold tabular-nums" :class="row.planned_qty !== '0' ? 'text-blue-700 dark:text-blue-300' : 'text-muted-foreground'">
                  {{ cellQty(row.planned_qty) }}
                </span>
              </td>

              <!-- Iniciado: iniciar (se há planejado) ou gerir o lote vivo -->
              <td v-if="access?.can_view_started" class="px-3 py-2 text-right">
                <button
                  v-if="row.started_orders.length"
                  type="button"
                  class="min-w-14 rounded-md border border-amber-500/40 bg-amber-500/5 px-2 py-1 text-right font-semibold tabular-nums text-amber-700 transition hover:bg-amber-500/10 dark:text-amber-300"
                  :aria-label="`Gerir lote iniciado de ${row.output_sku}`"
                  @click="startedRow = row; voidConfirming = false; kds.refresh()"
                >
                  {{ cellQty(row.started_qty) }}
                </button>
                <button
                  v-else-if="access?.can_edit_started && startableWorkOrder(row)"
                  type="button"
                  class="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-sm font-medium transition hover:bg-accent disabled:opacity-50"
                  :disabled="isBusy(row.output_sku)"
                  :aria-label="`Iniciar produção de ${row.output_sku}`"
                  @click="openStart(row)"
                >
                  <Icon name="lucide:play" class="size-3.5" /> Iniciar
                </button>
                <span v-else class="text-muted-foreground">—</span>
              </td>

              <!-- Concluído: informar produzido -->
              <td v-if="access?.can_view_finished" class="px-3 py-2 text-right">
                <button
                  v-if="access?.can_edit_finished && row.started_orders.length"
                  type="button"
                  class="min-w-14 rounded-md border px-2 py-1 text-right font-semibold tabular-nums transition hover:bg-accent"
                  :class="row.finished_qty !== '0' ? 'text-green-700 dark:text-green-300' : 'text-muted-foreground'"
                  :aria-label="`Concluir produção de ${row.output_sku}`"
                  @click="openFinish(row)"
                >
                  {{ cellQty(row.finished_qty) }}
                </button>
                <span v-else class="font-semibold tabular-nums" :class="row.finished_qty !== '0' ? 'text-green-700 dark:text-green-300' : 'text-muted-foreground'">
                  {{ cellQty(row.finished_qty) }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
        <p v-if="query && !visibleRows.length" class="border-t p-3 text-center text-sm text-muted-foreground">
          Nenhum resultado para “{{ query.trim() }}”.
        </p>
      </div>
    </section>

    <!-- planejar -->
    <UiDialog :open="planRow != null" @update:open="(v) => { if (!v) planRow = null }">
      <UiDialogContent class="sm:max-w-sm">
        <UiDialogHeader>
          <UiDialogTitle>Planejar {{ planRow?.output_sku }}</UiDialogTitle>
          <UiDialogDescription>
            {{ planRow?.recipe_name }} · {{ dateDisplay }}
            <template v-if="planRow?.suggestion"> · sugestão {{ planRow.suggestion.quantity }}</template>
          </UiDialogDescription>
        </UiDialogHeader>
        <input
          v-model="planQty"
          type="text"
          inputmode="decimal"
          placeholder="Quantidade"
          class="w-full rounded-md border bg-background p-2.5 text-lg font-semibold tabular-nums outline-none focus:ring-1 focus:ring-ring"
          aria-label="Quantidade planejada"
        />
        <UiDialogFooter>
          <button type="button" class="rounded-md border px-3 py-2 text-sm font-medium transition hover:bg-accent" @click="planRow = null">Cancelar</button>
          <button
            type="button"
            :disabled="!planQty.trim()"
            class="rounded-md border border-transparent bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
            @click="confirmPlan()"
          >
            Salvar planejado
          </button>
        </UiDialogFooter>
      </UiDialogContent>
    </UiDialog>

    <!-- iniciar -->
    <UiDialog :open="startRow != null" @update:open="(v) => { if (!v) startRow = null }">
      <UiDialogContent class="sm:max-w-sm">
        <UiDialogHeader>
          <UiDialogTitle>Iniciar {{ startRow?.output_sku }}</UiDialogTitle>
          <UiDialogDescription>Quantidade que entra em produção agora.</UiDialogDescription>
        </UiDialogHeader>
        <input
          v-model="startQty"
          type="text"
          inputmode="decimal"
          placeholder="Quantidade"
          class="w-full rounded-md border bg-background p-2.5 text-lg font-semibold tabular-nums outline-none focus:ring-1 focus:ring-ring"
          aria-label="Quantidade iniciada"
        />
        <UiDialogFooter>
          <button type="button" class="rounded-md border px-3 py-2 text-sm font-medium transition hover:bg-accent" @click="startRow = null">Cancelar</button>
          <button
            type="button"
            :disabled="!startQty.trim()"
            class="rounded-md border border-transparent bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
            @click="confirmStart()"
          >
            Iniciar produção
          </button>
        </UiDialogFooter>
      </UiDialogContent>
    </UiDialog>

    <!-- lote iniciado (o antigo card do chão, condensado) -->
    <UiDialog :open="startedRow != null" @update:open="(v) => { if (!v) { startedRow = null; voidConfirming = false } }">
      <UiDialogContent class="sm:max-w-md">
        <UiDialogHeader>
          <UiDialogTitle>{{ startedRow?.output_sku }} em produção</UiDialogTitle>
          <UiDialogDescription>
            #{{ startedRow?.started_orders[0]?.ref }} · {{ startedRow?.started_qty }} un. iniciadas
          </UiDialogDescription>
        </UiDialogHeader>

        <div v-if="startedCard" class="flex flex-col gap-2">
          <div class="flex items-center justify-between gap-2 text-sm">
            <span class="truncate font-medium">
              <template v-if="startedCard.total_steps > 0 && startedCard.current_step_index">
                {{ startedCard.current_step_index }}/{{ startedCard.total_steps }} · {{ startedCard.current_step_name || startedCard.current_step }}
              </template>
              <template v-else>{{ startedCard.current_step || "Produção" }}</template>
            </span>
            <span class="shrink-0 rounded-md border px-2 py-0.5 text-xs font-semibold tabular-nums" :class="timerChip(timerTone(startedCard.timer_class))">
              {{ elapsedLabel(startedCard.elapsed_seconds) }}
            </span>
          </div>
          <button
            v-if="startedCard.next_step_name"
            type="button"
            class="inline-flex items-center justify-center gap-1.5 rounded-md border px-3 py-2 text-sm font-medium transition hover:bg-accent"
            @click="advanceStep()"
          >
            <Icon name="lucide:arrow-right" class="size-4" /> Avançar para {{ startedCard.next_step_name }}
          </button>
        </div>

        <div v-if="startedRow && rowCommitments(startedRow).length" class="flex items-start gap-2 rounded-md border border-primary/30 bg-primary/5 p-2.5 text-sm">
          <Icon name="lucide:shopping-bag" class="mt-0.5 size-4 shrink-0 text-primary" />
          <span>{{ rowCommitments(startedRow).length }} pedido{{ rowCommitments(startedRow).length > 1 ? "s aguardam" : " aguarda" }} este lote.</span>
        </div>

        <div v-if="voidConfirming" class="flex flex-col gap-2">
          <p class="flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-2.5 text-sm text-amber-700 dark:text-amber-300">
            <Icon name="lucide:triangle-alert" class="mt-0.5 size-4 shrink-0" />
            <span>A ordem sai da produção e o vínculo com pedidos é desfeito.</span>
          </p>
          <textarea
            v-model="voidReason"
            rows="2"
            placeholder="Motivo do estorno…"
            class="w-full rounded-md border bg-background p-2.5 text-sm outline-none focus:ring-1 focus:ring-ring"
            aria-label="Motivo do estorno"
          />
        </div>

        <UiDialogFooter class="gap-2">
          <button
            v-if="!voidConfirming"
            type="button"
            class="mr-auto rounded-md border px-3 py-2 text-sm font-medium text-red-700 transition hover:bg-red-500/10 dark:text-red-300"
            @click="voidConfirming = true"
          >
            Estornar…
          </button>
          <button
            v-else
            type="button"
            class="mr-auto rounded-md border border-transparent bg-red-600 px-3 py-2 text-sm font-semibold text-white transition hover:bg-red-700"
            @click="confirmVoid()"
          >
            Confirmar estorno
          </button>
          <button type="button" class="rounded-md border px-3 py-2 text-sm font-medium transition hover:bg-accent" @click="startedRow = null; voidConfirming = false">Fechar</button>
          <button
            v-if="access?.can_edit_finished && startedRow"
            type="button"
            class="rounded-md border border-transparent bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90"
            @click="openFinish(startedRow)"
          >
            Concluir…
          </button>
        </UiDialogFooter>
      </UiDialogContent>
    </UiDialog>

    <!-- concluir -->
    <UiDialog :open="finishRow != null" @update:open="(v) => { if (!v) finishRow = null }">
      <UiDialogContent class="sm:max-w-sm">
        <UiDialogHeader>
          <UiDialogTitle>Concluir {{ finishRow?.output_sku }}</UiDialogTitle>
          <UiDialogDescription>Quantidade efetivamente produzida (#{{ finishRow?.started_orders[0]?.ref }}).</UiDialogDescription>
        </UiDialogHeader>
        <input
          v-model="finishQty"
          type="text"
          inputmode="decimal"
          placeholder="Ex.: 100"
          class="w-full rounded-md border bg-background p-2.5 text-lg font-semibold tabular-nums outline-none focus:ring-1 focus:ring-ring"
          aria-label="Quantidade concluída"
        />
        <UiDialogFooter>
          <button type="button" class="rounded-md border px-3 py-2 text-sm font-medium transition hover:bg-accent" @click="finishRow = null">Cancelar</button>
          <button
            type="button"
            :disabled="!finishQty.trim()"
            class="rounded-md border border-transparent bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
            @click="confirmFinish(false)"
          >
            Concluir produção
          </button>
        </UiDialogFooter>
      </UiDialogContent>
    </UiDialog>

    <!-- pedidos vinculados -->
    <UiDialog :open="commitmentsRow != null" @update:open="(v) => { if (!v) commitmentsRow = null }">
      <UiDialogContent class="sm:max-w-md">
        <UiDialogHeader>
          <UiDialogTitle>Pedidos aguardando {{ commitmentsRow?.output_sku }}</UiDialogTitle>
          <UiDialogDescription>Encomendas confirmadas vinculadas à produção desta ficha.</UiDialogDescription>
        </UiDialogHeader>
        <ul class="flex flex-col gap-2 text-sm">
          <li v-for="commitment in commitmentsList" :key="commitment.ref" class="flex items-center justify-between gap-3 rounded-md border p-2.5">
            <span class="inline-flex items-center gap-2">
              <Icon name="lucide:shopping-bag" class="size-4 text-muted-foreground" />
              <span class="font-medium">{{ commitment.ref }}</span>
              <UiBadge variant="outline" class="px-1.5 py-0 text-[0.65rem]">{{ commitment.status_label }}</UiBadge>
            </span>
            <span class="tabular-nums text-muted-foreground">{{ commitment.qty_required }} un.</span>
          </li>
        </ul>
        <UiDialogFooter>
          <button type="button" class="rounded-md border px-3 py-2 text-sm font-medium transition hover:bg-accent" @click="commitmentsRow = null">Fechar</button>
        </UiDialogFooter>
      </UiDialogContent>
    </UiDialog>

    <!-- explicação da sugestão -->
    <UiDialog :open="explaining != null" @update:open="(v) => { if (!v) explaining = null }">
      <UiDialogContent class="sm:max-w-md">
        <UiDialogHeader>
          <UiDialogTitle>Por que {{ explaining?.quantity }}?</UiDialogTitle>
          <UiDialogDescription>
            {{ explaining?.recipe_name }} · confiança {{ explaining?.confidence?.toLowerCase() }}
          </UiDialogDescription>
        </UiDialogHeader>
        <ul v-if="explaining?.explanation_parts?.length" class="flex flex-col gap-2 text-sm">
          <li v-for="part in explaining.explanation_parts" :key="part" class="flex items-start gap-2">
            <Icon name="lucide:corner-down-right" class="mt-0.5 size-4 shrink-0 text-muted-foreground" />
            <span>{{ part }}</span>
          </li>
        </ul>
        <p v-else class="text-sm text-muted-foreground">
          Ainda sem histórico suficiente para explicar — a sugestão usa apenas a margem padrão.
        </p>
        <UiDialogFooter>
          <button
            v-if="access?.can_edit_planned"
            type="button"
            class="mr-auto rounded-md border border-transparent bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90"
            @click="(() => { const row = rows.find(r => r.suggestion === explaining); explaining = null; if (row) openPlan(row); })()"
          >
            Planejar esta sugestão
          </button>
          <button type="button" class="rounded-md border px-3 py-2 text-sm font-medium transition hover:bg-accent" @click="explaining = null">Fechar</button>
        </UiDialogFooter>
      </UiDialogContent>
    </UiDialog>

    <ShortageDialog :shortage="shortage" @update:open="(v) => { if (!v) shortage = null }" @confirm="overrideShortage" />
  </main>
</template>
