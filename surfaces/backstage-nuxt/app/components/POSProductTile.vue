<script setup lang="ts">
import type { POSProductProjection } from '~/types/backstage'

const props = defineProps<{ product: POSProductProjection }>()
defineEmits<{ add: [POSProductProjection] }>()

const cart = usePosCart()
const inCart = computed(() => cart.state.value.items.find(i => i.sku === props.product.sku)?.qty || 0)
</script>

<template>
  <UCard
    as="button"
    type="button"
    :ui="{ body: 'p-3' }"
    class="text-left hover:bg-elevated active:scale-[0.98] transition-all relative"
    :class="inCart > 0 && 'ring-2 ring-primary'"
    @click="$emit('add', product)"
  >
    <UBadge
      v-if="inCart > 0"
      color="primary"
      variant="solid"
      size="md"
      class="absolute top-1 right-1 tabular-nums z-10"
    >
      {{ inCart }}×
    </UBadge>

    <p class="text-sm text-muted truncate">{{ product.sku }}</p>
    <p class="font-semibold text-highlighted leading-tight mt-1 line-clamp-2">{{ product.name }}</p>
    <p class="mt-2 text-base font-bold text-primary tabular-nums">{{ product.price_display }}</p>
    <UBadge v-if="product.is_d1" color="warning" variant="subtle" size="xs" class="mt-1">D-1</UBadge>
  </UCard>
</template>
