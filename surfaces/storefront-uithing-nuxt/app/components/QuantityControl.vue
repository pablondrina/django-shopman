<script setup lang="ts">
import type { ProductMutationMeta } from '~/types/shopman'

const props = defineProps<{
  meta: ProductMutationMeta
  qty: number
  disabled?: boolean
  maxQty?: number | null
  minQty?: number
  compact?: boolean
  tone?: 'default' | 'inverted'
}>()

const emit = defineEmits<{
  changed: [qty: number]
}>()

const { setSkuQty, isPending } = useCartState()
const localQty = ref(props.qty)

watch(() => props.qty, value => {
  localQty.value = value
})

const pending = computed(() => isPending(props.meta.sku))

async function commit (value: number) {
  const next = clampQuantity(value, props.maxQty, props.minQty ?? 0)
  localQty.value = next
  await setSkuQty(props.meta, next)
  emit('changed', next)
}

function handleModelValue (value: unknown) {
  const next = quantityFromModelValue(value, props.minQty ?? 0)
  if (next === null) return
  if (pending.value) {
    localQty.value = props.qty
    return
  }
  if (next === props.qty) {
    localQty.value = next
    return
  }
  void commit(next).catch(() => {
    localQty.value = props.qty
  })
}

const controlClass = computed(() => [
  props.compact ? 'w-28' : 'w-36',
  props.tone === 'inverted' ? 'border-background/30 bg-background text-foreground' : ''
])
</script>

<template>
  <UiNumberField
    v-model="localQty"
    :min="minQty ?? 0"
    :max="maxQty ?? undefined"
    :disabled="disabled || pending"
    :class="controlClass"
    aria-label="Quantidade"
    @update:model-value="handleModelValue"
  />
</template>
