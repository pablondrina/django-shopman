<script setup lang="ts">
// KDS surface shell — Arc 1 (scaffold). The station board (read + SSE), write-side
// gestures, picker and customer board land in Arcs 2-4. This placeholder confirms
// the foundation copied from the POS (UI-Thing primitives, neutral tokens + scale,
// django proxy) boots and renders.
useHead({ title: "Shopman KDS" });
</script>

<template>
  <div class="grid min-h-screen place-items-center bg-background p-6 text-foreground">
    <div class="flex flex-col items-center gap-4 text-center">
      <span class="grid size-14 place-items-center rounded-md bg-primary text-primary-foreground">
        <Icon name="lucide:cooking-pot" class="size-7" />
      </span>
      <div>
        <p class="text-xs font-medium uppercase tracking-wide text-muted-foreground">Kitchen Display</p>
        <h1 class="text-2xl font-semibold">Shopman KDS</h1>
      </div>
      <p class="max-w-sm text-sm text-muted-foreground">
        Scaffold (Arc 1) — fundação portada do PDV. Estação, board e tempo real (SSE)
        chegam no Arc 2.
      </p>
    </div>
  </div>
</template>
