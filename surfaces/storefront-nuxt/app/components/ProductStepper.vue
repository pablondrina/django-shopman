<script setup lang="ts">
import type { ProductMutationMeta } from '~/types/shopman'

const props = defineProps<{
  meta: ProductMutationMeta
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
const productName = computed(() => props.meta.name || 'item')

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
      :aria-label="`${label} ${productName}`"
      :loading="pending"
      :disabled="!canAdd || pending"
      data-haptic="light"
      @click="setQuantity(1)"
    />

    <div
      v-else
      class="inline-flex items-center overflow-hidden rounded-md border border-default bg-default shadow-xs"
      role="group"
      :aria-label="`Quantidade de ${productName} no carrinho`"
    >
      <UButton
        color="neutral"
        variant="ghost"
        icon="i-lucide-minus"
        :size="controlSize"
        class="rounded-none"
        :aria-label="`Diminuir quantidade de ${productName}`"
        :loading="pending"
        :disabled="!canDecrement"
        data-haptic="double"
        @click="setQuantity(qty - 1)"
      />
      <span
        class="min-w-9 px-2 text-center text-sm font-semibold tabular-nums text-highlighted"
        aria-live="polite"
      >
        {{ qty }}
      </span>
      <UButton
        color="neutral"
        variant="ghost"
        icon="i-lucide-plus"
        :size="controlSize"
        class="rounded-none"
        :aria-label="`Aumentar quantidade de ${productName}`"
        :loading="pending"
        :disabled="!canIncrement"
        data-haptic="light"
        @click="setQuantity(qty + 1)"
      />
    </div>
  </div>
</template>
