<script setup lang="ts">
// O PAINEL — previsão da produção estilo aeroporto, para a equipe da loja
// (vendas/encomendas) saber o que pode ser prometido para a data. Uma linha
// por fornada (= voo): PREVISTO honesto em três níveis (~estimativa → firme
// no start → real no finish), CHEGADA pela mediana histórica, LIVRE =
// prevista − comprometida. Desenhado para ficar aberto numa tela da loja:
// chrome mínimo, tipografia à distância, relógio vivo, poll de 30s.
import type { ForecastRowProjection, ForecastStatus } from "~/types/production";
import { fullDateLabel, weekdayLabel } from "~/presentation/production";

const { forecast, rows, selectedDate, pending, error } = useProductionForecast();

// ── Data: Hoje · Amanhã · dia escolhido (mesmo padrão das grades) ───────────
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

// ── Relógio vivo (alma de aeroporto) ────────────────────────────────────────
const clock = ref("");
let clockTimer: ReturnType<typeof setInterval> | null = null;
onMounted(() => {
  const tick = () => {
    const now = new Date();
    const pad = (n: number) => String(n).padStart(2, "0");
    clock.value = `${pad(now.getHours())}:${pad(now.getMinutes())}`;
  };
  tick();
  clockTimer = setInterval(tick, 1000);
});
onUnmounted(() => {
  if (clockTimer) clearInterval(clockTimer);
});

// ── Status: vocabulário e tom (uma cor = um significado) ───────────────────
const STATUS_CHIP: Record<ForecastStatus, string> = {
  scheduled: "border-border bg-muted text-muted-foreground",
  in_progress: "border-primary/40 bg-primary/10 text-primary",
  delayed: "animate-pulse border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300",
  arrived: "border-green-600/40 bg-green-600/10 text-green-700 dark:text-green-400",
};

function forecastDisplay(row: ForecastRowProjection): string {
  return row.qty_firm ? row.forecast_qty : `~${row.forecast_qty}`;
}
</script>

<template>
  <main class="flex min-h-screen flex-col">
    <header class="flex shrink-0 flex-wrap items-center gap-x-6 gap-y-2 border-b bg-card px-5 py-3">
      <NuxtLink to="/" class="grid size-10 shrink-0 place-items-center rounded-md border bg-card text-foreground transition hover:bg-accent" aria-label="Voltar para a Produção">
        <Icon name="lucide:croissant" class="size-5" />
      </NuxtLink>
      <div class="min-w-0">
        <p class="text-xs font-medium uppercase tracking-wider text-muted-foreground">Fournil · Painel da produção</p>
        <h1 class="truncate text-xl font-bold leading-tight">{{ fullDateLabel(selectedDate) }}</h1>
      </div>

      <div class="flex items-center gap-1 rounded-lg border bg-background p-0.5" role="group" aria-label="Data">
        <button
          type="button"
          class="rounded-md px-3 py-1.5 text-sm font-medium transition"
          :class="selectedDate === todayISO ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-accent hover:text-foreground'"
          :aria-pressed="selectedDate === todayISO"
          @click="selectedDate = todayISO"
        >
          Hoje
        </button>
        <button
          type="button"
          class="rounded-md px-3 py-1.5 text-sm font-medium transition"
          :class="selectedDate === tomorrowISO ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-accent hover:text-foreground'"
          :aria-pressed="selectedDate === tomorrowISO"
          @click="selectedDate = tomorrowISO"
        >
          Amanhã
        </button>
        <button
          type="button"
          class="relative rounded-md px-3 py-1.5 text-sm font-medium transition"
          :class="isCustomDate ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-accent hover:text-foreground'"
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

      <div class="ml-auto flex items-baseline gap-3">
        <span v-if="forecast" class="hidden text-xs text-muted-foreground sm:inline">atualizado {{ forecast.generated_at_display }}</span>
        <ClientOnly>
          <span class="text-4xl font-bold tabular-nums leading-none">{{ clock }}</span>
        </ClientOnly>
      </div>
    </header>

    <section class="min-h-0 flex-1 overflow-auto p-4 md:p-6">
      <p v-if="pending && !rows.length" class="text-sm text-muted-foreground">Carregando…</p>
      <p v-else-if="error" class="rounded-md border border-red-500/30 bg-red-500/5 p-4 text-sm text-red-700 dark:text-red-400">
        Falha ao carregar. Reconectando…
      </p>

      <div v-else-if="!rows.length" class="grid place-items-center gap-2 rounded-lg border border-dashed py-20 text-center text-muted-foreground">
        <Icon name="lucide:tower-control" class="size-8" />
        <p class="text-base font-medium">Nenhuma fornada programada para esta data.</p>
      </div>

      <div v-else class="overflow-hidden rounded-lg border">
        <table class="w-full">
          <thead class="bg-muted/50 text-left text-xs uppercase tracking-widest text-muted-foreground">
            <tr>
              <th class="px-4 py-3 font-semibold">Produto</th>
              <th class="px-4 py-3 text-right font-semibold">Planejado</th>
              <th class="px-4 py-3 text-right font-semibold">Previsto</th>
              <th class="px-4 py-3 text-right font-semibold">Chegada</th>
              <th class="px-4 py-3 text-right font-semibold">Livre</th>
              <th class="px-4 py-3 text-right font-semibold">Status</th>
            </tr>
          </thead>
          <tbody class="divide-y">
            <tr
              v-for="(row, index) in rows"
              :key="`${row.output_sku}-${index}`"
              class="transition"
              :class="row.status === 'arrived' ? 'opacity-60' : ''"
            >
              <td class="px-4 py-3">
                <p class="text-lg font-bold leading-tight">{{ row.output_sku }}</p>
                <p class="truncate text-sm text-muted-foreground">{{ row.recipe_name }}</p>
              </td>
              <td class="px-4 py-3 text-right text-lg tabular-nums text-muted-foreground">{{ row.planned_qty }}</td>
              <td class="px-4 py-3 text-right">
                <span class="text-lg font-semibold tabular-nums" :title="row.qty_firm ? 'Quantidade firme' : 'Estimativa'">
                  {{ forecastDisplay(row) }}
                </span>
              </td>
              <td class="px-4 py-3 text-right">
                <span class="inline-flex items-center gap-1.5 text-xl font-bold tabular-nums" :class="row.status === 'delayed' ? 'text-amber-700 dark:text-amber-300' : ''">
                  {{ row.eta_display }}
                  <Icon v-if="row.eta_is_actual" name="lucide:check" class="size-4 text-green-700 dark:text-green-400" />
                </span>
              </td>
              <td class="px-4 py-3 text-right">
                <span class="text-lg font-bold tabular-nums" :class="row.promisable_qty === '0' ? 'text-muted-foreground' : ''">
                  {{ row.promisable_qty }}
                </span>
                <span v-if="row.committed_qty !== '0'" class="block text-xs text-muted-foreground">{{ row.committed_qty }} c/ dono</span>
              </td>
              <td class="px-4 py-3 text-right">
                <span class="inline-flex items-center rounded-md border px-2.5 py-1 text-sm font-semibold uppercase tracking-wide" :class="STATUS_CHIP[row.status]">
                  {{ row.status_label }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <p v-if="rows.length" class="mt-3 text-xs text-muted-foreground">
        Chegadas previstas pela mediana dos últimos 28 dias de produção · quantidades com ~ são estimativas até o lote entrar em processo · LIVRE = previsto − encomendas com dono.
      </p>
    </section>
  </main>
</template>
