<script setup lang="ts">
// Mise en place — the day's aggregated ingredient list (craft.needs with the
// per-recipe breakdown). The baker separates and checks off each item; the
// check is shift-local (localStorage). "Matéria-prima" toggle explodes
// sub-recipes down to raw materials. Stock balance column appears only when
// the ingredient ledger has readings (graceful degrade). Tablet/touch-first.
import type { MiseEnPlaceLineProjection } from "~/types/production";

const {
  projection,
  lines,
  expand,
  pending,
  error,
  refresh,
  isChecked,
  toggleChecked,
  checkedCount,
} = useMiseEnPlace();

const route = useRoute();
const query = ref(typeof route.query.q === "string" ? route.query.q : "");
watch(() => route.query.q, (q) => { if (typeof q === "string") query.value = q; });

const visibleLines = computed<MiseEnPlaceLineProjection[]>(() => {
  const term = query.value.trim().toLowerCase();
  if (!term) return lines.value;
  return lines.value.filter(
    (line) =>
      line.sku.toLowerCase().includes(term) || line.name.toLowerCase().includes(term),
  );
});

const expandedSku = ref<string | null>(null);
function toggleBreakdown(line: MiseEnPlaceLineProjection) {
  if (!line.breakdown.length) return;
  expandedSku.value = expandedSku.value === line.sku ? null : line.sku;
}
</script>

<template>
  <main class="flex min-h-screen flex-col">
    <ProductionHeader
      v-model:query="query"
      title="Mise en place"
      :count="lines.length"
      count-label="insumos"
      :pending="pending"
      @refresh="refresh()"
    />

    <section class="min-h-0 flex-1 overflow-auto p-3 md:p-4">
      <div class="mb-3 flex flex-wrap items-center gap-3">
        <span class="text-sm text-muted-foreground">{{ projection?.selected_date_display }}</span>
        <span v-if="projection?.work_order_count" class="text-sm tabular-nums text-muted-foreground">
          {{ projection.work_order_count }} orden{{ projection.work_order_count > 1 ? "s" : "" }} aberta{{ projection.work_order_count > 1 ? "s" : "" }}
          · {{ checkedCount }}/{{ lines.length }} separados
        </span>
        <label class="ml-auto inline-flex cursor-pointer items-center gap-2 text-sm text-muted-foreground">
          <input v-model="expand" type="checkbox" class="size-4 rounded border" />
          Explodir até matéria-prima
        </label>
      </div>

      <p v-if="pending && !lines.length" class="text-sm text-muted-foreground">Carregando…</p>
      <p v-else-if="error" class="rounded-md border border-red-500/30 bg-red-500/5 p-4 text-sm text-red-700 dark:text-red-400">
        Falha ao carregar a lista. Reconectando…
      </p>

      <div v-else-if="!lines.length" class="grid place-items-center gap-2 rounded-lg border border-dashed py-16 text-center text-muted-foreground">
        <Icon name="lucide:scale" class="size-8" />
        <p class="text-base font-medium">Nada para separar hoje.</p>
        <NuxtLink to="/planejamento" class="text-sm text-primary underline-offset-2 hover:underline">Planejar produção</NuxtLink>
      </div>

      <div v-else class="overflow-hidden rounded-lg border">
        <table class="w-full text-sm">
          <thead class="bg-muted/50 text-left text-xs uppercase tracking-wide text-muted-foreground">
            <tr>
              <th class="w-12 px-3 py-2"><span class="sr-only">Separado</span></th>
              <th class="px-3 py-2 font-semibold">Insumo</th>
              <th class="px-3 py-2 text-right font-semibold">Quantidade</th>
              <th v-if="projection?.has_stock_readings" class="px-3 py-2 text-right font-semibold">Saldo</th>
              <th class="w-10 px-3 py-2"><span class="sr-only">Detalhe</span></th>
            </tr>
          </thead>
          <tbody class="divide-y">
            <template v-for="line in visibleLines" :key="line.sku">
              <tr
                class="transition"
                :class="isChecked(line.sku) ? 'bg-muted/40 text-muted-foreground' : 'hover:bg-muted/30'"
              >
                <td class="px-3 py-2">
                  <input
                    type="checkbox"
                    class="size-5 rounded border"
                    :checked="isChecked(line.sku)"
                    :aria-label="`Marcar ${line.name} como separado`"
                    @change="toggleChecked(line.sku)"
                  />
                </td>
                <td class="px-3 py-2">
                  <p class="font-bold" :class="isChecked(line.sku) ? 'line-through decoration-1' : ''">
                    {{ line.name }}
                  </p>
                  <p class="flex items-center gap-1.5 text-xs text-muted-foreground">
                    {{ line.sku }}
                    <UiBadge v-if="line.is_subrecipe" variant="outline" class="px-1.5 py-0 text-[0.65rem]">pré-preparo</UiBadge>
                  </p>
                </td>
                <td class="px-3 py-2 text-right font-semibold tabular-nums">{{ line.quantity_display }}</td>
                <td v-if="projection?.has_stock_readings" class="px-3 py-2 text-right tabular-nums">
                  <span :class="line.is_short ? 'font-semibold text-red-700 dark:text-red-400' : 'text-muted-foreground'">
                    {{ line.available_display || "—" }}
                  </span>
                  <p v-if="line.is_short" class="text-[0.7rem] font-medium text-red-700 dark:text-red-400">falta</p>
                </td>
                <td class="px-3 py-2 text-right">
                  <button
                    v-if="line.breakdown.length"
                    type="button"
                    class="inline-flex size-8 items-center justify-center rounded-md border transition hover:bg-accent"
                    :aria-label="`Ver receitas que usam ${line.name}`"
                    :aria-expanded="expandedSku === line.sku"
                    @click="toggleBreakdown(line)"
                  >
                    <Icon :name="expandedSku === line.sku ? 'lucide:chevron-up' : 'lucide:chevron-down'" class="size-4" />
                  </button>
                </td>
              </tr>
              <tr v-if="expandedSku === line.sku" class="bg-muted/20">
                <td></td>
                <td colspan="3" class="px-3 pb-2.5 pt-0.5">
                  <ul class="flex flex-col gap-1 text-xs text-muted-foreground">
                    <li v-for="row in line.breakdown" :key="row.output_sku" class="flex items-center justify-between gap-3">
                      <span>{{ row.recipe_name }} <span class="opacity-70">({{ row.output_sku }})</span></span>
                      <span class="tabular-nums">{{ row.quantity_display }}</span>
                    </li>
                  </ul>
                </td>
                <td></td>
              </tr>
            </template>
          </tbody>
        </table>
        <p v-if="query && !visibleLines.length" class="border-t p-3 text-center text-sm text-muted-foreground">
          Nenhum insumo para “{{ query.trim() }}”.
        </p>
      </div>
    </section>
  </main>
</template>
