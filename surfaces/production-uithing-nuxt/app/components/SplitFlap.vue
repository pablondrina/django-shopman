<script setup lang="ts">
// Texto em palhetas estilo Solari: cada caractere vive numa célula que GIRA
// ao trocar (squash rotateX com a troca no meio do giro + "clac"). A carga
// inicial cascateia da esquerda passando por um caractere intermediário —
// o charme do painel de aeroporto. `chars` fixa a largura em células para
// alinhar colunas; SSR renderiza células em branco e o giro é client-only
// (sem mismatch de hidratação).
const props = withDefaults(
  defineProps<{
    value: string;
    chars?: number;
    align?: "left" | "right";
  }>(),
  { chars: 0, align: "left" },
);

const FLAP_CHARSET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
const FLIP_MS = 55;

interface Cell {
  shown: string;
  flipping: boolean;
}

const { clack } = useFlapClack();
const cells = ref<Cell[]>([]);
const timers = new Set<ReturnType<typeof setTimeout>>();
let mounted = false;

function later(fn: () => void, ms: number) {
  const id = setTimeout(() => {
    timers.delete(id);
    fn();
  }, ms);
  timers.add(id);
}

function targetChars(): string[] {
  const raw = (props.value ?? "").toUpperCase();
  const width = props.chars || raw.length || 1;
  const clipped = raw.slice(0, width);
  const pad = " ".repeat(Math.max(0, width - clipped.length));
  return [...(props.align === "right" ? pad + clipped : clipped + pad)];
}

/** Gira a célula até o alvo, passando por `hops` caracteres aleatórios. */
function spin(index: number, to: string, hops: number, delay: number) {
  later(() => {
    const step = (remaining: number) => {
      const cell = cells.value[index];
      if (!cell) return;
      const next = remaining > 0 ? FLAP_CHARSET[Math.floor(Math.random() * FLAP_CHARSET.length)]! : to;
      cell.flipping = true;
      later(() => {
        cell.shown = next;
        clack();
        later(() => {
          cell.flipping = false;
          if (remaining > 0) step(remaining - 1);
        }, FLIP_MS);
      }, FLIP_MS);
    };
    step(hops);
  }, delay);
}

function applyValue(hops: number) {
  const target = targetChars();
  if (cells.value.length !== target.length) {
    cells.value = target.map((_, i) => cells.value[i] ?? { shown: " ", flipping: false });
    while (cells.value.length > target.length) cells.value.pop();
    while (cells.value.length < target.length) cells.value.push({ shown: " ", flipping: false });
  }
  target.forEach((char, index) => {
    const cell = cells.value[index]!;
    if (cell.shown === char) return;
    spin(index, char, char === " " ? 0 : hops, index * 28);
  });
}

onMounted(() => {
  mounted = true;
  applyValue(1); // cascata de estreia
});

onUnmounted(() => {
  for (const id of timers) clearTimeout(id);
  timers.clear();
});

watch(
  () => [props.value, props.chars],
  () => {
    if (mounted) applyValue(1);
  },
);

// SSR: células em branco na largura certa (o giro acontece no cliente).
if (!import.meta.client) {
  cells.value = targetChars().map(() => ({ shown: " ", flipping: false }));
}
</script>

<template>
  <span class="flap-word" aria-live="polite" :aria-label="value">
    <span
      v-for="(cell, index) in cells"
      :key="index"
      class="flap-cell"
      :class="{ 'flap-cell--blank': cell.shown === ' ', 'flap-cell--flipping': cell.flipping }"
      aria-hidden="true"
    >{{ cell.shown }}</span>
  </span>
</template>

<style scoped>
.flap-word {
  display: inline-flex;
  gap: 0.09em;
}
.flap-cell {
  position: relative;
  display: inline-grid;
  place-items: center;
  width: 0.78em;
  height: 1.18em;
  border-radius: 0.09em;
  background: linear-gradient(180deg, #23262b 0%, #191c20 48%, #101216 52%, #1b1e23 100%);
  box-shadow: inset 0 1px 0 rgb(255 255 255 / 6%), 0 1px 2px rgb(0 0 0 / 60%);
  font-variant-numeric: tabular-nums;
  line-height: 1;
  transition: transform 55ms ease-in;
  transform-style: preserve-3d;
}
/* A fenda horizontal — a alma da palheta. */
.flap-cell::after {
  content: "";
  position: absolute;
  inset: calc(50% - 0.5px) 0 auto;
  height: 1px;
  background: rgb(0 0 0 / 55%);
}
.flap-cell--flipping {
  transform: perspective(6em) rotateX(58deg);
  filter: brightness(0.75);
}
.flap-cell--blank {
  background: linear-gradient(180deg, #1a1d21 0%, #14161a 48%, #0e1013 52%, #16181c 100%);
}
</style>
