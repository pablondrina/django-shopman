<script setup lang="ts">
// Shared search box for the Gestor toolbars — icon affordance + clear button +
// expand-on-focus. Both boards use it (Pedidos: pedidos; Catálogo: produto/SKU), so
// width and behaviour are identical. Exposes focus() for the "/" keyboard shortcut.
withDefaults(
  defineProps<{
    modelValue: string;
    placeholder?: string;
    ariaLabel?: string;
  }>(),
  {
    placeholder: "Buscar…",
    ariaLabel: "Buscar",
  },
);
const emit = defineEmits<{ "update:modelValue": [value: string] }>();
const input = ref<HTMLInputElement | null>(null);
defineExpose({ focus: () => input.value?.focus() });
</script>

<template>
  <div class="relative">
    <Icon name="lucide:search" class="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
    <input
      ref="input"
      :value="modelValue"
      type="search"
      inputmode="search"
      :placeholder="placeholder"
      :aria-label="ariaLabel"
      class="h-9 w-44 rounded-md border bg-card pl-8 pr-8 text-sm outline-none transition-[width,box-shadow] focus:w-56 focus:ring-1 focus:ring-ring sm:w-52 sm:focus:w-64"
      @input="emit('update:modelValue', ($event.target as HTMLInputElement).value)"
    />
    <button
      v-if="modelValue"
      type="button"
      class="absolute right-1 top-1/2 grid size-6 -translate-y-1/2 place-items-center rounded text-muted-foreground transition hover:text-foreground"
      aria-label="Limpar busca"
      @click="emit('update:modelValue', '')"
    >
      <Icon name="lucide:x" class="size-3.5" />
    </button>
  </div>
</template>
