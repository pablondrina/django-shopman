<script setup lang="ts">
const { cart } = useCartState()

const cartBadge = computed(() => cart.value.items_count ? String(cart.value.items_count) : undefined)
const navigation = computed(() => [
  { label: 'Menu', to: '/menu', icon: 'i-lucide-store' },
  { label: 'Carrinho', to: '/cart', icon: 'i-lucide-shopping-bag', badge: cartBadge.value },
  { label: 'Finalizar', to: '/checkout', icon: 'i-lucide-credit-card' }
])
</script>

<template>
  <UHeader
    title="Shopman"
    to="/menu"
    mode="drawer"
    :toggle="{ color: 'neutral', variant: 'ghost' }"
    class="shop-header"
  >
    <UNavigationMenu :items="navigation" variant="link" highlight class="shop-header-nav" />

    <template #right>
      <UBadge v-if="cart.items_count" color="neutral" variant="soft" class="hidden sm:inline-flex">
        {{ cart.grand_total_display }}
      </UBadge>
      <UButton
        to="/cart"
        color="neutral"
        variant="outline"
        icon="i-lucide-shopping-bag"
        :label="cart.items_count ? `Carrinho ${cart.items_count}` : 'Carrinho'"
        class="shop-header-cart-button"
      />
    </template>

    <template #body>
      <UNavigationMenu :items="navigation" orientation="vertical" variant="link" class="-mx-2" />
    </template>
  </UHeader>
</template>
