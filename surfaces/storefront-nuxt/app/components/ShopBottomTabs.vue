<script setup lang="ts">
import type { NavigationMenuItem } from '@nuxt/ui'

const route = useRoute()
const { cart } = useCartState()

const items = computed<NavigationMenuItem[]>(() => [
  {
    label: 'Menu',
    icon: 'i-lucide-store',
    to: '/menu',
    active: route.path === '/' || route.path.startsWith('/menu') || route.path.startsWith('/produto')
  },
  {
    label: 'Carrinho',
    icon: 'i-lucide-shopping-bag',
    to: '/cart',
    active: route.path.startsWith('/cart') || route.path.startsWith('/checkout'),
    badge: cart.value.items_count || undefined
  }
])
</script>

<template>
  <nav class="shop-bottom-tabs" aria-label="Navegação principal">
    <UNavigationMenu
      :items="items"
      color="neutral"
      variant="link"
      :ui="{
        root: 'justify-around border-t border-default py-2',
        item: 'py-0',
        link: 'flex-col gap-1 px-3 relative',
        linkLeadingIcon: 'size-5',
        linkLabel: 'text-[10px]/3 font-normal',
        linkTrailing: 'absolute -top-1 -end-1',
        linkTrailingBadge: 'min-w-5 justify-center rounded-full'
      }"
      class="w-full"
    />
  </nav>
</template>
