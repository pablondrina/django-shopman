<script setup lang="ts">
const props = defineProps<{
  disabled?: boolean;
  compact?: boolean;
}>();

const emit = defineEmits<{
  digit: [string];
  backspace: [];
  clear: [];
}>();

const keys = ["1", "2", "3", "4", "5", "6", "7", "8", "9"];
const cellBase = "rounded-md border bg-card font-semibold tabular-nums transition hover:bg-accent active:translate-y-px disabled:cursor-not-allowed disabled:opacity-40";
const cell = computed(() => (props.compact ? `${cellBase} py-1.5 text-base` : `${cellBase} py-2.5 text-lg`));
const cellSm = computed(() => (props.compact ? "rounded-md border bg-card py-1.5 text-sm font-medium transition hover:bg-accent active:translate-y-px disabled:cursor-not-allowed disabled:opacity-40" : "rounded-md border bg-card py-2.5 text-sm font-medium transition hover:bg-accent active:translate-y-px disabled:cursor-not-allowed disabled:opacity-40"));
</script>

<template>
  <div :class="compact ? 'grid grid-cols-3 gap-1' : 'grid grid-cols-3 gap-1.5'" role="group" aria-label="Teclado numérico de quantidade">
    <button
      v-for="key in keys"
      :key="key"
      type="button"
      :class="cell"
      :disabled="disabled"
      :aria-label="`Dígito ${key}`"
      @click="emit('digit', key)"
    >
      {{ key }}
    </button>
    <button
      type="button"
      :class="cellSm"
      :disabled="disabled"
      aria-label="Limpar quantidade"
      @click="emit('clear')"
    >
      C
    </button>
    <button
      type="button"
      :class="cell"
      :disabled="disabled"
      aria-label="Dígito 0"
      @click="emit('digit', '0')"
    >
      0
    </button>
    <button
      type="button"
      class="grid place-items-center rounded-md border border-destructive/25 bg-destructive/5 text-destructive transition hover:bg-destructive/10 active:translate-y-px disabled:cursor-not-allowed disabled:opacity-40"
      :class="compact ? 'py-1.5' : 'py-2.5'"
      :disabled="disabled"
      aria-label="Apagar último dígito"
      @click="emit('backspace')"
    >
      <Icon name="lucide:delete" :class="compact ? 'size-4' : 'size-5'" />
    </button>
  </div>
</template>
