<script setup lang="ts">
import type { ProductCommandMeta } from '~/types/shopman'

const props = defineProps<{
  meta: ProductCommandMeta
  canAdd: boolean
  maxQty?: number | null
  addLabel?: string
  unavailableLabel?: string
  size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl'
}>()

const { qtyForSku, isPending, setSkuQty } = useCartState()

const qty = computed(() => qtyForSku(props.meta.sku))
const max = computed(() => props.maxQty ?? 99)
const pending = computed(() => isPending(props.meta.sku))
const canIncrement = computed(() => props.canAdd && qty.value < max.value && !pending.value)
const canDecrement = computed(() => qty.value > 0 && !pending.value)
const controlSize = computed(() => props.size || 'sm')
const addLabel = computed(() => props.canAdd ? (props.addLabel || 'Adicionar') : (props.unavailableLabel || 'Indisponível'))

const value = computed({
  get: () => qty.value,
  set: (next: number | null | undefined) => {
    void setQuantity(next).catch(() => {})
  }
})

function normalizeQty (next: number | null | undefined): number {
  if (typeof next !== 'number' || Number.isNaN(next)) return 0
  return Math.max(0, Math.min(max.value, Math.trunc(next)))
}

async function setQuantity (next: number | null | undefined) {
  const nextQty = normalizeQty(next)
  if (nextQty === qty.value) return
  if (nextQty > qty.value && !props.canAdd) return
  await setSkuQty(props.meta, nextQty)
}
</script>

<template>
  <div class="shop-stepper" :class="{ 'shop-stepper--add': qty === 0 }">
    <UButton
      v-if="qty === 0"
      block
      color="primary"
      variant="solid"
      icon="i-lucide-plus"
      :size="controlSize"
      :label="addLabel"
      :loading="pending"
      :disabled="!canAdd || pending"
      class="shop-add-button"
      @click="setQuantity(1)"
    />

    <UInputNumber
      v-else
      v-model="value"
      class="w-full"
      aria-label="Quantidade no carrinho"
      :aria-busy="pending"
      color="neutral"
      variant="subtle"
      :size="controlSize"
      :min="0"
      :max="max"
      :step="1"
      disable-wheel-change
      :disabled="pending"
      :increment="{
        color: 'neutral',
        variant: 'solid',
        size: 'xs',
        'aria-label': 'Adicionar unidade'
      }"
      :decrement="{
        color: 'neutral',
        variant: 'solid',
        size: 'xs',
        'aria-label': 'Remover unidade'
      }"
      :increment-disabled="!canIncrement"
      :decrement-disabled="!canDecrement"
      :ui="{
        root: 'w-full',
        base: 'font-semibold tabular-nums',
        increment: 'pe-1',
        decrement: 'ps-1'
      }"
    />
  </div>
</template>
