<script setup lang="ts">
const route = useRoute()
const { cart } = useCartState()
const isHydrated = ref(false)

const target = computed(() => route.path.startsWith('/cart') ? '/checkout' : '/cart')
const actionLabel = computed(() => route.path.startsWith('/cart') ? 'Finalizar' : 'Ver')
const isBrowsingSurface = computed(() =>
  route.path === '/' ||
  route.path.startsWith('/menu') ||
  route.path.startsWith('/produto') ||
  route.path.startsWith('/como-funciona')
)
const shouldShow = computed(() => isHydrated.value && !cart.value.is_empty && isBrowsingSurface.value)

onMounted(() => {
  isHydrated.value = true
})
</script>

<template>
  <Transition name="cartbar">
    <UPageCard
      v-if="shouldShow"
      as="aside"
      variant="solid"
      class="shop-bottom-cart"
      :ui="{ container: 'p-3 sm:p-3' }"
    >
      <NuxtLink :to="target" class="flex items-center justify-between gap-3" aria-label="Ver carrinho">
        <UBadge color="primary" variant="solid" size="lg">
          {{ cart.items_count }}
        </UBadge>
        <span class="grid flex-1 min-w-0 text-sm">
          <strong>{{ cart.summary_pending ? 'Atualizando...' : cart.grand_total_display }}</strong>
          <span class="text-xs text-white/68">
            {{ cart.items_count === 1 ? '1 item no carrinho' : `${cart.items_count} itens no carrinho` }}
          </span>
        </span>
        <UButton color="primary" variant="solid" size="sm" :label="actionLabel" />
      </NuxtLink>
    </UPageCard>
  </Transition>
</template>

<style scoped>
.cartbar-enter-active,
.cartbar-leave-active {
  transition: transform 160ms ease, opacity 160ms ease;
}

.cartbar-enter-from,
.cartbar-leave-to {
  opacity: 0;
  transform: translateY(12px);
}
</style>
