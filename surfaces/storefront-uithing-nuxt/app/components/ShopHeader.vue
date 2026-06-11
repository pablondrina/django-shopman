<script setup lang="ts">
const session = useShopSession()
const { cart } = useCartState()
const { cartPulse } = useCartPulse()

const navItems = [
  { to: '/', label: 'Início', icon: 'lucide:home' },
  { to: '/menu', label: 'Cardápio', icon: 'lucide:utensils' },
  { to: '/account', label: 'Conta', icon: 'lucide:user-round' }
]
</script>

<template>
  <header class="sticky top-0 z-40 border-b bg-background">
    <div class="shop-container flex h-14 items-center gap-3 md:h-16">
      <NuxtLink to="/" class="flex min-w-0 items-center gap-2.5">
        <div class="flex size-8 shrink-0 items-center justify-center text-foreground">
          <Icon name="lucide:store" class="size-5" />
        </div>
        <p class="truncate text-sm font-semibold leading-5">
          {{ session.shop.value?.brand_name || 'Shopman' }}
        </p>
      </NuxtLink>

      <nav class="ml-auto hidden items-center gap-1 md:flex" aria-label="Navegação principal">
        <UiButton
          v-for="item in navItems"
          :key="item.to"
          :to="item.to"
          variant="ghost"
          size="sm"
          :icon="item.icon"
          :text="item.label"
        />
      </nav>

      <UiButton
        to="/cart"
        variant="outline"
        size="sm"
        icon="lucide:shopping-cart"
        :text="cart.is_empty ? 'Carrinho' : `Carrinho (${cart.items_count})`"
        class="hidden md:inline-flex"
        :class="cartPulse ? 'scale-[1.03] ring-2 ring-primary/25' : ''"
        aria-label="Ver carrinho"
      />
    </div>
  </header>
</template>
