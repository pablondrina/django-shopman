<script setup lang="ts">
const { cart } = useCartState()
</script>

<template>
  <Transition name="cartbar">
    <UPageCard
      v-if="!cart.is_empty"
      as="aside"
      variant="solid"
      class="shop-bottom-cart"
      :ui="{ container: 'p-3 sm:p-3' }"
    >
      <NuxtLink to="/cart" class="shop-bottom-cart-inner" aria-label="Ver carrinho">
        <UBadge color="primary" variant="solid" size="lg">
          {{ cart.items_count }}
        </UBadge>
        <span class="shop-bottom-cart-copy">
          <strong>{{ cart.grand_total_display }}</strong>
          <span>
            {{ cart.items_count === 1 ? '1 item no carrinho' : `${cart.items_count} itens no carrinho` }}
          </span>
        </span>
        <UButton color="primary" variant="solid" size="sm" icon="i-lucide-shopping-cart" label="Ver" />
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
