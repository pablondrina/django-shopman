<script setup lang="ts">
const session = useShopSession()
const { cart, drawerOpen } = useCartState()

const navItems = [
  { to: '/', label: 'Inicio', icon: 'lucide:home' },
  { to: '/menu', label: 'Cardapio', icon: 'lucide:utensils' },
  { to: '/account', label: 'Conta', icon: 'lucide:user-round' }
]
</script>

<template>
  <header class="sticky top-0 z-40 border-b bg-background/92 backdrop-blur supports-[backdrop-filter]:bg-background/78">
    <div class="shop-container flex h-16 items-center gap-3">
      <NuxtLink to="/" class="flex min-w-0 items-center gap-3">
        <div class="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground">
          <Icon name="lucide:shopping-basket" class="size-5" />
        </div>
        <div class="min-w-0">
          <p class="truncate text-sm font-semibold leading-5">
            {{ session.shop.value?.brand_name || 'Shopman' }}
          </p>
          <p class="truncate text-xs text-muted-foreground">
            {{ session.shopStatus.value?.message || session.shop.value?.tagline || 'Compra rapida e acompanhada' }}
          </p>
        </div>
      </NuxtLink>

      <nav class="ml-auto hidden items-center gap-1 md:flex">
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

      <UiTooltipProvider>
        <UiTooltip>
          <UiTooltipTrigger as-child>
            <UiButton
              variant="outline"
              size="icon"
              icon="lucide:shopping-cart"
              aria-label="Abrir carrinho"
              @click="drawerOpen = true"
            />
          </UiTooltipTrigger>
          <UiTooltipContent>Carrinho</UiTooltipContent>
        </UiTooltip>
      </UiTooltipProvider>

      <UiBadge v-if="!cart.is_empty" variant="success" class="-ml-3 -mt-7">
        {{ cart.items_count }}
      </UiBadge>
    </div>
  </header>
</template>
