<script setup lang="ts">
// Payment numpad (spec §2.4, Odoo-fidelity): edits the SELECTED tender's amount
// in cents. Mirrors the quantity numpad's 3-column layout (one muscle-memory
// across screens) plus a contract-driven quick row: "Exato" fills the remaining
// due in cash, and the +R$ deltas top up the selected tender. The presets are
// policy from the Projection (`cash_tender_delta_presets_q`), never hardcoded.
import { formatBRL } from "~/utils/posIntent";

const props = defineProps<{
  /** Cash delta presets in cents from the contract; 0 = the "Exato" affordance. */
  presets: number[];
  disabled?: boolean;
}>();

defineEmits<{
  digit: [string];
  backspace: [];
  clear: [];
  add: [number];
  exact: [];
}>();

const hasExact = computed(() => props.presets.includes(0));
const deltas = computed(() => props.presets.filter((preset) => preset > 0));

const digits = ["1", "2", "3", "4", "5", "6", "7", "8", "9"];
const cell = "grid place-items-center rounded-lg border bg-card py-3 text-lg font-semibold tabular-nums transition hover:bg-accent active:translate-y-px disabled:cursor-not-allowed disabled:opacity-40";
const cellMuted = "grid place-items-center rounded-lg border bg-muted/60 py-3 text-sm font-semibold tabular-nums transition hover:bg-accent active:translate-y-px disabled:cursor-not-allowed disabled:opacity-40";
</script>

<template>
  <div class="flex min-h-0 flex-col gap-2">
    <!-- Quick row: Exato + cash deltas (contract-driven) -->
    <div v-if="hasExact || deltas.length" class="grid grid-flow-col auto-cols-fr gap-2">
      <button
        v-if="hasExact"
        type="button"
        :class="cellMuted"
        :disabled="disabled"
        @click="$emit('exact')"
      >
        Exato
      </button>
      <button
        v-for="delta in deltas"
        :key="delta"
        type="button"
        :class="cellMuted"
        :disabled="disabled"
        :aria-label="`Somar ${formatBRL(delta)}`"
        @click="$emit('add', delta)"
      >
        +{{ delta / 100 }}
      </button>
    </div>

    <!-- Digit pad (3 columns, mirrors the quantity numpad) -->
    <div class="grid min-h-0 flex-1 grid-cols-3 gap-2" role="group" aria-label="Teclado numérico de valor">
      <button
        v-for="digit in digits"
        :key="digit"
        type="button"
        :class="cell"
        :disabled="disabled"
        :aria-label="`Dígito ${digit}`"
        @click="$emit('digit', digit)"
      >
        {{ digit }}
      </button>
      <button type="button" :class="cell" :disabled="disabled" aria-label="Limpar valor" @click="$emit('clear')">C</button>
      <button type="button" :class="cell" :disabled="disabled" aria-label="Dígito 0" @click="$emit('digit', '0')">0</button>
      <button type="button" :class="cell" :disabled="disabled" aria-label="Apagar último dígito" @click="$emit('backspace')">
        <Icon name="lucide:delete" class="size-5" />
      </button>
    </div>
  </div>
</template>
