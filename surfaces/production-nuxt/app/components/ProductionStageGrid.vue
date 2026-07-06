<script setup lang="ts">
// A GRADE por etapa — um motor, três lentes (refinos Pablo 2026-07-03):
//   PRODUTO | leitura | AÇÃO — cada lente tem UMA coluna de leitura e UMA de
//   ação com verbo no cabeçalho:
//   · plan     (Planejamento): SUGERIDO   | PLANEJAR   — todos os SKUs;
//   · produce  (Produção):     PLANEJADO  | PROCESSAR  — só linhas com número;
//   · expedite (Expedição):    PROCESSADO | CONCLUIR   — só linhas com número.
// A ação abre overlay com quantidade em stepper touch (+/−) e confirmação
// explícita; cada informe vira evento imutável (actor + timestamp → BI).
// Instruções específicas do SKU (peso de corte etc.) terão casa neste overlay
// (estudo de notação de pâtonnage pendente). Nomenclatura interna do sistema
// intacta (planned/started/finished) — as lentes são linguagem de UI.
import {
  boardDisplay,
  elapsedLabel,
  fullDateLabel,
  isoForOffset,
  isStale,
  matchesRowQuery,
  rowCommitments,
  rowCommittedUnits,
  startableWorkOrder,
  timerChip,
  timerTone,
  weekdayLabel,
} from "~/presentation/production";
import type {
  ProductionKDSCardProjection,
  ProductionMatrixRowProjection,
  ProductionShortageError,
  ProductionSuggestionProjection,
  WorkOrderCardProjection,
} from "~/types/production";

const props = defineProps<{
  stage: "plan" | "produce" | "expedite";
  title: string;
}>();

const {
  board,
  rows,
  counts,
  selectedDate,
  pending,
  error,
  refresh,
  isBusy,
  plan,
  start,
} = useProductionBoard();
const kds = useProductionKds();

const access = computed(() => board.value?.access ?? null);

const route = useRoute();
const query = ref(typeof route.query.q === "string" ? route.query.q : "");
watch(
  () => route.query.q,
  (q) => {
    if (typeof q === "string") query.value = q;
  },
);

// ── Data: Hoje · Amanhã · Outra data (chip com o picker embutido) ───────────
const todayISO = isoForOffset(0);
const tomorrowISO = isoForOffset(1);
const isCustomDate = computed(
  () => selectedDate.value !== todayISO && selectedDate.value !== tomorrowISO,
);
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
      read: {
        key: "suggested",
        label: "Sugerido",
        visible: !!access.value?.can_view_suggested,
      },
      action: {
        key: "planned",
        label: "Planejar",
        visible: !!access.value?.can_view_planned,
        editable: !!access.value?.can_edit_planned,
      },
    } as const;
  }
  if (props.stage === "produce") {
    return {
      read: {
        key: "planned",
        label: "Planejado",
        visible: !!access.value?.can_view_planned,
      },
      action: {
        key: "started",
        label: "Processar",
        visible: !!access.value?.can_view_started,
        editable: !!access.value?.can_edit_started,
      },
    } as const;
  }
  return {
    read: {
      key: "started",
      label: "Processado",
      visible: !!access.value?.can_view_started,
    },
    action: {
      key: "finished",
      label: "Concluir",
      visible: !!access.value?.can_view_finished,
      editable: !!access.value?.can_edit_finished,
    },
  } as const;
});

// Linhas por lente: Planejamento vê TODOS os SKUs; Produção/Expedição só quem
// tem número relevante (higiene de foco na bancada).
const stageRows = computed<ProductionMatrixRowProjection[]>(() => {
  let base = rows.value.filter((r) => matchesRowQuery(r, query.value));
  if (baseFilter.value) {
    base = base.filter((r) =>
      r.base_usages.some((usage) => usage.output_sku === baseFilter.value),
    );
  }
  if (props.stage === "produce") {
    return base.filter((r) => r.planned_qty !== "0" || r.started_qty !== "0");
  }
  if (props.stage === "expedite") {
    return base.filter((r) => r.started_qty !== "0" || r.finished_qty !== "0");
  }
  return base;
});

// Board tolerante a dado velho: só troca a grade por carregando/erro quando NÃO há
// dado; havendo dado, mostra-o sempre + chip de degradação honesto se a última
// atualização falhou (dado velho visível > quadro vazio).
const display = computed(() =>
  boardDisplay({
    pending: pending.value,
    error: !!error.value,
    hasData: rows.value.length > 0,
  }),
);
const stale = computed(() =>
  isStale({ error: !!error.value, hasData: rows.value.length > 0 }),
);

const emptyCopy = computed(() =>
  props.stage === "plan"
    ? { text: "Nenhuma receita ativa.", cta: "", to: "" }
    : props.stage === "produce"
      ? {
          text: "Nada planejado para processar nesta data.",
          cta: "Ir para o Planejamento",
          to: "/planejamento",
        }
      : {
          text: "Nada processado para concluir nesta data.",
          cta: "Ir para a Produção",
          to: "/",
        },
);

// ── Overlays ────────────────────────────────────────────────────────────────
const explaining = ref<ProductionSuggestionProjection | null>(null);
const planRow = ref<ProductionMatrixRowProjection | null>(null);
const planQty = ref("");

// O gesto de planejar tem TRÊS sentidos, e o operador precisa saber qual está
// fazendo (o kernel já distingue: set_planned_quantity ajusta a WO planejada;
// depois do start ela sai do "planejado" e um novo plano cria OUTRO lote):
//   · plan      — nada na data ainda: planeja a primeira quantidade;
//   · adjust    — existe WO planejada: SUBSTITUI a quantidade (0 remove);
//   · new-batch — a produção já assumiu (iniciado/concluído): cria lote que
//                 SOMA ao dia — explícito, nunca silencioso.
type PlanMode = "plan" | "adjust" | "new-batch";
const planMode = computed<PlanMode>(() => {
  const row = planRow.value;
  if (!row) return "plan";
  if (row.planned_qty !== "0") return "adjust";
  if (row.started_qty !== "0" || row.finished_qty !== "0") return "new-batch";
  return "plan";
});
function rowPlanMode(row: ProductionMatrixRowProjection): PlanMode {
  if (row.planned_qty !== "0") return "adjust";
  if (row.started_qty !== "0" || row.finished_qty !== "0") return "new-batch";
  return "plan";
}
const PLAN_TITLE: Record<PlanMode, string> = {
  plan: "Planejar",
  adjust: "Ajustar planejado",
  "new-batch": "Planejar novo lote",
};
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

// Timer do forno (Expedição): lembrete armado por fornada — a ferramenta do
// forneiro para conferir/retirar, com som. Não confundir com o relógio de
// idade do lote (guardrail de esquecimento, que vive nos alertas).
const oven = useOvenTimers();
const ovenRow = ref<ProductionMatrixRowProjection | null>(null);
const ovenMinutes = ref("15");
function ovenKey(row: ProductionMatrixRowProjection): string {
  return String(row.started_orders[0]?.pk ?? "");
}
function openOven(row: ProductionMatrixRowProjection) {
  const key = ovenKey(row);
  if (!key) return;
  if (oven.isRinging(key)) {
    oven.clear(key);
    return;
  }
  ovenRow.value = row;
  ovenMinutes.value = String(oven.get(key)?.minutes ?? 15);
}
function confirmOven() {
  const row = ovenRow.value;
  const minutes = parseFloat(ovenMinutes.value.replace(",", "."));
  if (!row || Number.isNaN(minutes) || minutes < 1) return;
  oven.arm(ovenKey(row), minutes);
  ovenRow.value = null;
}
function cancelOven() {
  const row = ovenRow.value;
  if (row) oven.clear(ovenKey(row));
  ovenRow.value = null;
}

// Stepper touch: quantidade sempre editável com +/− generosos.
// (Recebe o NOME do campo — no template o Vue desembrulha refs, então passar
// `planQty` entregaria a string, não o ref.)
const qtyFields = {
  plan: planQty,
  start: startQty,
  finish: finishQty,
  oven: ovenMinutes,
} as const;
function bump(field: keyof typeof qtyFields, delta: number) {
  const target = qtyFields[field];
  const current = parseFloat(target.value.replace(",", ".")) || 0;
  const next = Math.max(0, current + delta);
  target.value = Number.isInteger(next)
    ? String(next)
    : next.toFixed(3).replace(/\.?0+$/, "");
}

function openPlan(row: ProductionMatrixRowProjection) {
  planRow.value = row;
  const mode = rowPlanMode(row);
  // Novo lote parte de 0 — a sugestão era para o dia inteiro e a produção já
  // assumiu parte dela; pré-preencher aqui dobraria o dia sem querer.
  if (mode === "new-batch") planQty.value = "0";
  else if (mode === "adjust") planQty.value = row.planned_qty;
  else planQty.value = row.suggestion?.quantity ?? "0";
}

// Do diálogo "por que essa sugestão?" direto para o planejamento da linha dona da
// sugestão (fecha a explicação e abre o plano).
function planFromExplanation() {
  const row = rows.value.find((r) => r.suggestion === explaining.value);
  explaining.value = null;
  if (row) openPlan(row);
}

async function confirmPlan() {
  const row = planRow.value;
  if (!row || row.recipe_pk == null || !board.value || !planQty.value.trim())
    return;
  const res = await plan(row.output_sku, {
    recipe_id: row.recipe_pk,
    quantity: planQty.value.trim(),
    target_date: board.value.selected_date,
    position_ref: board.value.selected_position_ref || undefined,
    source:
      row.suggestion && planQty.value.trim() === row.suggestion.quantity
        ? "suggested"
        : undefined,
  });
  if (res.ok) {
    const label =
      planMode.value === "new-batch" ? "Novo lote planejado" : "Planejado";
    planRow.value = null;
    useSonner.success(`${label}: ${row.output_sku} × ${planQty.value.trim()}`);
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
    useSonner.success(
      `Em processo: ${row.output_sku} × ${startQty.value.trim()}`,
    );
  }
}

// A conclusão mira UMA WorkOrder específica, não o agregado da linha. Com dois
// lotes de 30 em processo, pré-preencher com o started_qty AGREGADO (60) contra a
// WO[0] (30) fazia o ledger engolir rendimento de 200%. Aqui a qty pré-preenchida
// é a do lote alvo, e o operador escolhe o lote quando há mais de um.
const finishTargetPk = ref<number | null>(null);
const finishTarget = computed<WorkOrderCardProjection | null>(() => {
  const row = finishRow.value;
  if (!row) return null;
  return (
    row.started_orders.find((w) => w.pk === finishTargetPk.value) ??
    row.started_orders[0] ??
    null
  );
});
function selectFinishTarget(wo: WorkOrderCardProjection) {
  finishTargetPk.value = wo.pk;
  finishQty.value =
    wo.started_qty !== "0"
      ? wo.started_qty
      : (finishRow.value?.planned_qty ?? "");
}

function openFinish(row: ProductionMatrixRowProjection) {
  startedRow.value = null;
  finishRow.value = row;
  const wo0 = row.started_orders[0];
  finishTargetPk.value = wo0?.pk ?? null;
  finishQty.value =
    wo0 && wo0.started_qty !== "0" ? wo0.started_qty : row.planned_qty;
}

async function confirmFinish(force = false) {
  const row = finishRow.value;
  const wo = finishTarget.value;
  if (!row || !wo || !finishQty.value.trim()) return;
  const res = await kds.finish(wo.pk, finishQty.value.trim(), force);
  if (res.ok) {
    finishRow.value = null;
    refresh();
    useSonner.success(
      `Concluído: ${row.output_sku} × ${finishQty.value.trim()}`,
    );
  } else if (res.shortage) {
    finishRow.value = null;
    shortage.value = res.shortage;
  }
}

// Inicia o próximo lote PLANEJADO sem sair do fluxo — antes, com um lote em
// processo, qualquer toque caía no diálogo de gestão e não havia como largar o
// próximo até concluir o primeiro.
function startNextBatch() {
  const row = startedRow.value;
  startedRow.value = null;
  if (row) openStart(row);
}

async function overrideShortage() {
  const s = shortage.value;
  shortage.value = null;
  if (!s) return;
  const ref = (s as { work_order_ref?: string }).work_order_ref;
  const row = rows.value.find((r) =>
    r.started_orders.some((wo) => wo.ref === ref),
  );
  if (row) {
    finishRow.value = row;
    const wo = row.started_orders.find((w) => w.ref === ref);
    finishTargetPk.value = wo?.pk ?? row.started_orders[0]?.pk ?? null;
    await confirmFinish(true);
  }
}

async function confirmVoid() {
  const row = startedRow.value;
  const wo = row?.started_orders[0];
  if (!row || !wo) return;
  const res = await kds.voidOrder(
    wo.pk,
    voidReason.value.trim() || "Estornado pelo operador",
  );
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
  if (props.stage === "produce")
    return !!row.started_orders.length || !!startableWorkOrder(row);
  return !!row.started_orders.length;
}

const ACTION_VERB: Record<string, string> = {
  plan: "Planejar",
  produce: "Processar",
  expedite: "Concluir",
};

// Verbo da célula de plano: quando a produção já assumiu a quantidade do dia,
// o gesto disponível é somar um lote — e a célula diz isso antes do modal.
function planCellVerb(row: ProductionMatrixRowProjection): string {
  return rowPlanMode(row) === "new-batch" ? "Novo lote" : "Planejar";
}

const planQtyValid = computed(() => {
  const qty = parseFloat(planQty.value.replace(",", "."));
  if (Number.isNaN(qty) || qty < 0) return false;
  // Zerar só faz sentido quando há planejado a remover; num lote novo, 0 é no-op.
  if (qty === 0) return planMode.value === "adjust";
  return true;
});

function cellQty(value: string): string {
  return value === "0" ? "—" : value;
}

// ── Anatomia única de célula (números neutros; cor não codifica coluna) ─────
const CELL =
  "inline-flex h-10 min-w-20 items-center justify-end gap-1.5 rounded-md px-2.5 font-semibold tabular-nums transition";
const CELL_ACTION = `${CELL} border hover:bg-accent disabled:opacity-50`;
const CELL_READ = `${CELL} border border-transparent`;

// Progresso do dia: noção visual do quanto falta (expedido ÷ total do dia).
const dayProgress = computed(() => {
  const parse = (v?: string) => parseFloat((v ?? "0").replace(",", ".")) || 0;
  const planned =
    parse(counts.value?.planned_qty) +
    parse(counts.value?.started_qty) +
    parse(counts.value?.finished_qty);
  const finished = parse(counts.value?.finished_qty);
  if (!planned) return null;
  return {
    pct: Math.min(100, Math.round((finished / planned) * 100)),
    finished,
    planned,
  };
});

const headerCount = computed(() => {
  if (props.stage === "plan")
    return { count: counts.value?.planned ?? 0, label: "planejados" };
  if (props.stage === "produce")
    return { count: counts.value?.started ?? 0, label: "em processo" };
  return { count: counts.value?.finished ?? 0, label: "concluídos" };
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
      @refresh="
        refresh();
        kds.refresh();
      "
    />

    <section class="min-h-0 flex-1 overflow-auto p-3 md:p-4">
      <div class="mb-3 flex flex-wrap items-center gap-3">
        <div
          class="flex items-center gap-1 rounded-lg border bg-background p-0.5"
          role="group"
          aria-label="Data"
        >
          <button
            type="button"
            class="rounded-md px-2.5 py-1.5 text-sm font-medium transition"
            :class="
              selectedDate === todayISO
                ? 'bg-primary text-primary-foreground'
                : 'text-muted-foreground hover:bg-accent hover:text-foreground'
            "
            :aria-pressed="selectedDate === todayISO"
            @click="selectedDate = todayISO"
          >
            Hoje
          </button>
          <button
            type="button"
            class="rounded-md px-2.5 py-1.5 text-sm font-medium transition"
            :class="
              selectedDate === tomorrowISO
                ? 'bg-primary text-primary-foreground'
                : 'text-muted-foreground hover:bg-accent hover:text-foreground'
            "
            :aria-pressed="selectedDate === tomorrowISO"
            @click="selectedDate = tomorrowISO"
          >
            Amanhã
          </button>
          <button
            type="button"
            class="relative rounded-md px-2.5 py-1.5 text-sm font-medium transition"
            :class="
              isCustomDate
                ? 'bg-primary text-primary-foreground'
                : 'text-muted-foreground hover:bg-accent hover:text-foreground'
            "
            :aria-pressed="isCustomDate"
            @click="openCustomDate()"
          >
            {{ isCustomDate ? weekdayLabel(selectedDate) : "Outra data" }}
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
        <span class="text-sm text-muted-foreground">{{
          fullDateLabel(selectedDate)
        }}</span>
        <div
          v-if="dayProgress"
          class="inline-flex items-center gap-2"
          :title="`${dayProgress.finished} de ${dayProgress.planned} un. concluídas`"
          role="progressbar"
          :aria-valuenow="dayProgress.pct"
          aria-valuemin="0"
          aria-valuemax="100"
          aria-label="Progresso do dia"
        >
          <div class="h-1.5 w-24 overflow-hidden rounded-full bg-muted">
            <div
              class="h-full rounded-full bg-primary transition-all"
              :style="{ width: `${dayProgress.pct}%` }"
            />
          </div>
          <span class="text-xs tabular-nums text-muted-foreground"
            >{{ dayProgress.pct }}%</span
          >
        </div>
        <select
          v-if="baseOptions.length"
          v-model="baseFilter"
          class="ml-auto h-9 rounded-md border bg-background px-2 text-sm text-muted-foreground outline-none focus:ring-1 focus:ring-ring"
          aria-label="Filtrar por ficha-base"
        >
          <option value="">Todas as bases</option>
          <option
            v-for="base in baseOptions"
            :key="base.output_sku"
            :value="base.output_sku"
          >
            {{ base.name }} ({{ base.count }})
          </option>
        </select>
      </div>

      <p v-if="display === 'loading'" class="text-sm text-muted-foreground">
        Carregando…
      </p>

      <!-- Erro só toma a tela quando NÃO há dado nenhum a mostrar (acolhedor, não tela branca). -->
      <div
        v-else-if="display === 'error'"
        class="grid place-items-center gap-2 rounded-lg border border-dashed border-red-500/30 py-16 text-center text-muted-foreground"
      >
        <Icon name="lucide:cloud-off" class="size-8 text-red-500/70" />
        <p class="text-base font-medium text-foreground">
          Não foi possível carregar o quadro.
        </p>
        <p class="text-sm">Estamos tentando reconectar sozinhos.</p>
        <button
          type="button"
          class="mt-1 inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-sm font-medium transition hover:bg-accent"
          @click="refresh()"
        >
          <Icon name="lucide:refresh-cw" class="size-4" /> Tentar de novo
        </button>
      </div>

      <template v-else>
        <!-- Dado presente: chip de degradação honesto quando a última atualização falhou. -->
        <div
          v-if="stale"
          role="status"
          aria-live="polite"
          class="mb-3 flex items-center gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm font-medium text-amber-700 dark:text-amber-300"
        >
          <Icon name="lucide:wifi-off" class="size-4 shrink-0" />
          <span>Sem atualizar — mostrando o último quadro carregado.</span>
        </div>

        <div
          v-if="!stageRows.length"
          class="grid place-items-center gap-2 rounded-lg border border-dashed py-16 text-center text-muted-foreground"
        >
          <Icon name="lucide:layout-grid" class="size-8" />
          <p class="text-base font-medium">{{ emptyCopy.text }}</p>
          <NuxtLink
            v-if="emptyCopy.to"
            :to="emptyCopy.to"
            class="text-sm text-primary underline-offset-2 hover:underline"
          >
            {{ emptyCopy.cta }}
          </NuxtLink>
        </div>

        <div v-else class="overflow-hidden rounded-lg border">
          <table class="w-full text-sm">
            <thead
              class="bg-muted/50 text-left text-xs uppercase tracking-wide text-muted-foreground"
            >
              <tr>
                <th class="px-3 py-2 font-semibold">Produto</th>
                <th
                  v-if="lens.read.visible"
                  class="px-3 py-2 text-right font-semibold"
                >
                  {{ lens.read.label }}
                </th>
                <th
                  v-if="lens.action.visible"
                  class="px-3 py-2 text-right font-semibold"
                >
                  {{ lens.action.label }}
                </th>
              </tr>
            </thead>
            <tbody class="divide-y">
              <tr
                v-for="row in stageRows"
                :key="row.output_sku"
                class="hover:bg-muted/30"
              >
                <td class="px-3 py-1.5">
                  <p class="font-bold">{{ row.output_sku }}</p>
                  <p
                    class="flex items-center gap-1.5 text-xs text-muted-foreground"
                  >
                    <span class="truncate">{{ row.recipe_name }}</span>
                    <button
                      v-if="stage === 'expedite' && ovenKey(row)"
                      type="button"
                      class="inline-flex shrink-0 items-center gap-1 rounded-md border px-1.5 py-0.5 text-[0.7rem] font-semibold tabular-nums transition"
                      :class="
                        oven.isRinging(ovenKey(row))
                          ? 'animate-pulse border-red-500/40 bg-red-500/10 text-red-700 dark:text-red-300'
                          : oven.get(ovenKey(row))
                            ? 'border-border bg-muted text-foreground'
                            : 'border-dashed text-muted-foreground hover:bg-accent hover:text-foreground'
                      "
                      :aria-label="
                        oven.isRinging(ovenKey(row))
                          ? `Conferir ${row.output_sku} no forno`
                          : `Timer do forno para ${row.output_sku}`
                      "
                      @click="openOven(row)"
                    >
                      <Icon name="lucide:alarm-clock" class="size-3" />
                      <template v-if="oven.isRinging(ovenKey(row))"
                        >Conferir!</template
                      >
                      <template v-else-if="oven.get(ovenKey(row))">{{
                        oven.remainingLabel(ovenKey(row))
                      }}</template>
                      <template v-else>Timer</template>
                    </button>
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
                    :class="[
                      CELL_READ,
                      row.suggestion.quantity !== '0'
                        ? 'text-foreground'
                        : 'text-muted-foreground',
                      'hover:bg-accent',
                    ]"
                    :aria-label="`Por que ${row.suggestion.quantity} de ${row.recipe_name}?`"
                    @click="explaining = row.suggestion"
                  >
                    {{ cellQty(row.suggestion.quantity) }}
                    <Icon name="lucide:info" class="size-3.5 opacity-60" />
                  </button>
                  <span
                    v-else
                    :class="[
                      CELL_READ,
                      rowValue(row, lens.read.key) !== '0'
                        ? 'text-foreground'
                        : 'text-muted-foreground',
                    ]"
                  >
                    {{ cellQty(rowValue(row, lens.read.key)) }}
                  </span>
                </td>

                <!-- Coluna de AÇÃO (verbo no cabeçalho; valor atual + gesto) -->
                <td v-if="lens.action.visible" class="px-3 py-1.5 text-right">
                  <button
                    v-if="actionEnabled(row)"
                    type="button"
                    :class="[
                      CELL_ACTION,
                      rowValue(row, lens.action.key) !== '0'
                        ? 'text-foreground'
                        : 'text-muted-foreground',
                    ]"
                    :disabled="isBusy(row.output_sku)"
                    :aria-label="`${ACTION_VERB[stage]} ${row.output_sku}`"
                    @click="onAction(row)"
                  >
                    <template v-if="rowValue(row, lens.action.key) !== '0'">
                      {{ rowValue(row, lens.action.key) }}
                      <Icon
                        :name="
                          stage === 'produce' && row.started_orders.length
                            ? 'lucide:settings-2'
                            : 'lucide:pencil'
                        "
                        class="size-3.5 opacity-60"
                      />
                    </template>
                    <template v-else>
                      <span class="whitespace-nowrap text-sm font-medium">{{
                        stage === "plan"
                          ? planCellVerb(row)
                          : ACTION_VERB[stage]
                      }}</span>
                      <Icon
                        name="lucide:chevron-right"
                        class="size-3.5 opacity-60"
                      />
                    </template>
                  </button>
                  <span
                    v-else
                    :class="[
                      CELL_READ,
                      rowValue(row, lens.action.key) !== '0'
                        ? 'text-foreground'
                        : 'text-muted-foreground',
                    ]"
                  >
                    {{ cellQty(rowValue(row, lens.action.key)) }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
          <p
            v-if="query && !stageRows.length"
            class="border-t p-3 text-center text-sm text-muted-foreground"
          >
            Nenhum resultado para “{{ query.trim() }}”.
          </p>
        </div>
      </template>
    </section>

    <!-- planejar -->
    <UiDialog
      :open="planRow != null"
      @update:open="
        (v) => {
          if (!v) planRow = null;
        }
      "
    >
      <UiDialogContent class="sm:max-w-sm">
        <UiDialogHeader>
          <UiDialogTitle
            >{{ PLAN_TITLE[planMode] }} ·
            {{ planRow?.output_sku }}</UiDialogTitle
          >
          <UiDialogDescription>
            {{ planRow?.recipe_name }} · {{ fullDateLabel(selectedDate) }}
            <template v-if="planRow?.suggestion">
              · sugestão {{ planRow.suggestion.quantity }}</template
            >
          </UiDialogDescription>
        </UiDialogHeader>
        <p v-if="planMode === 'adjust'" class="text-sm text-muted-foreground">
          Substitui o planejado atual ({{ planRow?.planned_qty }}) — 0 remove.
        </p>
        <p
          v-else-if="planMode === 'new-batch'"
          class="text-sm text-muted-foreground"
        >
          Soma ao dia<template v-if="planRow?.started_qty !== '0'">
            · {{ planRow?.started_qty }} em processo</template
          ><template v-if="planRow?.finished_qty !== '0'">
            · {{ planRow?.finished_qty }} concluídas</template
          >.
        </p>
        <div class="flex items-center gap-2">
          <button
            type="button"
            class="grid size-12 shrink-0 place-items-center rounded-md border text-xl font-bold transition hover:bg-accent"
            aria-label="Diminuir"
            @click="bump('plan', -1)"
          >
            −
          </button>
          <input
            v-model="planQty"
            type="text"
            inputmode="decimal"
            class="h-12 w-full rounded-md border bg-background text-center text-2xl font-bold tabular-nums outline-none focus:ring-1 focus:ring-ring"
            aria-label="Quantidade planejada"
          />
          <button
            type="button"
            class="grid size-12 shrink-0 place-items-center rounded-md border text-xl font-bold transition hover:bg-accent"
            aria-label="Aumentar"
            @click="bump('plan', 1)"
          >
            +
          </button>
        </div>
        <UiDialogFooter>
          <button
            type="button"
            class="rounded-md border px-3 py-2 text-sm font-medium transition hover:bg-accent"
            @click="planRow = null"
          >
            Cancelar
          </button>
          <button
            type="button"
            :disabled="!planQty.trim() || !planQtyValid"
            class="rounded-md border border-transparent bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
            @click="confirmPlan()"
          >
            {{
              planMode === "new-batch" ? "Salvar novo lote" : "Salvar planejado"
            }}
          </button>
        </UiDialogFooter>
      </UiDialogContent>
    </UiDialog>

    <!-- processar (iniciar) -->
    <UiDialog
      :open="startRow != null"
      @update:open="
        (v) => {
          if (!v) startRow = null;
        }
      "
    >
      <UiDialogContent class="sm:max-w-sm">
        <UiDialogHeader>
          <UiDialogTitle>Processar {{ startRow?.output_sku }}</UiDialogTitle>
          <UiDialogDescription
            >Quantidade que entra em processo agora — registra o início e
            materializa o lote.</UiDialogDescription
          >
        </UiDialogHeader>
        <div class="flex items-center gap-2">
          <button
            type="button"
            class="grid size-12 shrink-0 place-items-center rounded-md border text-xl font-bold transition hover:bg-accent"
            aria-label="Diminuir"
            @click="bump('start', -1)"
          >
            −
          </button>
          <input
            v-model="startQty"
            type="text"
            inputmode="decimal"
            class="h-12 w-full rounded-md border bg-background text-center text-2xl font-bold tabular-nums outline-none focus:ring-1 focus:ring-ring"
            aria-label="Quantidade em processo"
          />
          <button
            type="button"
            class="grid size-12 shrink-0 place-items-center rounded-md border text-xl font-bold transition hover:bg-accent"
            aria-label="Aumentar"
            @click="bump('start', 1)"
          >
            +
          </button>
        </div>
        <UiDialogFooter>
          <button
            type="button"
            class="rounded-md border px-3 py-2 text-sm font-medium transition hover:bg-accent"
            @click="startRow = null"
          >
            Cancelar
          </button>
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
    <UiDialog
      :open="startedRow != null"
      @update:open="
        (v) => {
          if (!v) {
            startedRow = null;
            voidConfirming = false;
          }
        }
      "
    >
      <UiDialogContent class="sm:max-w-md">
        <UiDialogHeader>
          <UiDialogTitle
            >{{ startedRow?.output_sku }} em processo</UiDialogTitle
          >
          <UiDialogDescription>
            #{{ startedRow?.started_orders[0]?.ref }} ·
            {{ startedRow?.started_qty }} un. em processo
          </UiDialogDescription>
        </UiDialogHeader>

        <div v-if="startedCard" class="flex flex-col gap-2">
          <div class="flex items-center justify-between gap-2 text-sm">
            <span class="truncate font-medium">
              <template
                v-if="
                  startedCard.total_steps > 0 && startedCard.current_step_index
                "
              >
                {{ startedCard.current_step_index }}/{{
                  startedCard.total_steps
                }}
                ·
                {{ startedCard.current_step_name || startedCard.current_step }}
              </template>
              <template v-else>{{
                startedCard.current_step || "Em processo"
              }}</template>
            </span>
            <span
              class="shrink-0 rounded-md border px-2 py-0.5 text-xs font-semibold tabular-nums"
              :class="timerChip(timerTone(startedCard.timer_class))"
            >
              {{ elapsedLabel(startedCard.elapsed_seconds) }}
            </span>
          </div>
          <button
            v-if="startedCard.next_step_name"
            type="button"
            class="inline-flex items-center justify-center gap-1.5 rounded-md border px-3 py-2 text-sm font-medium transition hover:bg-accent"
            @click="advanceStep()"
          >
            <Icon name="lucide:arrow-right" class="size-4" /> Avançar para
            {{ startedCard.next_step_name }}
          </button>
        </div>

        <button
          v-if="startedRow && startableWorkOrder(startedRow)"
          type="button"
          class="inline-flex items-center justify-center gap-1.5 rounded-md border border-dashed px-3 py-2 text-sm font-medium transition hover:bg-accent"
          @click="startNextBatch()"
        >
          <Icon name="lucide:plus" class="size-4" /> Iniciar próximo lote ({{
            startableWorkOrder(startedRow)?.planned_qty
          }}
          un.)
        </button>

        <div v-if="voidConfirming" class="flex flex-col gap-2">
          <p
            class="flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-2.5 text-sm text-amber-700 dark:text-amber-300"
          >
            <Icon name="lucide:triangle-alert" class="mt-0.5 size-4 shrink-0" />
            <span
              >A ordem sai do processo e o vínculo com pedidos é desfeito.</span
            >
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
          <button
            type="button"
            class="rounded-md border px-3 py-2 text-sm font-medium transition hover:bg-accent"
            @click="
              startedRow = null;
              voidConfirming = false;
            "
          >
            Fechar
          </button>
          <NuxtLink
            to="/expedicao"
            class="rounded-md border px-3 py-2 text-sm font-medium transition hover:bg-accent"
          >
            Expedição →
          </NuxtLink>
        </UiDialogFooter>
      </UiDialogContent>
    </UiDialog>

    <!-- concluir (a saída da produção — quantidade final, pós-conferência) -->
    <UiDialog
      :open="finishRow != null"
      @update:open="
        (v) => {
          if (!v) finishRow = null;
        }
      "
    >
      <UiDialogContent class="sm:max-w-sm">
        <UiDialogHeader>
          <UiDialogTitle>Concluir {{ finishRow?.output_sku }}</UiDialogTitle>
          <UiDialogDescription>
            Quantidade final aprovada (#{{ finishTarget?.ref }}) — sai da
            produção e segue para a vitrine.
          </UiDialogDescription>
        </UiDialogHeader>
        <div
          v-if="(finishRow?.started_orders.length ?? 0) > 1"
          class="flex flex-wrap gap-1.5"
          role="group"
          aria-label="Escolher o lote a concluir"
        >
          <button
            v-for="wo in finishRow?.started_orders"
            :key="wo.pk"
            type="button"
            :aria-pressed="wo.pk === finishTargetPk"
            class="rounded-md border px-2 py-1 text-xs font-medium tabular-nums transition"
            :class="
              wo.pk === finishTargetPk
                ? 'border-primary bg-primary/5'
                : 'hover:bg-accent'
            "
            @click="selectFinishTarget(wo)"
          >
            #{{ wo.ref }} · {{ wo.started_qty }} un.
          </button>
        </div>
        <div class="flex items-center gap-2">
          <button
            type="button"
            class="grid size-12 shrink-0 place-items-center rounded-md border text-xl font-bold transition hover:bg-accent"
            aria-label="Diminuir"
            @click="bump('finish', -1)"
          >
            −
          </button>
          <input
            v-model="finishQty"
            type="text"
            inputmode="decimal"
            class="h-12 w-full rounded-md border bg-background text-center text-2xl font-bold tabular-nums outline-none focus:ring-1 focus:ring-ring"
            aria-label="Quantidade concluída"
          />
          <button
            type="button"
            class="grid size-12 shrink-0 place-items-center rounded-md border text-xl font-bold transition hover:bg-accent"
            aria-label="Aumentar"
            @click="bump('finish', 1)"
          >
            +
          </button>
        </div>
        <UiDialogFooter>
          <button
            type="button"
            class="rounded-md border px-3 py-2 text-sm font-medium transition hover:bg-accent"
            @click="finishRow = null"
          >
            Cancelar
          </button>
          <button
            type="button"
            :disabled="!finishQty.trim()"
            class="rounded-md border border-transparent bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
            @click="confirmFinish(false)"
          >
            Confirmar conclusão
          </button>
        </UiDialogFooter>
      </UiDialogContent>
    </UiDialog>

    <!-- timer do forno (lembrete por fornada, com som) -->
    <UiDialog
      :open="ovenRow != null"
      @update:open="
        (v) => {
          if (!v) ovenRow = null;
        }
      "
    >
      <UiDialogContent class="sm:max-w-sm">
        <UiDialogHeader>
          <UiDialogTitle
            >Timer do forno · {{ ovenRow?.output_sku }}</UiDialogTitle
          >
          <UiDialogDescription
            >Minutos até o lembrete de conferir/retirar. Toca neste
            aparelho.</UiDialogDescription
          >
        </UiDialogHeader>
        <div class="flex items-center gap-2">
          <button
            type="button"
            class="grid size-12 shrink-0 place-items-center rounded-md border text-xl font-bold transition hover:bg-accent"
            aria-label="Diminuir"
            @click="bump('oven', -1)"
          >
            −
          </button>
          <div class="relative w-full">
            <input
              v-model="ovenMinutes"
              type="text"
              inputmode="numeric"
              class="h-12 w-full rounded-md border bg-background text-center text-2xl font-bold tabular-nums outline-none focus:ring-1 focus:ring-ring"
              aria-label="Minutos do timer"
            />
            <span
              class="pointer-events-none absolute inset-y-0 right-3 grid place-items-center text-sm text-muted-foreground"
              >min</span
            >
          </div>
          <button
            type="button"
            class="grid size-12 shrink-0 place-items-center rounded-md border text-xl font-bold transition hover:bg-accent"
            aria-label="Aumentar"
            @click="bump('oven', 1)"
          >
            +
          </button>
        </div>
        <UiDialogFooter>
          <button
            v-if="ovenRow && oven.get(ovenKey(ovenRow))"
            type="button"
            class="mr-auto rounded-md border px-3 py-2 text-sm font-medium text-red-700 transition hover:bg-red-500/10 dark:text-red-300"
            @click="cancelOven()"
          >
            Cancelar timer
          </button>
          <button
            type="button"
            class="rounded-md border px-3 py-2 text-sm font-medium transition hover:bg-accent"
            @click="ovenRow = null"
          >
            Fechar
          </button>
          <button
            type="button"
            :disabled="!(parseFloat(ovenMinutes.replace(',', '.')) >= 1)"
            class="rounded-md border border-transparent bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
            @click="confirmOven()"
          >
            Iniciar timer
          </button>
        </UiDialogFooter>
      </UiDialogContent>
    </UiDialog>

    <!-- pedidos vinculados -->
    <UiDialog
      :open="commitmentsRow != null"
      @update:open="
        (v) => {
          if (!v) commitmentsRow = null;
        }
      "
    >
      <UiDialogContent class="sm:max-w-md">
        <UiDialogHeader>
          <UiDialogTitle
            >{{ commitmentsRow ? rowCommittedUnits(commitmentsRow) : 0 }} un.
            comprometidas · {{ commitmentsRow?.output_sku }}</UiDialogTitle
          >
          <UiDialogDescription
            >Encomendas confirmadas que dependem desta
            produção.</UiDialogDescription
          >
        </UiDialogHeader>
        <ul class="flex flex-col gap-2 text-sm">
          <li
            v-for="commitment in commitmentsList"
            :key="commitment.ref"
            class="flex items-center justify-between gap-3 rounded-md border p-2.5"
          >
            <span class="inline-flex items-center gap-2">
              <Icon
                name="lucide:shopping-bag"
                class="size-4 text-muted-foreground"
              />
              <span class="font-medium">{{ commitment.ref }}</span>
              <UiBadge variant="outline" class="px-1.5 py-0 text-[0.65rem]">{{
                commitment.status_label
              }}</UiBadge>
            </span>
            <span class="tabular-nums text-muted-foreground"
              >{{ commitment.qty_required }} un.</span
            >
          </li>
        </ul>
        <UiDialogFooter>
          <button
            type="button"
            class="rounded-md border px-3 py-2 text-sm font-medium transition hover:bg-accent"
            @click="commitmentsRow = null"
          >
            Fechar
          </button>
        </UiDialogFooter>
      </UiDialogContent>
    </UiDialog>

    <!-- explicação da sugestão -->
    <UiDialog
      :open="explaining != null"
      @update:open="
        (v) => {
          if (!v) explaining = null;
        }
      "
    >
      <UiDialogContent class="sm:max-w-md">
        <UiDialogHeader>
          <UiDialogTitle>Por que {{ explaining?.quantity }}?</UiDialogTitle>
          <UiDialogDescription>
            {{ explaining?.recipe_name }} · confiança
            {{ explaining?.confidence?.toLowerCase() }}
          </UiDialogDescription>
        </UiDialogHeader>
        <ul
          v-if="explaining?.explanation_parts?.length"
          class="flex flex-col gap-2 text-sm"
        >
          <li
            v-for="part in explaining.explanation_parts"
            :key="part"
            class="flex items-start gap-2"
          >
            <Icon
              name="lucide:corner-down-right"
              class="mt-0.5 size-4 shrink-0 text-muted-foreground"
            />
            <span>{{ part }}</span>
          </li>
        </ul>
        <p v-else class="text-sm text-muted-foreground">
          Ainda sem histórico suficiente para explicar — a sugestão usa apenas a
          margem padrão.
        </p>
        <UiDialogFooter>
          <button
            v-if="stage === 'plan' && access?.can_edit_planned"
            type="button"
            class="mr-auto rounded-md border border-transparent bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90"
            @click="planFromExplanation()"
          >
            Planejar esta sugestão
          </button>
          <button
            type="button"
            class="rounded-md border px-3 py-2 text-sm font-medium transition hover:bg-accent"
            @click="explaining = null"
          >
            Fechar
          </button>
        </UiDialogFooter>
      </UiDialogContent>
    </UiDialog>

    <ShortageDialog
      :shortage="shortage"
      @update:open="
        (v) => {
          if (!v) shortage = null;
        }
      "
      @confirm="overrideShortage"
    />
  </main>
</template>
