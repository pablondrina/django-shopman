<script setup lang="ts">
// Shared work toolbar for the Gestor boards (Pedidos + Catálogo). Full-bleed,
// compact bar that sits under the hub nav (GestorTopBar). The default slot holds
// the primary controls (search + filter chips, left-aligned); the `end` slot holds
// the view/action cluster (pushed right). Both boards compose it from the same
// chrome primitives (UiSearchInput, UiFilterChip, UiIconButton) so they read as one
// design language, not copy-paste.
</script>

<template>
  <div class="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-2 border-b bg-card/60 px-4 py-2 print:hidden">
    <slot />
    <div v-if="$slots.end" class="ml-auto flex items-center gap-1.5">
      <slot name="end" />
    </div>
  </div>
</template>
