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

function decrement () {
  void commit(localQty.value - 1)
}

function increment () {
  void commit(localQty.value + 1)
}
</script>

<template>
  <div class="flex items-center gap-2">
    <UiButton
      variant="outline"
      :size="compact ? 'icon-sm' : 'icon'"
      icon="lucide:minus"
      :disabled="disabled || pending || localQty <= 0"
      aria-label="Diminuir quantidade"
      @click="decrement"
    />
    <UiNumberField
      v-model="localQty"
      :min="0"
      :max="maxQty ?? undefined"
      :disabled="disabled || pending"
      class="w-24"
      @update:model-value="commit(Number($event || 0))"
    />
    <UiButton
      variant="outline"
      :size="compact ? 'icon-sm' : 'icon'"
      icon="lucide:plus"
      :disabled="disabled || pending"
      aria-label="Aumentar quantidade"
      @click="increment"
    />
  </div>
</template>
