<script setup lang="ts">
import type { POSProductProjection } from "~/types/pos";

defineProps<{
  product: POSProductProjection;
  qty: number;
}>();

defineEmits<{
  add: [POSProductProjection];
}>();
</script>

<template>
  <UiCard
    as="button"
    type="button"
    class="relative min-h-32 gap-3 rounded-lg p-3 text-left shadow-none transition hover:border-primary/40 hover:bg-accent/60 active:translate-y-px"
    :class="qty > 0 ? 'border-primary/50 bg-primary/5' : ''"
    @click="$emit('add', product)"
  >
    <div class="flex items-start justify-between gap-3">
      <div class="min-w-0">
        <p class="truncate text-xs font-medium text-muted-foreground">{{ product.sku }}</p>
        <p class="mt-1 line-clamp-2 text-sm font-semibold leading-snug">{{ product.name }}</p>
      </div>
      <UiBadge v-if="qty > 0" class="shrink-0 tabular-nums">{{ qty }}x</UiBadge>
    </div>
    <div class="mt-auto flex items-center justify-between gap-2">
      <strong class="tabular-nums">{{ product.price_display }}</strong>
      <UiBadge v-if="product.is_d1" variant="outline" class="border-amber-500/40 text-amber-700">
        D-1
      </UiBadge>
    </div>
  </UiCard>
</template>
