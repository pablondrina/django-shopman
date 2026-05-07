<script setup lang="ts">
import type { ProductCommandMeta } from '~/types/shopman'

const props = defineProps<{
  meta: ProductCommandMeta
  canAdd: boolean
  maxQty?: number | null
}>()

const { qtyForSku, isPending, setSkuQty } = useCartState()

const qty = computed(() => qtyForSku(props.meta.sku))
const max = computed(() => props.maxQty ?? 99)
const pending = computed(() => isPending(props.meta.sku))
const canIncrement = computed(() => props.canAdd && qty.value < max.value && !pending.value)
const canDecrement = computed(() => qty.value > 0 && !pending.value)

async function changeBy (delta: number) {
  const nextQty = Math.max(0, Math.min(max.value, qty.value + delta))
  if (nextQty === qty.value) return
  await setSkuQty(props.meta, nextQty)
}
</script>

<template>
  <div class="shop-stepper" :aria-busy="pending">
    <UButton
      aria-label="Remover unidade"
      variant="ghost"
      color="neutral"
      icon="i-lucide-minus"
      square
      :disabled="!canDecrement"
      @click="changeBy(-1)"
    />
    <UBadge color="neutral" variant="soft" class="shop-stepper-count">
      {{ pending ? '...' : qty }}
    </UBadge>
    <UButton
      aria-label="Adicionar unidade"
      variant="ghost"
      color="neutral"
      icon="i-lucide-plus"
      square
      :disabled="!canIncrement"
      @click="changeBy(1)"
    />
  </div>
</template>
