<script setup lang="ts">
// A GRADE por etapa — um motor, três lentes (refinos Pablo 2026-07-03):
//   PRODUTO | leitura | AÇÃO — cada lente tem UMA coluna de leitura e UMA de
//   ação com verbo no cabeçalho:
//   · plan     (Planejamento): SUGERIDO   | PLANEJAR   — todos os SKUs;
//   · produce  (Produção):     PLANEJADO  | PROCESSAR  — só linhas com número;
//   · expedite (Expedição):    PROCESSADO | EXPEDIR    — só linhas com número.
// A ação abre overlay com quantidade em stepper touch (+/−) e confirmação
// explícita; cada informe vira evento imutável (actor + timestamp → BI).
// Instruções específicas do SKU (peso de corte etc.) terão casa neste overlay
// (estudo de notação de pâtonnage pendente). Nomenclatura interna do sistema
// intacta (planned/started/finished) — as lentes são linguagem de UI.
import {
  elapsedLabel,
  matchesRowQuery,
  rowCommitments,
  rowCommittedUnits,
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

const props = defineProps<{ stage: "plan" | "produce" | "expedite"; title: string }>();

const { board, rows, counts, dateDisplay, selectedDate, pending, error, refresh, isBusy, plan, start } =
  useProductionBoard();
const kds = useProductionKds();

const access = computed(() => board.value?.access ?? null);

const route = useRoute();
const query = ref(typeof route.query.q === "string" ? route.query.q : "");
watch(() => route.query.q, (q) => { if (typeof q === "string") query.value = q; });

// ── Data: Hoje · Amanhã · Outra data (chip com o picker embutido) ───────────
function isoFor(offsetDays: number): string {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}
const todayISO = isoFor(0);
const tomorrowISO = isoFor(1);
const isCustomDate = computed(() => selectedDate.value !== todayISO && selectedDate.value !== tomorrowISO);
const customDateInput = ref<HTMLInputElement | null>(null);
function openCustomDate() {
  customDateInput.value?.showPicker?.();
  customDateInput.value?.focus();
}

// ── Filtro por ficha-base (higiene visual por grupo de massa) ───────────────
const baseFilter = ref("");
const baseOptions = computed(() => board.value?.base_recipes ?? []);

// ── Papéis de coluna por lente (cruzados com a permissão) ───────────────────
const lens = computed(() => {
  if (props.stage === "plan") {
    return {
      read: { key: "suggested", label: "Sugerido", visible: !!access.value?.can_view_suggested },
      action: { key: "planned", label: "Planejar", visible: !!access.value?.can_view_planned, editable: !!access.value?.can_edit_planned },
    } as const;
  }
  if (props.stage === "produce") {
    return {
      read: { key: "planned", label: "Planejado", visible: !!access.value?.can_view_planned },
      action: { key: "started", label: "Processar", visible: !!access.value?.can_view_started, editable: !!access.value?.can_edit_started },
    } as const;
  }
  return {
    read: { key: "started", label: "Processado", visible: !!access.value?.can_view_started },
    action: { key: "finished", label: "Expedir", visible: !!access.value?.can_view_finished, editable: !!access.value?.can_edit_finished },
  } as const;
});

// Linhas por lente: Planejamento vê TODOS os SKUs; Produção/Expedição só quem
// tem número relevante (higiene de foco na bancada).
const stageRows = computed<ProductionMatrixRowProjection[]>(() => {
  let base = rows.value.filter((r) => matchesRowQuery(r, query.value));
  if (baseFilter.value) {
    base = base.filter((r) => r.base_usages.some((usage) => usage.output_sku === baseFilter.value));
  }
  if (props.stage === "produce") {
    return base.filter((r) => r.planned_qty !== "0" || r.started_qty !== "0");
  }
  if (props.stage === "expedite") {
    return base.filter((r) => r.started_qty !== "0" || r.finished_qty !== "0");
  }
  return base;
});

const emptyCopy = computed(() =>
  props.stage === "plan"
    ? { text: "Nenhuma receita ativa.", cta: "", to: "" }
    : props.stage === "produce"
      ? { text: "Nada planejado para processar nesta data.", cta: "Ir para o Planejamento", to: "/planejamento" }
      : { text: "Nada processado para expedir nesta data.", cta: "Ir para a Produção", to: "/" },
);

// ── Overlays ────────────────────────────────────────────────────────────────
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

const startedCard = computed<ProductionKDSCardProjection | null>(() => {
  const wo = startedRow.value?.started_orders[0];
  if (!wo) return null;
  return kds.cards.value.find((c) => c.pk === wo.pk) ?? null;
});

// Stepper touch: quantidade sempre editável com +/− generosos.
// (Recebe o NOME do campo — no template o Vue desembrulha refs, então passar
// `planQty` entregaria a string, não o ref.)
const qtyFields = { plan: planQty, start: startQty, finish: finishQty } as const;
function bump(field: keyof typeof qtyFields, delta: number) {
  const target = qtyFields[field];
  const current = parseFloat(target.value.replace(",", ".")) || 0;
  const next = Math.max(0, current + delta);
  target.value = Number.isInteger(next) ? String(next) : next.toFixed(3).replace(/\.?0+$/, "");
}

function openPlan(row: ProductionMatrixRowProjection) {
  planRow.value = row;
  planQty.value = row.planned_qty !== "0" ? row.planned_qty : (row.suggestion?.quantity ?? "0");
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
    useSonner.success(`Em processo: ${row.output_sku} × ${startQty.value.trim()}`);
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
    useSonner.success(`Expedido: ${row.output_sku} × ${finishQty.value.trim()}`);
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

function onAction(row: ProductionMatrixRowProjection) {
  if (props.stage === "plan") return openPlan(row);
  if (props.stage === "produce") {
    if (row.started_orders.length) {
      startedRow.value = row;
      voidConfirming.value = false;
      kds.refresh();
      return;
    }
    return openStart(row);
  }
  return openFinish(row);
}

function rowValue(row: ProductionMatrixRowProjection, key: string): string {
  if (key === "suggested") return row.suggestion?.quantity ?? "0";
  if (key === "planned") return row.planned_qty;
  if (key === "started") return row.started_qty;
  return row.finished_qty;
}

function actionEnabled(row: ProductionMatrixRowProjection): boolean {
  if (!lens.value.action.editable) return false;
  if (props.stage === "plan") return row.recipe_pk != null;
  if (props.stage === "produce") return !!row.started_orders.length || !!startableWorkOrder(row);
  return !!row.started_orders.length;
}

const ACTION_VERB: Record<string, string> = { plan: "Planejar", produce: "Processar", expedite: "Expedir" };

function cellQty(value: string): string {
  return value === "0" ? "—" : value;
}

// ── Anatomia única de célula (números neutros; cor não codifica coluna) ─────
const CELL = "inline-flex h-10 min-w-20 items-center justify-end gap-1.5 rounded-md px-2.5 font-semibold tabular-nums transition";
const CELL_ACTION = `${CELL} border hover:bg-accent disabled:opacity-50`;
const CELL_READ = `${CELL} border border-transparent`;

// Progresso do dia: noção visual do quanto falta (expedido ÷ total do dia).
const dayProgress = computed(() => {
  const parse = (v?: string) => parseFloat((v ?? "0").replace(",", ".")) || 0;
  const planned = parse(counts.value?.planned_qty) + parse(counts.value?.started_qty) + parse(counts.value?.finished_qty);
  const finished = parse(counts.value?.finished_qty);
  if (!planned) return null;
  return { pct: Math.min(100, Math.round((finished / planned) * 100)), finished, planned };
});

const headerCount = computed(() => {
  if (props.stage === "plan") return { count: counts.value?.planned ?? 0, label: "planejados" };
  if (props.stage === "produce") return { count: counts.value?.started ?? 0, label: "em processo" };
  return { count: counts.value?.finished ?? 0, label: "expedidos" };
});
</script>

<template>
  <main class="flex min-h-screen flex-col">
    <ProductionHeader
      v-model:query="query"
      :title="title"
      :count="headerCount.count"
      :count-label="headerCount.label"
      :pending="pending"
      @refresh="refresh(); kds.refresh();"
    />

    <section class="min-h-0 flex-1 overflow-auto p-3 md:p-4">
      <div class="mb-3 flex flex-wrap items-center gap-3">
        <div class="flex items-center gap-1 rounded-lg border bg-background p-0.5" role="group" aria-label="Data">
          <button
            type="button"
            class="rounded-md px-2.5 py-1.5 text-sm font-medium transition"
            :class="selectedDate === todayISO ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-accent hover:text-foreground'"
            :aria-pressed="selectedDate === todayISO"
            @click="selectedDate = todayISO"
          >
            Hoje
          </button>
          <button
            type="button"
            class="rounded-md px-2.5 py-1.5 text-sm font-medium transition"
            :class="selectedDate === tomorrowISO ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-accent hover:text-foreground'"
            :aria-pressed="selectedDate === tomorrowISO"
            @click="selectedDate = tomorrowISO"
          >
            Amanhã
          </button>
          <button
            type="button"
            class="relative rounded-md px-2.5 py-1.5 text-sm font-medium transition"
            :class="isCustomDate ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-accent hover:text-foreground'"
            :aria-pressed="isCustomDate"
            @click="openCustomDate()"
          >
            {{ isCustomDate ? dateDisplay : "Outra data" }}
            <input
              ref="customDateInput"
              v-model="selectedDate"
              type="date"
              class="absolute inset-0 cursor-pointer opacity-0"
              aria-label="Escolher outra data"
              tabindex="-1"
            />
          </button>
        </div>
        <span v-if="!isCustomDate" class="text-sm text-muted-foreground">{{ dateDisplay }}</span>
        <div
          v-if="dayProgress"
          class="inline-flex items-center gap-2"
          :title="`${dayProgress.finished} de ${dayProgress.planned} un. expedidas`"
          role="progressbar"
          :aria-valuenow="dayProgress.pct"
          aria-valuemin="0"
          aria-valuemax="100"
          aria-label="Progresso do dia"
        >
          <div class="h-1.5 w-24 overflow-hidden rounded-full bg-muted">
            <div class="h-full rounded-full bg-primary transition-all" :style="{ width: `${dayProgress.pct}%` }" />
          </div>
          <span class="text-xs tabular-nums text-muted-foreground">{{ dayProgress.pct }}%</span>
        </div>
        <select
          v-if="baseOptions.length"
          v-model="baseFilter"
          class="ml-auto h-9 rounded-md border bg-background px-2 text-sm text-muted-foreground outline-none focus:ring-1 focus:ring-ring"
          aria-label="Filtrar por ficha-base"
        >
          <option value="">Todas as massas</option>
          <option v-for="base in baseOptions" :key="base.output_sku" :value="base.output_sku">
            {{ base.name }} ({{ base.count }})
          </option>
        </select>
      </div>

      <p v-if="pending && !rows.length" class="text-sm text-muted-foreground">Carregando…</p>
      <p v-else-if="error" class="rounded-md border border-red-500/30 bg-red-500/5 p-4 text-sm text-red-700 dark:text-red-400">
        Falha ao carregar. Reconectando…
      </p>

      <div v-else-if="!stageRows.length" class="grid place-items-center gap-2 rounded-lg border border-dashed py-16 text-center text-muted-foreground">
        <Icon name="lucide:layout-grid" class="size-8" />
        <p class="text-base font-medium">{{ emptyCopy.text }}</p>
        <NuxtLink v-if="emptyCopy.to" :to="emptyCopy.to" class="text-sm text-primary underline-offset-2 hover:underline">
          {{ emptyCopy.cta }}
        </NuxtLink>
      </div>

      <div v-else class="overflow-hidden rounded-lg border">
        <table class="w-full text-sm">
          <thead class="bg-muted/50 text-left text-xs uppercase tracking-wide text-muted-foreground">
            <tr>
              <th class="px-3 py-2 font-semibold">Produto</th>
              <th v-if="lens.read.visible" class="px-3 py-2 text-right font-semibold">{{ lens.read.label }}</th>
              <th v-if="lens.action.visible" class="px-3 py-2 text-right font-semibold">{{ lens.action.label }}</th>
            </tr>
          </thead>
          <tbody class="divide-y">
            <tr v-for="row in stageRows" :key="row.output_sku" class="hover:bg-muted/30">
              <td class="px-3 py-1.5">
                <p class="font-bold">{{ row.output_sku }}</p>
                <p class="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <span class="truncate">{{ row.recipe_name }}</span>
                  <button
                    v-if="rowCommittedUnits(row) > 0"
                    type="button"
                    class="inline-flex shrink-0 items-center gap-1 rounded-md border border-primary/30 bg-primary/5 px-1.5 py-0.5 text-[0.7rem] font-medium tabular-nums text-primary transition hover:bg-primary/10"
                    :aria-label="`${rowCommittedUnits(row)} unidades de ${row.output_sku} comprometidas com pedidos`"
                    @click="commitmentsRow = row"
                  >
                    <Icon name="lucide:shopping-bag" class="size-3" />
                    {{ rowCommittedUnits(row) }} un.
                  </button>
                </p>
              </td>

              <!-- Coluna de LEITURA -->
              <td v-if="lens.read.visible" class="px-3 py-1.5 text-right">
                <button
                  v-if="stage === 'plan' && row.suggestion"
                  type="button"
                  :class="[CELL_ACTION, 'text-muted-foreground']"
                  :aria-label="`Por que ${row.suggestion.quantity} de ${row.recipe_name}?`"
                  @click="explaining = row.suggestion"
                >
                  {{ row.suggestion.quantity }}
                  <Icon name="lucide:info" class="size-3.5 opacity-60" />
                </button>
                <span v-else :class="[CELL_READ, rowValue(row, lens.read.key) !== '0' ? 'text-foreground' : 'text-muted-foreground']">
                  {{ cellQty(rowValue(row, lens.read.key)) }}
                </span>
              </td>

              <!-- Coluna de AÇÃO (verbo no cabeçalho; valor atual + gesto) -->
              <td v-if="lens.action.visible" class="px-3 py-1.5 text-right">
                <button
                  v-if="actionEnabled(row)"
                  type="button"
                  :class="[CELL_ACTION, rowValue(row, lens.action.key) !== '0' ? 'text-foreground' : 'text-muted-foreground']"
                  :disabled="isBusy(row.output_sku)"
                  :aria-label="`${ACTION_VERB[stage]} ${row.output_sku}`"
                  @click="onAction(row)"
                >
                  <template v-if="rowValue(row, lens.action.key) !== '0'">
                    {{ rowValue(row, lens.action.key) }}
                    <Icon :name="stage === 'produce' && row.started_orders.length ? 'lucide:settings-2' : 'lucide:pencil'" class="size-3.5 opacity-60" />
                  </template>
                  <template v-else>
                    <span class="text-sm font-medium">{{ ACTION_VERB[stage] }}</span>
                    <Icon name="lucide:chevron-right" class="size-3.5 opacity-60" />
                  </template>
                </button>
                <span v-else :class="[CELL_READ, rowValue(row, lens.action.key) !== '0' ? 'text-foreground' : 'text-muted-foreground']">
                  {{ cellQty(rowValue(row, lens.action.key)) }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
        <p v-if="query && !stageRows.length" class="border-t p-3 text-center text-sm text-muted-foreground">
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
        <div class="flex items-center gap-2">
          <button type="button" class="grid size-12 shrink-0 place-items-center rounded-md border text-xl font-bold transition hover:bg-accent" aria-label="Diminuir" @click="bump('plan', -1)">−</button>
          <input
            v-model="planQty"
            type="text"
            inputmode="decimal"
            class="h-12 w-full rounded-md border bg-background text-center text-2xl font-bold tabular-nums outline-none focus:ring-1 focus:ring-ring"
            aria-label="Quantidade planejada"
          />
          <button type="button" class="grid size-12 shrink-0 place-items-center rounded-md border text-xl font-bold transition hover:bg-accent" aria-label="Aumentar" @click="bump('plan', 1)">+</button>
        </div>
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

    <!-- processar (iniciar) -->
    <UiDialog :open="startRow != null" @update:open="(v) => { if (!v) startRow = null }">
      <UiDialogContent class="sm:max-w-sm">
        <UiDialogHeader>
          <UiDialogTitle>Processar {{ startRow?.output_sku }}</UiDialogTitle>
          <UiDialogDescription>Quantidade que entra em processo agora — registra o início e materializa o lote.</UiDialogDescription>
        </UiDialogHeader>
        <div class="flex items-center gap-2">
          <button type="button" class="grid size-12 shrink-0 place-items-center rounded-md border text-xl font-bold transition hover:bg-accent" aria-label="Diminuir" @click="bump('start', -1)">−</button>
          <input
            v-model="startQty"
            type="text"
            inputmode="decimal"
            class="h-12 w-full rounded-md border bg-background text-center text-2xl font-bold tabular-nums outline-none focus:ring-1 focus:ring-ring"
            aria-label="Quantidade em processo"
          />
          <button type="button" class="grid size-12 shrink-0 place-items-center rounded-md border text-xl font-bold transition hover:bg-accent" aria-label="Aumentar" @click="bump('start', 1)">+</button>
        </div>
        <UiDialogFooter>
          <button type="button" class="rounded-md border px-3 py-2 text-sm font-medium transition hover:bg-accent" @click="startRow = null">Cancelar</button>
          <button
            type="button"
            :disabled="!startQty.trim()"
            class="rounded-md border border-transparent bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
            @click="confirmStart()"
          >
            Iniciar
          </button>
        </UiDialogFooter>
      </UiDialogContent>
    </UiDialog>

    <!-- lote em processo (gerir: etapa, timer, estornar) -->
    <UiDialog :open="startedRow != null" @update:open="(v) => { if (!v) { startedRow = null; voidConfirming = false } }">
      <UiDialogContent class="sm:max-w-md">
        <UiDialogHeader>
          <UiDialogTitle>{{ startedRow?.output_sku }} em processo</UiDialogTitle>
          <UiDialogDescription>
            #{{ startedRow?.started_orders[0]?.ref }} · {{ startedRow?.started_qty }} un. em processo
          </UiDialogDescription>
        </UiDialogHeader>

        <div v-if="startedCard" class="flex flex-col gap-2">
          <div class="flex items-center justify-between gap-2 text-sm">
            <span class="truncate font-medium">
              <template v-if="startedCard.total_steps > 0 && startedCard.current_step_index">
                {{ startedCard.current_step_index }}/{{ startedCard.total_steps }} · {{ startedCard.current_step_name || startedCard.current_step }}
              </template>
              <template v-else>{{ startedCard.current_step || "Em processo" }}</template>
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

        <div v-if="startedRow && rowCommittedUnits(startedRow) > 0" class="flex items-start gap-2 rounded-md border border-primary/30 bg-primary/5 p-2.5 text-sm">
          <Icon name="lucide:shopping-bag" class="mt-0.5 size-4 shrink-0 text-primary" />
          <span>{{ rowCommittedUnits(startedRow) }} un. deste lote já têm dono (pedidos confirmados).</span>
        </div>

        <div v-if="voidConfirming" class="flex flex-col gap-2">
          <p class="flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-2.5 text-sm text-amber-700 dark:text-amber-300">
            <Icon name="lucide:triangle-alert" class="mt-0.5 size-4 shrink-0" />
            <span>A ordem sai do processo e o vínculo com pedidos é desfeito.</span>
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
          <NuxtLink to="/expedicao" class="rounded-md border px-3 py-2 text-sm font-medium transition hover:bg-accent">
            Expedição →
          </NuxtLink>
        </UiDialogFooter>
      </UiDialogContent>
    </UiDialog>

    <!-- expedir (a saída da produção — quantidade final, pós-conferência) -->
    <UiDialog :open="finishRow != null" @update:open="(v) => { if (!v) finishRow = null }">
      <UiDialogContent class="sm:max-w-sm">
        <UiDialogHeader>
          <UiDialogTitle>Expedir {{ finishRow?.output_sku }}</UiDialogTitle>
          <UiDialogDescription>
            Quantidade final aprovada (#{{ finishRow?.started_orders[0]?.ref }}) — segue para a vitrine.
          </UiDialogDescription>
        </UiDialogHeader>
        <div class="flex items-center gap-2">
          <button type="button" class="grid size-12 shrink-0 place-items-center rounded-md border text-xl font-bold transition hover:bg-accent" aria-label="Diminuir" @click="bump('finish', -1)">−</button>
          <input
            v-model="finishQty"
            type="text"
            inputmode="decimal"
            class="h-12 w-full rounded-md border bg-background text-center text-2xl font-bold tabular-nums outline-none focus:ring-1 focus:ring-ring"
            aria-label="Quantidade expedida"
          />
          <button type="button" class="grid size-12 shrink-0 place-items-center rounded-md border text-xl font-bold transition hover:bg-accent" aria-label="Aumentar" @click="bump('finish', 1)">+</button>
        </div>
        <UiDialogFooter>
          <button type="button" class="rounded-md border px-3 py-2 text-sm font-medium transition hover:bg-accent" @click="finishRow = null">Cancelar</button>
          <button
            type="button"
            :disabled="!finishQty.trim()"
            class="rounded-md border border-transparent bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
            @click="confirmFinish(false)"
          >
            Confirmar expedição
          </button>
        </UiDialogFooter>
      </UiDialogContent>
    </UiDialog>

    <!-- pedidos vinculados -->
    <UiDialog :open="commitmentsRow != null" @update:open="(v) => { if (!v) commitmentsRow = null }">
      <UiDialogContent class="sm:max-w-md">
        <UiDialogHeader>
          <UiDialogTitle>{{ commitmentsRow ? rowCommittedUnits(commitmentsRow) : 0 }} un. comprometidas · {{ commitmentsRow?.output_sku }}</UiDialogTitle>
          <UiDialogDescription>Encomendas confirmadas que dependem desta produção.</UiDialogDescription>
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
            v-if="stage === 'plan' && access?.can_edit_planned"
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
