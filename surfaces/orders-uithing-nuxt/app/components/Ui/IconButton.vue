<script setup lang="ts">
// Shared square icon action (size-9) for the Gestor toolbars — refresh, export,
// print, theme, view toggles. One neutral resting style; `active` tints it like a
// pressed segment, `spinning` animates the glyph (refresh-in-flight). Renders a
// native <button> as root so parent `@click`/`:disabled` fall through.
defineProps<{
  icon: string;
  label: string;
  active?: boolean;
  spinning?: boolean;
}>();
</script>

<template>
  <button
    type="button"
    :aria-label="label"
    :title="label"
    class="grid size-9 shrink-0 place-items-center rounded-md border text-muted-foreground transition hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40 disabled:pointer-events-none disabled:opacity-50"
    :class="active ? 'bg-accent text-foreground' : ''"
  >
    <Icon :name="icon" class="size-4" :class="spinning ? 'animate-spin' : ''" />
  </button>
</template>
