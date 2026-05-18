<script setup lang="ts">
import type { ProductMutationMeta } from '~/types/shopman'

const props = withDefaults(defineProps<{
  meta: ProductMutationMeta
  qty: number
  disabled?: boolean
  maxQty?: number | null
  compact?: boolean
  addLabel?: string
}>(), {
  addLabel: 'Adicionar'
})

const { setSkuQty, isPending } = useCartState()
const hydrated = ref(false)
const pending = computed(() => isPending(props.meta.sku))

onMounted(() => {
  hydrated.value = true
})

async function addOne () {
  if (!hydrated.value || props.disabled || pending.value) return
  await setSkuQty(props.meta, 1)
}
</script>

<template>
  <QuantityControl
    v-if="qty > 0"
    :meta="meta"
    :qty="qty"
    :disabled="disabled"
    :max-qty="maxQty"
    :compact="compact"
  />
  <UiButton
    v-else
    variant="default"
    :size="compact ? 'sm' : 'default'"
    icon="lucide:shopping-cart"
    :disabled="!hydrated || disabled || pending"
    :loading="pending"
    @click="addOne"
  >
    {{ addLabel }}
  </UiButton>
</template>
