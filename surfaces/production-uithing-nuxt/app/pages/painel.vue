<script setup lang="ts">
// FORNADAS — o painel Solari em modo KIOSK (refino Pablo):
// · página à parte, sem o chrome do backstage (o link de entrada vive na
//   aba "Painel" da UI normal); botão de tela cheia para a TV;
// · tipografia Oswald (grotesca condensada de painel), DUAS escalas apenas:
//   display (título · relógio) e linha (todas as palhetas);
// · NOME do produto nas palhetas (SKU saiu); quantidade com UN embutido
//   ("12 UN" — doze o quê? unidades); horário como estava;
// · atrasado não pisca: as palhetas RE-GIRAM periodicamente até o mesmo
//   valor, como os painéis mecânicos reais fazem;
// · ordem de aeroporto: cronológica pelo horário — status muda cor, nunca
//   posição; confirmados saem pelo TTL.
import type { ForecastStatus } from "~/types/production";
import { fullDateLabel, weekdayLabel } from "~/presentation/production";

const { rows, selectedDate, pending, error } = useProductionForecast();
const sound = useFlapClack();

// ── Data: seletor discreto (a TV vive em Hoje; o vendedor consulta Amanhã) ──
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

// ── Relógio vivo ────────────────────────────────────────────────────────────
const clock = ref("--:--");
let clockTimer: ReturnType<typeof setInterval> | null = null;

// ── O tique do atraso: re-gira as palhetas do status a cada 25s ────────────
const respinTick = ref(0);
let respinTimer: ReturnType<typeof setInterval> | null = null;

onMounted(() => {
  sound.unlock();
  const tick = () => {
    const now = new Date();
    const pad = (n: number) => String(n).padStart(2, "0");
    clock.value = `${pad(now.getHours())}:${pad(now.getMinutes())}`;
  };
  tick();
  clockTimer = setInterval(tick, 1000);
  respinTimer = setInterval(() => {
    respinTick.value++;
  }, 25_000);
});
onUnmounted(() => {
  if (clockTimer) clearInterval(clockTimer);
  if (respinTimer) clearInterval(respinTimer);
});

// ── Tela cheia (kiosk de verdade na TV) ─────────────────────────────────────
const isFullscreen = ref(false);
function toggleFullscreen() {
  sound.unlock();
  if (document.fullscreenElement) {
    void document.exitFullscreen();
  } else {
    void document.documentElement.requestFullscreen?.();
  }
}
onMounted(() => {
  document.addEventListener("fullscreenchange", onFullscreenChange);
});
onUnmounted(() => {
  document.removeEventListener("fullscreenchange", onFullscreenChange);
});
function onFullscreenChange() {
  isFullscreen.value = !!document.fullscreenElement;
}

// ── Status → cor (uma cor, um significado) ─────────────────────────────────
const STATUS_TONE: Record<ForecastStatus, string> = {
  scheduled: "tone-neutral",
  in_progress: "tone-cyan",
  delayed: "tone-amber",
  arrived: "tone-green",
};

const NAME_CHARS = 22; // maior nome atual: "Pão de Forma Artesanal"
const QTY_CHARS = 6; // "999 UN"
const STATUS_CHARS = 10; // CONFIRMADO
</script>

<template>
  <main class="board flex min-h-screen flex-col">
    <header class="flex flex-wrap items-end gap-x-6 gap-y-3 px-4 pb-2 pt-5 md:px-8">
      <div class="min-w-0">
        <h1 class="board-title">Fornadas</h1>
        <div class="board-labels mt-1 flex items-center gap-3">
          <span>{{ fullDateLabel(selectedDate) }}</span>
          <span aria-hidden="true">·</span>
          <div class="flex items-center gap-2.5" role="group" aria-label="Data">
            <button type="button" class="board-datekey" :class="{ 'board-datekey--active': selectedDate === todayISO }" :aria-pressed="selectedDate === todayISO" @click="sound.unlock(); selectedDate = todayISO">Hoje</button>
            <button type="button" class="board-datekey" :class="{ 'board-datekey--active': selectedDate === tomorrowISO }" :aria-pressed="selectedDate === tomorrowISO" @click="sound.unlock(); selectedDate = tomorrowISO">Amanhã</button>
            <button type="button" class="board-datekey relative" :class="{ 'board-datekey--active': isCustomDate }" :aria-pressed="isCustomDate" @click="openCustomDate()">
              {{ isCustomDate ? weekdayLabel(selectedDate) : "Outra" }}
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
        </div>
      </div>

      <div class="ml-auto flex items-center gap-2.5">
        <button
          type="button"
          class="board-key"
          :aria-label="sound.enabled.value ? 'Silenciar palhetas' : 'Ativar som das palhetas'"
          @click="sound.toggle()"
        >
          <Icon :name="sound.enabled.value ? 'lucide:volume-2' : 'lucide:volume-x'" class="size-4" />
        </button>
        <button
          type="button"
          class="board-key"
          :aria-label="isFullscreen ? 'Sair da tela cheia' : 'Tela cheia'"
          @click="toggleFullscreen()"
        >
          <Icon :name="isFullscreen ? 'lucide:minimize' : 'lucide:maximize'" class="size-4" />
        </button>
        <ClientOnly>
          <SplitFlap :value="clock" :chars="5" class="board-display ml-2" />
        </ClientOnly>
      </div>
    </header>

    <section class="min-h-0 flex-1 overflow-auto px-4 pb-8 pt-4 md:px-8">
      <p v-if="pending && !rows.length" class="board-labels py-8">Carregando…</p>
      <p v-else-if="error" class="board-labels py-8">Sinal perdido — reconectando…</p>

      <div v-else-if="!rows.length" class="board-labels grid place-items-center gap-2 py-24 text-center">
        <Icon name="lucide:tower-control" class="size-9" />
        <p>Nenhuma fornada programada para esta data.</p>
      </div>

      <TransitionGroup v-else tag="div" name="board-row" class="relative flex flex-col gap-1.5">
        <article
          v-for="row in rows"
          :key="row.ref"
          class="board-row"
          :aria-label="`${row.recipe_name}: ${row.qty} unidades às ${row.eta_display}, ${row.status_label}`"
        >
          <SplitFlap :value="row.recipe_name" :chars="NAME_CHARS" class="board-flap min-w-0" />
          <SplitFlap :value="`${row.qty} UN`" :chars="QTY_CHARS" align="right" class="board-flap" />
          <SplitFlap :value="row.eta_display" :chars="5" align="right" class="board-flap" :class="row.status === 'delayed' ? 'tone-amber' : row.eta_is_actual ? 'tone-green' : ''" />
          <SplitFlap
            :value="row.status_label"
            :chars="STATUS_CHARS"
            align="right"
            class="board-flap"
            :class="STATUS_TONE[row.status]"
            :pulse="row.status === 'delayed' ? respinTick : 0"
          />
        </article>
      </TransitionGroup>
    </section>
  </main>
</template>

<style scoped>
/* ── A pele do Solari: noturna por natureza, alheia ao tema do app ── */
.board {
  --board-bg: #0b0d10;
  --board-panel: #121417;
  --board-line: #23262b;
  --board-text: #ece9df;
  --board-dim: #82868d;
  --board-green: #45d98a;
  --board-amber: #ffb02e;
  --board-cyan: #5cc9f5;

  /* DUAS escalas, e só: display (título · relógio) e linha (palhetas). */
  --scale-display: clamp(1.9rem, 4vw, 2.6rem);
  --scale-row: clamp(1.05rem, 2vw, 1.5rem);

  background:
    radial-gradient(120% 90% at 50% 0%, #14171b 0%, var(--board-bg) 55%),
    var(--board-bg);
  color: var(--board-text);
  font-family: Oswald, "Arial Narrow", "Helvetica Neue", sans-serif;
  letter-spacing: 0.02em;
}

.board-title {
  font-size: var(--scale-display);
  font-weight: 600;
  line-height: 1;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}
.board-display {
  font-size: var(--scale-display);
  font-weight: 600;
}
.board-flap {
  font-size: var(--scale-row);
  font-weight: 500;
}

.board-labels {
  font-size: 0.78rem;
  font-weight: 500;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--board-dim);
}

.board-datekey {
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--board-dim);
  border-bottom: 1px solid transparent;
  padding-bottom: 1px;
  transition: color 150ms, border-color 150ms;
}
.board-datekey:hover {
  color: var(--board-text);
}
.board-datekey--active {
  color: var(--board-text);
  border-color: var(--board-text);
}

.board-key {
  display: grid;
  place-items: center;
  width: 2.25rem;
  height: 2.25rem;
  border-radius: 0.375rem;
  border: 1px solid var(--board-line);
  background: var(--board-panel);
  color: var(--board-dim);
  transition: color 150ms, border-color 150ms;
}
.board-key:hover {
  color: var(--board-text);
  border-color: #3a3e45;
}

/* ── Grade: TV = uma linha; celular = nome em cima, mostradores embaixo ── */
.board-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto auto;
  gap: 1.25rem;
  align-items: center;
  border: 1px solid var(--board-line);
  border-radius: 0.5rem;
  background: linear-gradient(180deg, #14171b 0%, var(--board-panel) 100%);
  padding: 0.7rem 1rem;
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

/* Entrada/saída de fornadas (lote novo; confirmado expirou o TTL). */
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

@media (max-width: 700px) {
  .board-row {
    grid-template-columns: auto auto auto;
    grid-template-areas:
      "nome nome nome"
      "qtd horario status";
    justify-content: space-between;
    row-gap: 0.6rem;
  }
  .board-row > :nth-child(1) {
    grid-area: nome;
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
  .board {
    --scale-row: 0.92rem;
  }
}
</style>
