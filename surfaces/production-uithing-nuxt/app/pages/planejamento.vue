<script setup lang="ts">
// Production planning — the matrix (the old Admin planning surface, now Nuxt).
// Reads the production board projection via useProductionBoard; each row is an
// output SKU with its planned/started/finished totals, the demand suggestion, an
// inline plan input (set the planned quantity) and a start action for the first
// planned WO. Plan/start POST through the django proxy and reconcile. An order
// shortage on plan opens the shortage modal. Tablet/touch-first.
import { matchesRowQuery, rowHasActivity, startableWorkOrder } from "~/presentation/production";
import type { ProductionMatrixRowProjection, ProductionShortageError } from "~/types/production";

const { board, rows, counts, dateDisplay, pending, error, refresh, isBusy, plan, start } = useProductionBoard();

const query = ref("");
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
                <span v-if="row.suggestion" class="inline-flex flex-col items-end">
                  <span class="font-semibold tabular-nums">{{ row.suggestion.quantity }}</span>
                  <span class="text-[0.7rem] text-muted-foreground">{{ row.suggestion.confidence }} · méd {{ row.suggestion.avg_demand }}</span>
                </span>
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
  </main>
</template>
