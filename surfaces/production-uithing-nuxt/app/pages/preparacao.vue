<script setup lang="ts">
// Preparação (mise en place) — the day's separation & weighing station.
// Two lenses over the same planned WOs:
//   · "Insumos": aggregated ingredient list (checklist local ao turno) — bom
//     para conferir provisionamento ("quanto de farinha no total?").
//   · "Por preparo": each prep with its scaled ingredients — é a pesagem real,
//     e de onde saem as ETIQUETAS CEGAS (código do dia, ingrediente, peso,
//     data; nunca o nome da receita — o mapa código↔preparo é visão de gestor
//     no Admin). Impressão via print CSS: só as etiquetas saem no papel.
// Tablet/touch-first.
import type { MiseEnPlaceLineProjection } from "~/types/production";

// Preparação olha hoje por padrão (a pesagem é do dia); amanhã na véspera.
function isoFor(offsetDays: number): string {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}
const selectedDate = ref(isoFor(0));
const dateChips = [
  { iso: isoFor(0), label: "Hoje" },
  { iso: isoFor(1), label: "Amanhã" },
];

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
} = useMiseEnPlace(selectedDate);
const weighing = useWeighing(selectedDate);

const mode = ref<"insumos" | "preparos">("insumos");

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

const visibleTickets = computed(() => {
  const term = query.value.trim().toLowerCase();
  if (!term) return weighing.tickets.value;
  return weighing.tickets.value.filter(
    (ticket) =>
      ticket.name.toLowerCase().includes(term) ||
      ticket.output_sku.toLowerCase().includes(term) ||
      ticket.blind_code.toLowerCase().includes(term) ||
      ticket.ingredients.some((ing) => ing.name.toLowerCase().includes(term)),
  );
});

const expandedSku = ref<string | null>(null);
function toggleBreakdown(line: MiseEnPlaceLineProjection) {
  if (!line.breakdown.length) return;
  expandedSku.value = expandedSku.value === line.sku ? null : line.sku;
}

// Dois artefatos de impressão, papéis distintos:
//   · etiquetas CEGAS de pesagem (uma por preparo × ingrediente) — só o
//     código do dia, para qualquer colaborador pesar sem correlacionar;
//   · etiquetas EXPLÍCITAS do preparo pronto (uma por preparo) — a massa
//     feita ganha nome, data, rendimento e objetivo (o sigilo é da pesagem,
//     não do produto).
const printMode = ref<"pesagem" | "preparo">("pesagem");

const labels = computed(() =>
  weighing.tickets.value.flatMap((ticket) =>
    ticket.ingredients.map((ing) => ({
      code: ticket.blind_code,
      ingredient: ing.name,
      weight: ing.quantity_display,
      date: weighing.dateDisplay.value,
      key: `${ticket.blind_code}-${ing.sku}`,
    })),
  ),
);

function printLabels(kind: "pesagem" | "preparo") {
  printMode.value = kind;
  mode.value = "preparos";
  nextTick(() => window.print());
}

const isPending = computed(() => (mode.value === "insumos" ? pending.value : weighing.pending.value));
function refreshAll() {
  refresh();
  weighing.refresh();
}
</script>

<template>
  <main class="flex min-h-screen flex-col">
    <div class="print:hidden">
      <ProductionHeader
        v-model:query="query"
        title="Preparação"
        :count="mode === 'insumos' ? lines.length : visibleTickets.length"
        :count-label="mode === 'insumos' ? 'insumos' : 'preparos'"
        :pending="isPending"
        @refresh="refreshAll()"
      />
    </div>

    <section class="min-h-0 flex-1 overflow-auto p-3 md:p-4 print:hidden">
      <div class="mb-3 flex flex-wrap items-center gap-3">
        <div class="flex items-center gap-1 rounded-lg border bg-background p-0.5" role="group" aria-label="Data da preparação">
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
        </div>

        <div class="flex items-center gap-1 rounded-lg border bg-background p-0.5" role="group" aria-label="Modo de visualização">
          <button
            type="button"
            class="rounded-md px-2.5 py-1.5 text-sm font-medium transition"
            :class="mode === 'insumos' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-accent hover:text-foreground'"
            :aria-pressed="mode === 'insumos'"
            @click="mode = 'insumos'"
          >
            Insumos
          </button>
          <button
            type="button"
            class="rounded-md px-2.5 py-1.5 text-sm font-medium transition"
            :class="mode === 'preparos' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-accent hover:text-foreground'"
            :aria-pressed="mode === 'preparos'"
            @click="mode = 'preparos'"
          >
            Por preparo
          </button>
        </div>

        <span v-if="mode === 'insumos' && projection?.work_order_count" class="text-sm tabular-nums text-muted-foreground">
          {{ checkedCount }}/{{ lines.length }} separados
        </span>

        <div class="ml-auto flex items-center gap-3">
          <label v-if="mode === 'insumos'" class="inline-flex cursor-pointer items-center gap-2 text-sm text-muted-foreground">
            <input v-model="expand" type="checkbox" class="size-4 rounded border" />
            Explodir até matéria-prima
          </label>
          <template v-if="mode === 'preparos' && visibleTickets.length">
            <button
              type="button"
              class="inline-flex items-center gap-1.5 rounded-md border border-transparent bg-primary px-2.5 py-1.5 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90"
              @click="printLabels('pesagem')"
            >
              <Icon name="lucide:printer" class="size-4" /> Etiquetas de pesagem
            </button>
            <button
              type="button"
              class="inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-sm font-medium transition hover:bg-accent"
              title="Adesivo explícito da massa pronta: nome, data, rendimento e objetivo"
              @click="printLabels('preparo')"
            >
              <Icon name="lucide:tag" class="size-4" /> Etiquetas do preparo
            </button>
          </template>
        </div>
      </div>

      <!-- ── Modo Insumos: agregado do dia (provisionamento + checklist) ── -->
      <template v-if="mode === 'insumos'">
        <p v-if="pending && !lines.length" class="text-sm text-muted-foreground">Carregando…</p>
        <p v-else-if="error" class="rounded-md border border-red-500/30 bg-red-500/5 p-4 text-sm text-red-700 dark:text-red-400">
          Falha ao carregar a lista. Reconectando…
        </p>

        <div v-else-if="!lines.length" class="grid place-items-center gap-2 rounded-lg border border-dashed py-16 text-center text-muted-foreground">
          <Icon name="lucide:scale" class="size-8" />
          <p class="text-base font-medium">Nada para separar nesta data.</p>
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
      </template>

      <!-- ── Modo Por preparo: a pesagem real (fonte das etiquetas) ── -->
      <template v-else>
        <p v-if="weighing.pending.value && !weighing.tickets.value.length" class="text-sm text-muted-foreground">Carregando…</p>
        <p v-else-if="weighing.error.value" class="rounded-md border border-red-500/30 bg-red-500/5 p-4 text-sm text-red-700 dark:text-red-400">
          Falha ao carregar os preparos. Reconectando…
        </p>

        <div v-else-if="!weighing.tickets.value.length" class="grid place-items-center gap-2 rounded-lg border border-dashed py-16 text-center text-muted-foreground">
          <Icon name="lucide:scale" class="size-8" />
          <p class="text-base font-medium">Nenhum preparo para pesar nesta data.</p>
          <NuxtLink to="/planejamento" class="text-sm text-primary underline-offset-2 hover:underline">Planejar produção</NuxtLink>
        </div>

        <div v-else class="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          <article v-for="ticket in visibleTickets" :key="ticket.recipe_ref" class="flex flex-col gap-2.5 rounded-lg border bg-card p-3 shadow-sm">
            <header class="flex items-start justify-between gap-2">
              <div class="min-w-0">
                <p class="text-base font-bold leading-tight">{{ ticket.name }}</p>
                <p class="text-xs text-muted-foreground">{{ ticket.output_quantity_display }} · {{ ticket.output_sku }}</p>
              </div>
              <span
                class="shrink-0 rounded-md border border-primary/30 bg-primary/5 px-2 py-0.5 font-mono text-sm font-bold tracking-wide text-primary"
                title="Código cego do dia — vai nas etiquetas no lugar do nome"
              >{{ ticket.blind_code }}</span>
            </header>
            <ul class="flex flex-col divide-y text-sm">
              <li v-for="ing in ticket.ingredients" :key="ing.sku" class="flex items-center justify-between gap-3 py-1.5">
                <span class="min-w-0 truncate">{{ ing.name }}</span>
                <span class="shrink-0 font-semibold tabular-nums">{{ ing.quantity_display }}</span>
              </li>
            </ul>
            <footer v-if="ticket.sources_display" class="text-xs text-muted-foreground">
              Objetivo: {{ ticket.sources_display }}
            </footer>
          </article>
        </div>
        <p v-if="query && !visibleTickets.length && weighing.tickets.value.length" class="mt-3 rounded-md border border-dashed p-3 text-center text-sm text-muted-foreground">
          Nenhum preparo para “{{ query.trim() }}”.
        </p>
      </template>
    </section>

    <!-- ── Etiquetas CEGAS de pesagem (só existem no papel) ──
         Uma por pesagem: código do dia, ingrediente, peso, data. SEM nome de
         receita — o colaborador pesa sem correlacionar; o mapa é do gestor. -->
    <section v-if="printMode === 'pesagem'" class="hidden print:block" aria-hidden="true">
      <div class="grid grid-cols-2 gap-2">
        <div
          v-for="label in labels"
          :key="label.key"
          class="flex break-inside-avoid flex-col gap-0.5 rounded border border-black p-2"
        >
          <div class="flex items-baseline justify-between gap-2">
            <span class="font-mono text-2xl font-bold tracking-widest">{{ label.code }}</span>
            <span class="text-[0.65rem]">{{ label.date }}</span>
          </div>
          <span class="text-sm">{{ label.ingredient }}</span>
          <span class="text-lg font-bold tabular-nums">{{ label.weight }}</span>
        </div>
      </div>
    </section>

    <!-- ── Etiquetas EXPLÍCITAS do preparo pronto ──
         Uma por preparo: a massa feita se identifica — nome, data, rendimento
         e objetivo. O código cego aparece pequeno só para casar com os potes
         pesados. -->
    <section v-else class="hidden print:block" aria-hidden="true">
      <div class="grid grid-cols-2 gap-2">
        <div
          v-for="ticket in weighing.tickets.value"
          :key="ticket.recipe_ref"
          class="flex break-inside-avoid flex-col gap-0.5 rounded border border-black p-2"
        >
          <div class="flex items-baseline justify-between gap-2">
            <span class="text-lg font-bold uppercase leading-tight">{{ ticket.name }}</span>
            <span class="text-[0.65rem]">{{ weighing.dateDisplay.value }}</span>
          </div>
          <span class="text-base font-bold tabular-nums">{{ ticket.output_quantity_display }}</span>
          <span v-if="ticket.sources_display" class="text-xs">Objetivo: {{ ticket.sources_display }}</span>
          <span class="font-mono text-[0.65rem]">{{ ticket.blind_code }}</span>
        </div>
      </div>
    </section>
  </main>
</template>
