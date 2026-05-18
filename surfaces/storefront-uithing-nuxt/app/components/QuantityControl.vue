<script setup lang="ts">
import type { ProductMutationMeta } from '~/types/shopman'

const props = defineProps<{
  meta: ProductMutationMeta
  qty: number
  disabled?: boolean
  maxQty?: number | null
  compact?: boolean
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
  const numeric = Number.isFinite(value) ? Math.max(0, Math.trunc(value)) : 0
  const next = props.maxQty != null ? Math.min(numeric, props.maxQty) : numeric
  localQty.value = next
  await setSkuQty(props.meta, next)
  emit('changed', next)
}

const controlClass = computed(() => props.compact ? 'w-28' : 'w-36')
</script>

<template>
  <UiNumberField
    v-model="localQty"
    :min="0"
    :max="maxQty ?? undefined"
    :disabled="disabled || pending"
    :class="controlClass"
    aria-label="Quantidade"
    @update:model-value="commit(Number($event || 0))"
  />
</template>
