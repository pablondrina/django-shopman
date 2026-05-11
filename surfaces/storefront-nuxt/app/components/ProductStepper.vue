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
const controlSize = computed(() => props.size || 'xs')
const label = computed(() => props.canAdd ? (props.addLabel || 'Adicionar') : (props.unavailableLabel || 'Indisponível'))

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
  <div class="flex-shrink-0" @click.prevent.stop>
    <UButton
      v-if="qty === 0"
      color="neutral"
      variant="outline"
      icon="i-lucide-plus"
      :size="controlSize"
      :label="label"
      :loading="pending"
      :disabled="!canAdd || pending"
      @click="setQuantity(1)"
    />

    <UInputNumber
      v-else
      v-model="value"
      aria-label="Quantidade no carrinho"
      color="neutral"
      variant="outline"
      :size="controlSize"
      :min="0"
      :max="max"
      :step="1"
      disable-wheel-change
      :disabled="pending"
    />
  </div>
</template>
