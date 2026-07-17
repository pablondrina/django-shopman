<script setup lang="ts">
// Relatórios — a lente de GESTOR do Fournil (perm fina
// backstage.view_production_reports; o gate grosso de chão NÃO abre esta tela).
// Três blocos, todos servidos pela API de relatórios:
//   · Gestão do dia: rendimento médio, capacidade % e a tabela de atrasos;
//   · Relatórios por período: Histórico · Produtividade · Desperdício, com
//     filtros (datas, ficha, posto, operador) e download CSV (link direto);
//   · Mapa código-cego ↔ preparo: a correlação que as telas de chão NUNCA
//     mostram (etiquetas circulam só com o código) — aqui é a visão de gestor.
// Sem gráficos: tabelas caladas e números pré-formatados pelas projections.
import { isStale, isoForOffset } from "~/presentation/production";
import {
  REPORT_KINDS,
  type ReportFiltersQuery,
  type ReportKind,
} from "~/presentation/reports";

// ── Gestão do dia (KPIs + atrasos + mapa cego) ─────────────────────────────
const selectedDate = ref(isoForOffset(0));
const dateChips = [
  { iso: isoForOffset(-1), label: "Ontem" },
  { iso: isoForOffset(0), label: "Hoje" },
];

const {
  management,
  lateOrders,
  forbidden: managementForbidden,
  pending: managementPending,
  refresh: refreshManagement,
} = useProductionManagement(selectedDate);
const blindMap = useBlindMap(selectedDate);

// ── Relatórios por período ─────────────────────────────────────────────────
const kind = ref<ReportKind>("history");
const dateFrom = ref(isoForOffset(-6));
const dateTo = ref(isoForOffset(0));
const recipeRef = ref("");
const positionRef = ref("");
const operatorRef = ref("");

const filters = computed<ReportFiltersQuery>(() => ({
  report_kind: kind.value,
  date_from: dateFrom.value,
  date_to: dateTo.value,
  recipe_ref: recipeRef.value,
  position_ref: positionRef.value,
  operator_ref: operatorRef.value.trim(),
}));

const {
  reports,
  historyRows,
  operatorRows,
  wasteRows,
  availableRecipes,
  availablePositions,
  forbidden: reportsForbidden,
  csvUrl,
  pending,
  error,
  refresh,
} = useProductionReports(filters);

// 403 em qualquer bloco = mesma causa (sem a perm fina) → mensagem única e calma.
const forbidden = computed(
  () => reportsForbidden.value || managementForbidden.value,
);

const hasRows = computed(() => {
  if (kind.value === "operator_productivity") return operatorRows.value.length > 0;
  if (kind.value === "recipe_waste") return wasteRows.value.length > 0;
  return historyRows.value.length > 0;
});
const stale = computed(() =>
  isStale({ error: !!error.value, hasData: !!reports.value }),
);

function refreshAll() {
  refresh();
  refreshManagement();
  blindMap.refresh();
}
</script>

<template>
  <main class="flex min-h-screen flex-col">
    <ProductionHeader
      title="Relatórios"
      :pending="pending || managementPending"
      @refresh="refreshAll()"
    />

    <!-- Sem a perm fina de gestor: explica com calma, sem beco. -->
    <section
      v-if="forbidden"
      class="grid flex-1 place-items-center p-6 text-center"
    >
      <div class="grid max-w-md gap-2 rounded-lg border border-dashed p-10">
        <Icon name="lucide:lock" class="mx-auto size-8 text-muted-foreground" />
        <p class="text-base font-semibold">Área do gestor</p>
        <p class="text-sm text-muted-foreground">
          Os relatórios de produção pedem uma permissão de gestão que este
          operador não tem. Peça a liberação a quem administra a loja.
        </p>
        <NuxtLink
          to="/"
          class="mt-1 text-sm text-primary underline-offset-2 hover:underline"
          >Voltar para a produção</NuxtLink
        >
      </div>
    </section>

    <section v-else class="min-h-0 flex-1 overflow-auto p-3 md:p-4">
      <!-- ── Gestão do dia ─────────────────────────────────────────────── -->
      <div class="mb-3 flex flex-wrap items-center gap-3">
        <h2 class="text-base font-bold">Gestão do dia</h2>
        <div
          class="flex items-center gap-1 rounded-lg border bg-background p-0.5"
          role="group"
          aria-label="Data da gestão"
        >
          <button
            v-for="chip in dateChips"
            :key="chip.iso"
            type="button"
            class="rounded-md px-2.5 py-1.5 text-sm font-medium transition"
            :class="
              selectedDate === chip.iso
                ? 'bg-primary text-primary-foreground'
                : 'text-muted-foreground hover:bg-accent hover:text-foreground'
            "
            :aria-pressed="selectedDate === chip.iso"
            @click="selectedDate = chip.iso"
          >
            {{ chip.label }}
          </button>
        </div>
        <span
          v-if="management"
          class="text-sm text-muted-foreground"
          >{{ management.selected_date_display }}</span
        >
      </div>

      <div class="mb-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <div class="rounded-lg border bg-card p-3">
          <p class="text-xs font-medium uppercase tracking-wider text-muted-foreground">
            Rendimento médio
          </p>
          <p class="mt-1 text-2xl font-bold tabular-nums">
            {{ management?.average_yield_rate || "—" }}
          </p>
          <p class="text-xs text-muted-foreground">
            {{ management?.finished_orders ?? 0 }} OPs concluídas
          </p>
        </div>
        <div class="rounded-lg border bg-card p-3">
          <p class="text-xs font-medium uppercase tracking-wider text-muted-foreground">
            Capacidade
          </p>
          <p class="mt-1 text-2xl font-bold tabular-nums">
            <template v-if="management?.capacity_percent != null"
              >{{ management.capacity_percent }}%</template
            >
            <template v-else>—</template>
          </p>
          <p class="text-xs text-muted-foreground">
            {{
              management?.capacity_percent != null
                ? "do planejado sobre a capacidade diária"
                : "sem capacidade configurada nas fichas"
            }}
          </p>
        </div>
        <div class="rounded-lg border bg-card p-3">
          <p class="text-xs font-medium uppercase tracking-wider text-muted-foreground">
            Planejado
          </p>
          <p class="mt-1 text-2xl font-bold tabular-nums">
            {{ management?.planned_qty || "0" }}
          </p>
          <p class="text-xs text-muted-foreground">
            {{ management?.planned_orders ?? 0 }} OPs planejadas
          </p>
        </div>
        <div class="rounded-lg border bg-card p-3">
          <p class="text-xs font-medium uppercase tracking-wider text-muted-foreground">
            Perda
          </p>
          <p class="mt-1 text-2xl font-bold tabular-nums">
            {{ management?.loss_qty || "0" }}
          </p>
          <p class="text-xs text-muted-foreground">
            concluído {{ management?.finished_qty || "0" }} de
            {{ management?.started_qty || "0" }} iniciados
          </p>
        </div>
      </div>

      <div
        v-if="lateOrders.length"
        class="mb-4 overflow-hidden rounded-lg border"
      >
        <p
          class="flex items-center gap-2 border-b bg-warning/10 px-3 py-2 text-sm font-semibold text-amber-700 dark:text-amber-300"
        >
          <Icon name="lucide:timer" class="size-4" /> Atrasos em andamento
        </p>
        <table class="w-full text-sm">
          <thead
            class="bg-muted/50 text-left text-xs uppercase tracking-wide text-muted-foreground"
          >
            <tr>
              <th class="px-3 py-2 font-semibold">OP</th>
              <th class="px-3 py-2 font-semibold">Produto</th>
              <th class="px-3 py-2 text-right font-semibold">Tempo (min)</th>
              <th class="px-3 py-2 text-right font-semibold">Meta (min)</th>
              <th class="px-3 py-2 font-semibold">Operador</th>
            </tr>
          </thead>
          <tbody class="divide-y">
            <tr v-for="item in lateOrders" :key="item.pk">
              <td class="px-3 py-2 font-mono text-xs">{{ item.ref }}</td>
              <td class="px-3 py-2 font-medium">{{ item.output_sku }}</td>
              <td class="px-3 py-2 text-right tabular-nums font-semibold text-amber-700 dark:text-amber-300">
                {{ item.elapsed_minutes }}
              </td>
              <td class="px-3 py-2 text-right tabular-nums">
                {{ item.target_minutes }}
              </td>
              <td class="px-3 py-2">{{ item.operator_ref || "—" }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- ── Relatórios por período ────────────────────────────────────── -->
      <div class="mb-3 flex flex-wrap items-center gap-3">
        <h2 class="text-base font-bold">Relatórios</h2>
        <div
          class="flex items-center gap-1 rounded-lg border bg-background p-0.5"
          role="group"
          aria-label="Tipo de relatório"
        >
          <button
            v-for="entry in REPORT_KINDS"
            :key="entry.kind"
            type="button"
            class="rounded-md px-2.5 py-1.5 text-sm font-medium transition"
            :class="
              kind === entry.kind
                ? 'bg-primary text-primary-foreground'
                : 'text-muted-foreground hover:bg-accent hover:text-foreground'
            "
            :aria-pressed="kind === entry.kind"
            @click="kind = entry.kind"
          >
            {{ entry.label }}
          </button>
        </div>
        <a
          :href="csvUrl"
          download
          class="ml-auto inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-sm font-medium transition hover:bg-accent"
        >
          <Icon name="lucide:download" class="size-4" /> Baixar CSV
        </a>
      </div>

      <div
        class="mb-3 flex flex-wrap items-end gap-3 rounded-lg border bg-card p-3"
      >
        <label class="grid gap-1 text-xs font-medium text-muted-foreground">
          De
          <input
            v-model="dateFrom"
            type="date"
            class="h-9 rounded-md border bg-background px-2 text-sm text-foreground"
          />
        </label>
        <label class="grid gap-1 text-xs font-medium text-muted-foreground">
          Até
          <input
            v-model="dateTo"
            type="date"
            class="h-9 rounded-md border bg-background px-2 text-sm text-foreground"
          />
        </label>
        <label class="grid gap-1 text-xs font-medium text-muted-foreground">
          Ficha técnica
          <select
            v-model="recipeRef"
            class="h-9 rounded-md border bg-background px-2 text-sm text-foreground"
          >
            <option value="">Todas</option>
            <option
              v-for="recipe in availableRecipes"
              :key="recipe.ref"
              :value="recipe.ref"
            >
              {{ recipe.name }}
            </option>
          </select>
        </label>
        <label class="grid gap-1 text-xs font-medium text-muted-foreground">
          Posto
          <select
            v-model="positionRef"
            class="h-9 rounded-md border bg-background px-2 text-sm text-foreground"
          >
            <option value="">Todos</option>
            <option
              v-for="position in availablePositions"
              :key="position.ref"
              :value="position.ref"
            >
              {{ position.name }}
            </option>
          </select>
        </label>
        <label class="grid gap-1 text-xs font-medium text-muted-foreground">
          Operador
          <input
            v-model="operatorRef"
            type="text"
            placeholder="Nome ou usuário"
            class="h-9 rounded-md border bg-background px-2 text-sm text-foreground"
          />
        </label>
      </div>

      <div
        v-if="stale"
        role="status"
        aria-live="polite"
        class="mb-3 flex items-center gap-2 rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-sm font-medium text-amber-700 dark:text-amber-300"
      >
        <Icon name="lucide:wifi-off" class="size-4 shrink-0" />
        <span>Sem atualizar — mostrando o último relatório carregado.</span>
      </div>

      <p v-if="pending && !reports" class="text-sm text-muted-foreground">
        Carregando…
      </p>
      <div
        v-else-if="error && !reports"
        class="grid place-items-center gap-2 rounded-lg border border-dashed border-destructive/30 py-16 text-center text-muted-foreground"
      >
        <Icon name="lucide:cloud-off" class="size-8 text-destructive/70" />
        <p class="text-base font-medium text-foreground">
          Não foi possível carregar os relatórios.
        </p>
        <button
          type="button"
          class="mt-1 inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-sm font-medium transition hover:bg-accent"
          @click="refresh()"
        >
          <Icon name="lucide:refresh-cw" class="size-4" /> Tentar de novo
        </button>
      </div>
      <div
        v-else-if="!hasRows"
        class="grid place-items-center gap-2 rounded-lg border border-dashed py-16 text-center text-muted-foreground"
      >
        <Icon name="lucide:table-2" class="size-8" />
        <p class="text-base font-medium">Nada produzido nesse período.</p>
        <p class="text-sm">Ajuste as datas ou os filtros acima.</p>
      </div>

      <!-- Histórico por OP -->
      <div
        v-else-if="kind === 'history'"
        class="overflow-x-auto rounded-lg border"
      >
        <table class="w-full min-w-[64rem] text-sm">
          <thead
            class="bg-muted/50 text-left text-xs uppercase tracking-wide text-muted-foreground"
          >
            <tr>
              <th class="px-3 py-2 font-semibold">OP</th>
              <th class="px-3 py-2 font-semibold">Data</th>
              <th class="px-3 py-2 font-semibold">Ficha técnica</th>
              <th class="px-3 py-2 font-semibold">Posto</th>
              <th class="px-3 py-2 text-right font-semibold">Planejado</th>
              <th class="px-3 py-2 text-right font-semibold">Iniciado</th>
              <th class="px-3 py-2 text-right font-semibold">Concluído</th>
              <th class="px-3 py-2 text-right font-semibold">Perda</th>
              <th class="px-3 py-2 text-right font-semibold">Rendimento</th>
              <th class="px-3 py-2 font-semibold">Operador</th>
              <th class="px-3 py-2 text-right font-semibold">Tempo (min)</th>
            </tr>
          </thead>
          <tbody class="divide-y">
            <tr v-for="row in historyRows" :key="row.ref" class="hover:bg-muted/30">
              <td class="px-3 py-2 font-mono text-xs">{{ row.ref }}</td>
              <td class="px-3 py-2 tabular-nums">{{ row.date }}</td>
              <td class="px-3 py-2 font-medium">{{ row.recipe_name }}</td>
              <td class="px-3 py-2">{{ row.position_ref || "—" }}</td>
              <td class="px-3 py-2 text-right tabular-nums">{{ row.qty_planned }}</td>
              <td class="px-3 py-2 text-right tabular-nums">{{ row.qty_started || "—" }}</td>
              <td class="px-3 py-2 text-right tabular-nums">{{ row.qty_finished || "—" }}</td>
              <td class="px-3 py-2 text-right tabular-nums">{{ row.qty_loss }}</td>
              <td class="px-3 py-2 text-right tabular-nums">{{ row.yield_rate || "—" }}</td>
              <td class="px-3 py-2">{{ row.operator_ref || "—" }}</td>
              <td class="px-3 py-2 text-right tabular-nums">{{ row.duration_minutes || "—" }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Produtividade por operador -->
      <div
        v-else-if="kind === 'operator_productivity'"
        class="overflow-x-auto rounded-lg border"
      >
        <table class="w-full text-sm">
          <thead
            class="bg-muted/50 text-left text-xs uppercase tracking-wide text-muted-foreground"
          >
            <tr>
              <th class="px-3 py-2 font-semibold">Operador</th>
              <th class="px-3 py-2 text-right font-semibold">Ordens</th>
              <th class="px-3 py-2 text-right font-semibold">Qtd total</th>
              <th class="px-3 py-2 text-right font-semibold">Rendimento médio</th>
              <th class="px-3 py-2 text-right font-semibold">Tempo médio (min)</th>
            </tr>
          </thead>
          <tbody class="divide-y">
            <tr
              v-for="row in operatorRows"
              :key="row.operator_ref"
              class="hover:bg-muted/30"
            >
              <td class="px-3 py-2 font-medium">{{ row.operator_name }}</td>
              <td class="px-3 py-2 text-right tabular-nums">{{ row.wo_count }}</td>
              <td class="px-3 py-2 text-right tabular-nums">{{ row.qty_total }}</td>
              <td class="px-3 py-2 text-right tabular-nums">{{ row.yield_avg || "—" }}</td>
              <td class="px-3 py-2 text-right tabular-nums">{{ row.duration_avg_minutes || "—" }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Desperdício por ficha -->
      <div v-else class="overflow-x-auto rounded-lg border">
        <table class="w-full text-sm">
          <thead
            class="bg-muted/50 text-left text-xs uppercase tracking-wide text-muted-foreground"
          >
            <tr>
              <th class="px-3 py-2 font-semibold">Ficha técnica</th>
              <th class="px-3 py-2 text-right font-semibold">Ordens</th>
              <th class="px-3 py-2 text-right font-semibold">Perda total</th>
              <th class="px-3 py-2 text-right font-semibold">Rendimento médio</th>
            </tr>
          </thead>
          <tbody class="divide-y">
            <tr
              v-for="row in wasteRows"
              :key="row.recipe_ref"
              class="hover:bg-muted/30"
            >
              <td class="px-3 py-2 font-medium">{{ row.recipe_name }}</td>
              <td class="px-3 py-2 text-right tabular-nums">{{ row.wo_count }}</td>
              <td class="px-3 py-2 text-right tabular-nums">{{ row.loss_total }}</td>
              <td class="px-3 py-2 text-right tabular-nums">{{ row.yield_avg || "—" }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- ── Mapa código-cego ↔ preparo (visão de gestor) ──────────────── -->
      <div class="mt-6">
        <div class="mb-2 flex flex-wrap items-center gap-2">
          <h2 class="text-base font-bold">Mapa código-cego</h2>
          <UiBadge variant="outline" class="px-1.5 py-0 text-xs"
            >visão de gestor</UiBadge
          >
        </div>
        <p class="mb-3 max-w-2xl text-sm text-muted-foreground">
          As etiquetas de pesagem circulam pela cozinha apenas com o código do
          dia. Esta tabela é a única correlação código ↔ preparo — ela não
          aparece nas telas de chão.
        </p>
        <div
          v-if="!blindMap.rows.value.length"
          class="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground"
        >
          Nenhum preparo aberto nesta data — sem códigos para correlacionar.
        </div>
        <div v-else class="max-w-2xl overflow-hidden rounded-lg border">
          <table class="w-full text-sm">
            <thead
              class="bg-muted/50 text-left text-xs uppercase tracking-wide text-muted-foreground"
            >
              <tr>
                <th class="px-3 py-2 font-semibold">Código</th>
                <th class="px-3 py-2 font-semibold">Preparo</th>
                <th class="px-3 py-2 text-right font-semibold">Rendimento</th>
              </tr>
            </thead>
            <tbody class="divide-y">
              <tr
                v-for="row in blindMap.rows.value"
                :key="row.code"
                class="hover:bg-muted/30"
              >
                <td class="px-3 py-2">
                  <span
                    class="rounded-md border border-primary/30 bg-primary/5 px-2 py-0.5 font-mono text-sm font-bold tracking-wide text-primary"
                    >{{ row.code }}</span
                  >
                </td>
                <td class="px-3 py-2 font-medium">{{ row.name }}</td>
                <td class="px-3 py-2 text-right tabular-nums">
                  {{ row.output_quantity_display }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>
  </main>
</template>
