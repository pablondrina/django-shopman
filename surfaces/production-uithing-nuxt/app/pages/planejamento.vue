<script setup lang="ts">
// Production planning — the matrix (the old Admin planning surface, now Nuxt).
// Reads the production board projection via useProductionBoard; each row is an
// output SKU with its planned/started/finished totals, the demand suggestion
// (tap to see why), an inline plan input and a start action. The date selector
// gives the multi-day horizon (default: tomorrow after noon). Plan/start POST
// through the django proxy and reconcile. Tablet/touch-first.
import { matchesRowQuery, rowHasActivity, startableWorkOrder } from "~/presentation/production";
import type { ProductionMatrixRowProjection, ProductionShortageError, ProductionSuggestionProjection } from "~/types/production";

const { board, rows, counts, dateDisplay, selectedDate, pending, error, refresh, isBusy, plan, start } = useProductionBoard();

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

// Sugestão explicável: bottom-sheet com o basis em frases.
const explaining = ref<ProductionSuggestionProjection | null>(null);
const showAll = ref(false);
const visibleRows = computed<ProductionMatrixRowProjection[]>(() =>
  rows.value
    .filter((r) => showAll.value || rowHasActivity(r))
    .filter((r) => matchesRowQuery(r, query.value)),
);

// per-row plan quantity inputs, seeded from the suggestion when present.
const planInputs = reactive<Record<string, string>>({});
function planValue(row: ProductionMatrixRowProjection): string {
  if (planInputs[row.output_sku] != null) return planInputs[row.output_sku]!;
  return row.suggestion?.quantity ?? "";
}

const shortage = ref<ProductionShortageError | null>(null);

async function submitPlan(row: ProductionMatrixRowProjection, source?: string) {
  if (row.recipe_pk == null || !board.value) return;
  const qty = (planInputs[row.output_sku] ?? row.suggestion?.quantity ?? "").trim();
  if (!qty) return;
  const res = await plan(row.output_sku, {
    recipe_id: row.recipe_pk,
    quantity: qty,
    target_date: board.value.selected_date,
    position_ref: board.value.selected_position_ref || undefined,
    source,
  });
  if (res.ok) {
    delete planInputs[row.output_sku];
    useSonner.success(`Planejado: ${row.output_sku} × ${qty}`);
  } else if (res.shortage) {
    shortage.value = res.shortage;
  }
}

async function submitStart(row: ProductionMatrixRowProjection) {
  const wo = startableWorkOrder(row);
  if (!wo) return;
  const res = await start(row.output_sku, wo.pk, wo.planned_qty);
  if (res.ok) useSonner.success(`Produção iniciada: ${row.output_sku} × ${wo.planned_qty}`);
}
</script>

<template>
  <main class="flex min-h-screen flex-col">
    <ProductionHeader v-model:query="query" title="Planejamento" :count="counts?.planned ?? 0" count-label="planejados" :pending="pending" @refresh="refresh()" />

    <section class="min-h-0 flex-1 overflow-auto p-3 md:p-4">
      <div class="mb-3 flex flex-wrap items-center gap-3">
        <div class="flex items-center gap-1 rounded-lg border bg-background p-0.5" role="group" aria-label="Data do planejamento">
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
          Plan {{ counts.planned_qty }} · Iniciado {{ counts.started_qty }} · Concluído {{ counts.finished_qty }}
        </span>
        <label class="ml-auto inline-flex cursor-pointer items-center gap-2 text-sm text-muted-foreground">
          <input v-model="showAll" type="checkbox" class="size-4 rounded border" />
          Mostrar todas as receitas
        </label>
      </div>

      <p v-if="pending && !rows.length" class="text-sm text-muted-foreground">Carregando…</p>
      <p v-else-if="error" class="rounded-md border border-red-500/30 bg-red-500/5 p-4 text-sm text-red-700 dark:text-red-400">
        Falha ao carregar o planejamento. Reconectando…
      </p>

      <div v-else-if="!visibleRows.length" class="grid place-items-center gap-2 rounded-lg border border-dashed py-16 text-center text-muted-foreground">
        <Icon name="lucide:clipboard-list" class="size-8" />
        <p class="text-base font-medium">Nada planejado para hoje.</p>
        <button type="button" class="text-sm text-primary underline-offset-2 hover:underline" @click="showAll = true">Ver todas as receitas</button>
      </div>

      <div v-else class="overflow-hidden rounded-lg border">
        <table class="w-full text-sm">
          <thead class="bg-muted/50 text-left text-xs uppercase tracking-wide text-muted-foreground">
            <tr>
              <th class="px-3 py-2 font-semibold">Produto</th>
              <th class="px-3 py-2 text-right font-semibold">Sugestão</th>
              <th class="px-3 py-2 text-right font-semibold">Plan / Inic / Concl</th>
              <th class="px-3 py-2 font-semibold">Planejar</th>
              <th class="px-3 py-2 font-semibold"></th>
            </tr>
          </thead>
          <tbody class="divide-y">
            <tr v-for="row in visibleRows" :key="row.output_sku" class="hover:bg-muted/30">
              <td class="px-3 py-2">
                <p class="font-bold">{{ row.output_sku }}</p>
                <p class="truncate text-xs text-muted-foreground">{{ row.recipe_name }}</p>
              </td>
              <td class="px-3 py-2 text-right">
                <button
                  v-if="row.suggestion"
                  type="button"
                  class="group inline-flex flex-col items-end rounded-md px-1.5 py-0.5 transition hover:bg-accent"
                  :aria-label="`Por que ${row.suggestion.quantity} de ${row.recipe_name}?`"
                  @click="explaining = row.suggestion"
                >
                  <span class="inline-flex items-center gap-1 font-semibold tabular-nums">
                    {{ row.suggestion.quantity }}
                    <Icon name="lucide:info" class="size-3.5 text-muted-foreground transition group-hover:text-foreground" />
                  </span>
                  <span class="text-[0.7rem] text-muted-foreground">{{ row.suggestion.confidence }} · méd {{ row.suggestion.avg_demand }}</span>
                </button>
                <span v-else class="text-muted-foreground">—</span>
              </td>
              <td class="px-3 py-2 text-right tabular-nums">
                <span :class="row.planned_qty !== '0' ? 'font-semibold text-blue-700 dark:text-blue-300' : 'text-muted-foreground'">{{ row.planned_qty }}</span>
                <span class="text-muted-foreground"> / </span>
                <span :class="row.started_qty !== '0' ? 'font-semibold text-amber-700 dark:text-amber-300' : 'text-muted-foreground'">{{ row.started_qty }}</span>
                <span class="text-muted-foreground"> / </span>
                <span :class="row.finished_qty !== '0' ? 'font-semibold text-green-700 dark:text-green-300' : 'text-muted-foreground'">{{ row.finished_qty }}</span>
              </td>
              <td class="px-3 py-2">
                <div class="flex items-center gap-1.5">
                  <input
                    :value="planValue(row)"
                    type="text"
                    inputmode="decimal"
                    placeholder="qtd"
                    class="h-9 w-20 rounded-md border bg-background px-2 text-sm tabular-nums outline-none focus:ring-1 focus:ring-ring"
                    :aria-label="`Quantidade planejada de ${row.output_sku}`"
                    :disabled="row.recipe_pk == null || isBusy(row.output_sku)"
                    @input="planInputs[row.output_sku] = ($event.target as HTMLInputElement).value"
                  />
                  <button
                    type="button"
                    class="inline-flex items-center gap-1 rounded-md border border-transparent bg-primary px-2.5 py-1.5 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
                    :disabled="row.recipe_pk == null || isBusy(row.output_sku) || !planValue(row).trim()"
                    @click="submitPlan(row, row.suggestion ? 'suggested' : undefined)"
                  >
                    <Icon name="lucide:calendar-plus" class="size-4" /> Planejar
                  </button>
                </div>
              </td>
              <td class="px-3 py-2">
                <button
                  v-if="startableWorkOrder(row)"
                  type="button"
                  class="inline-flex items-center gap-1 rounded-md border px-2.5 py-1.5 text-sm font-medium transition hover:bg-accent disabled:opacity-50"
                  :disabled="isBusy(row.output_sku)"
                  @click="submitStart(row)"
                >
                  <Icon name="lucide:play" class="size-4" /> Iniciar
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <ShortageDialog :shortage="shortage" @update:open="(v) => { if (!v) shortage = null }" />

    <!-- suggestion explanation -->
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
          <button type="button" class="rounded-md border px-3 py-2 text-sm font-medium transition hover:bg-accent" @click="explaining = null">Fechar</button>
        </UiDialogFooter>
      </UiDialogContent>
    </UiDialog>
  </main>
</template>
