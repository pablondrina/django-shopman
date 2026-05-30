<script setup lang="ts">
defineProps<{
  disabled?: boolean;
}>();

const emit = defineEmits<{
  digit: [string];
  backspace: [];
  clear: [];
}>();

const keys = ["1", "2", "3", "4", "5", "6", "7", "8", "9"];
</script>

<template>
  <div class="grid grid-cols-3 gap-1.5" role="group" aria-label="Teclado numérico de quantidade">
    <button
      v-for="key in keys"
      :key="key"
      type="button"
      class="rounded-lg border bg-card py-2.5 text-lg font-semibold tabular-nums transition hover:bg-accent active:translate-y-px disabled:cursor-not-allowed disabled:opacity-40"
      :disabled="disabled"
      :aria-label="`Dígito ${key}`"
      @click="emit('digit', key)"
    >
      {{ key }}
    </button>
    <button
      type="button"
      class="rounded-lg border bg-card py-2.5 text-sm font-medium transition hover:bg-accent active:translate-y-px disabled:cursor-not-allowed disabled:opacity-40"
      :disabled="disabled"
      aria-label="Limpar quantidade"
      @click="emit('clear')"
    >
      C
    </button>
    <button
      type="button"
      class="rounded-lg border bg-card py-2.5 text-lg font-semibold tabular-nums transition hover:bg-accent active:translate-y-px disabled:cursor-not-allowed disabled:opacity-40"
      :disabled="disabled"
      aria-label="Dígito 0"
      @click="emit('digit', '0')"
    >
      0
    </button>
    <button
      type="button"
      class="grid place-items-center rounded-lg border bg-card py-2.5 transition hover:bg-accent active:translate-y-px disabled:cursor-not-allowed disabled:opacity-40"
      :disabled="disabled"
      aria-label="Apagar último dígito"
      @click="emit('backspace')"
    >
      <Icon name="lucide:delete" class="size-5" />
    </button>
  </div>
</template>
