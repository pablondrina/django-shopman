<script setup lang="ts">
// O PAINEL — agora com alma de Solari: fundo noturno, palhetas que giram
// (SplitFlap), cascata na carga, "clac" opcional, linhas que entram/saem
// animadas. Ordenação de aeroporto: estritamente cronológica pelo horário
// (status muda a COR, nunca a posição); confirmados saem pelo TTL.
// Responsivo de TV a celular: em telas largas é uma linha por fornada; no
// celular o produto ocupa a primeira linha e os mostradores a segunda.
import type { ForecastStatus } from "~/types/production";
import { fullDateLabel, weekdayLabel } from "~/presentation/production";

const { forecast, rows, selectedDate, pending, error } = useProductionForecast();
const sound = useFlapClack();

// ── Data: Hoje · Amanhã · dia escolhido ─────────────────────────────────────
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
  sound.unlock();
  customDateInput.value?.showPicker?.();
  customDateInput.value?.focus();
}

// ── Relógio vivo em palhetas ────────────────────────────────────────────────
const clock = ref("--:--");
let clockTimer: ReturnType<typeof setInterval> | null = null;
onMounted(() => {
  sound.unlock(); // se o browser deixar; senão, destrava no primeiro toque
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

// ── Status → cor (uma cor, um significado; atrasado pisca) ────────────────
const STATUS_TONE: Record<ForecastStatus, string> = {
  scheduled: "tone-neutral",
  in_progress: "tone-cyan",
  delayed: "tone-amber blink",
  arrived: "tone-green",
};

const PRODUCT_CHARS = 17; // maior SKU atual: BAGUETE-CAMPAGNE (16)
const STATUS_CHARS = 10; // CONFIRMADO
</script>

<template>
  <main class="board flex min-h-screen flex-col">
    <header class="flex flex-wrap items-center gap-x-5 gap-y-3 px-4 py-4 md:px-8">
      <NuxtLink to="/" class="board-control grid size-10 shrink-0 place-items-center rounded-md" aria-label="Voltar para a Produção">
        <Icon name="lucide:croissant" class="size-5" />
      </NuxtLink>
      <div class="min-w-0">
        <p class="board-eyebrow">Fournil · Chegadas da produção</p>
        <h1 class="board-date">{{ fullDateLabel(selectedDate) }}</h1>
      </div>

      <div class="board-chips flex items-center gap-1 rounded-lg p-0.5" role="group" aria-label="Data">
        <button
          type="button"
          class="board-chip"
          :class="{ 'board-chip--active': selectedDate === todayISO }"
          :aria-pressed="selectedDate === todayISO"
          @click="sound.unlock(); selectedDate = todayISO"
        >
          Hoje
        </button>
        <button
          type="button"
          class="board-chip"
          :class="{ 'board-chip--active': selectedDate === tomorrowISO }"
          :aria-pressed="selectedDate === tomorrowISO"
          @click="sound.unlock(); selectedDate = tomorrowISO"
        >
          Amanhã
        </button>
        <button
          type="button"
          class="board-chip relative"
          :class="{ 'board-chip--active': isCustomDate }"
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

      <div class="ml-auto flex items-center gap-3">
        <button
          type="button"
          class="board-control grid size-10 place-items-center rounded-md"
          :aria-label="sound.enabled.value ? 'Silenciar palhetas' : 'Ativar som das palhetas'"
          :title="sound.enabled.value ? 'Som ligado' : 'Som desligado'"
          @click="sound.toggle()"
        >
          <Icon :name="sound.enabled.value ? 'lucide:volume-2' : 'lucide:volume-x'" class="size-4" />
        </button>
        <ClientOnly>
          <SplitFlap :value="clock" :chars="5" class="board-clock" />
        </ClientOnly>
      </div>
    </header>

    <section class="min-h-0 flex-1 overflow-auto px-4 pb-6 md:px-8">
      <p v-if="pending && !rows.length" class="board-dim py-8 text-sm">Carregando…</p>
      <p v-else-if="error" class="board-dim py-8 text-sm">Sinal perdido — reconectando…</p>

      <div v-else-if="!rows.length" class="board-dim grid place-items-center gap-2 py-24 text-center">
        <Icon name="lucide:tower-control" class="size-9" />
        <p class="text-base">Nenhuma fornada programada para esta data.</p>
      </div>

      <template v-else>
        <div class="board-headrow" aria-hidden="true">
          <span>Produto</span>
          <span class="text-right">Qtd</span>
          <span class="text-right">Horário</span>
          <span class="text-right">Status</span>
        </div>

        <TransitionGroup tag="div" name="board-row" class="flex flex-col gap-1.5">
          <article v-for="row in rows" :key="row.ref" class="board-row" :aria-label="`${row.output_sku}: ${row.qty} às ${row.eta_display}, ${row.status_label}`">
            <div class="board-produto min-w-0">
              <SplitFlap :value="row.output_sku" :chars="PRODUCT_CHARS" class="board-flap" />
              <p class="board-dim mt-1 truncate text-xs">{{ row.recipe_name }}</p>
            </div>
            <SplitFlap :value="row.qty" :chars="3" align="right" class="board-flap board-num" />
            <SplitFlap :value="row.eta_display" :chars="5" align="right" class="board-flap board-num" :class="row.status === 'delayed' ? 'tone-amber' : row.eta_is_actual ? 'tone-green' : ''" />
            <SplitFlap :value="row.status_label" :chars="STATUS_CHARS" align="right" class="board-flap board-status" :class="STATUS_TONE[row.status]" />
          </article>
        </TransitionGroup>

        <p class="board-dim mt-4 text-xs">
          Ordem cronológica pelo horário previsto · horários pela média histórica até a confirmação (hora real depois) · confirmados saem do painel 30 min após a chegada.
        </p>
      </template>
    </section>
  </main>
</template>

<style scoped>
/* ── A pele do Solari: noturna por natureza, independente do tema do app ── */
.board {
  --board-bg: #0b0d10;
  --board-panel: #121417;
  --board-line: #23262b;
  --board-text: #e9e6dc;
  --board-dim: #8b8f96;
  --board-green: #45d98a;
  --board-amber: #ffb02e;
  --board-cyan: #5cc9f5;

  background:
    radial-gradient(120% 90% at 50% 0%, #14171b 0%, var(--board-bg) 55%),
    var(--board-bg);
  color: var(--board-text);
  font-family: ui-monospace, "SF Mono", "Cascadia Mono", Menlo, Consolas, monospace;
}

.board-eyebrow {
  font-size: 0.68rem;
  font-weight: 600;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: var(--board-dim);
}
.board-date {
  font-size: 1.15rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
.board-dim {
  color: var(--board-dim);
}

.board-control {
  border: 1px solid var(--board-line);
  background: var(--board-panel);
  color: var(--board-dim);
  transition: color 150ms, border-color 150ms;
}
.board-control:hover {
  color: var(--board-text);
  border-color: #3a3e45;
}

.board-chips {
  border: 1px solid var(--board-line);
  background: var(--board-panel);
}
.board-chip {
  border-radius: 0.375rem;
  padding: 0.4rem 0.75rem;
  font-size: 0.8rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--board-dim);
  transition: color 150ms, background 150ms;
}
.board-chip:hover {
  color: var(--board-text);
}
.board-chip--active {
  background: var(--board-text);
  color: #101216;
}

.board-clock {
  font-size: clamp(1.6rem, 4vw, 2.4rem);
  font-weight: 700;
}

/* ── Grade: TV = uma linha; celular = produto em cima, mostradores embaixo ── */
.board-headrow,
.board-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto auto;
  gap: 1.25rem;
  align-items: center;
}
.board-headrow {
  padding: 0 1rem 0.5rem;
  font-size: 0.65rem;
  font-weight: 600;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: var(--board-dim);
}
.board-row {
  border: 1px solid var(--board-line);
  border-radius: 0.5rem;
  background: linear-gradient(180deg, #14171b 0%, var(--board-panel) 100%);
  padding: 0.7rem 1rem;
}

.board-flap {
  font-size: clamp(1rem, 2.1vw, 1.5rem);
  font-weight: 700;
}
.board-status {
  font-size: clamp(0.8rem, 1.5vw, 1.05rem);
}

.tone-green :deep(.flap-cell) {
  color: var(--board-green);
}
.tone-amber :deep(.flap-cell) {
  color: var(--board-amber);
}
.tone-cyan :deep(.flap-cell) {
  color: var(--board-cyan);
}
.tone-neutral :deep(.flap-cell) {
  color: var(--board-text);
}
.blink {
  animation: board-blink 1.6s steps(2, start) infinite;
}
@keyframes board-blink {
  50% {
    opacity: 0.45;
  }
}

/* Entrada/saída de fornadas (chegou lote novo; confirmado expirou o TTL). */
.board-row-enter-active,
.board-row-leave-active {
  transition: opacity 400ms ease, transform 400ms ease;
}
.board-row-enter-from {
  opacity: 0;
  transform: translateY(-0.5rem);
}
.board-row-leave-to {
  opacity: 0;
  transform: translateY(0.5rem);
}
.board-row-leave-active {
  position: absolute;
  width: 100%;
}

@media (max-width: 640px) {
  .board-headrow {
    display: none;
  }
  .board-row {
    grid-template-columns: auto auto auto;
    grid-template-areas:
      "produto produto produto"
      "qtd horario status";
    justify-content: space-between;
    row-gap: 0.6rem;
  }
  .board-produto {
    grid-area: produto;
  }
  .board-row > :nth-child(2) {
    grid-area: qtd;
  }
  .board-row > :nth-child(3) {
    grid-area: horario;
  }
  .board-row > :nth-child(4) {
    grid-area: status;
  }
  .board-flap {
    font-size: 0.95rem;
  }
}
</style>
