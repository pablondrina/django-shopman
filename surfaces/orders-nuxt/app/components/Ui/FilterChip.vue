<script setup lang="ts">
// Shared filter pill for the Gestor boards — the channel axis (Pedidos) and the
// collection axis (Catálogo) use the exact same chip. Active = solid `bg-primary`
// (the one unified choice; Catálogo's old `bg-foreground` is gone). Optional count
// suffix and an `icon` slot for the channel/collection glyph.
defineProps<{
  active?: boolean;
  count?: number | null;
}>();
</script>

<template>
  <button
    type="button"
    class="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-full border px-3 text-xs font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
    :class="active ? 'border-transparent bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-accent hover:text-foreground'"
  >
    <slot name="icon" />
    <slot />
    <span v-if="count != null" class="tabular-nums opacity-70">{{ count }}</span>
  </button>
</template>
