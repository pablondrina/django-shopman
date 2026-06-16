<script setup lang="ts">
const route = useRoute()
const { cart } = useCartState()
const { cartPulse } = useCartPulse()

const items = [
  { to: '/', label: 'Início', icon: 'lucide:home', showsCartBadge: false },
  { to: '/menu', label: 'Cardápio', icon: 'lucide:utensils', showsCartBadge: false },
  { to: '/cart', label: 'Carrinho', icon: 'lucide:shopping-cart', showsCartBadge: true },
  { to: '/account', label: 'Conta', icon: 'lucide:user-round', showsCartBadge: false }
]

function active (to: string) {
  if (to === '/') return route.path === '/'
  return route.path.startsWith(to)
}
</script>

<template>
  <nav
    class="shop-bottomnav-bar fixed inset-x-0 bottom-0 z-40 border-t bg-bottomnav/95 pb-[env(safe-area-inset-bottom)] backdrop-blur md:hidden"
    aria-label="Navegação principal"
  >
    <div class="mx-auto grid h-16 max-w-md grid-cols-4 items-center px-2">
      <NuxtLink
        v-for="item in items"
        :key="item.to"
        :to="item.to"
        class="relative flex min-w-0 flex-col items-center gap-1 rounded-md px-1 py-2 text-xs"
        :class="[active(item.to) ? 'font-bold text-primary' : 'text-muted-foreground', item.showsCartBadge && cartPulse ? 'scale-105 text-primary' : '']"
        :aria-current="active(item.to) ? 'page' : undefined"
      >
        <Icon
          :name="item.icon"
          class="size-5"
          :class="[active(item.to) ? 'fill-current' : '', item.showsCartBadge ? ['transition-transform', cartPulse ? 'scale-110' : ''] : '']"
        />
        <span class="truncate">{{ item.label }}</span>
        <UiBadge
          v-if="item.showsCartBadge && !cart.is_empty"
          variant="default"
          size="sm"
          class="absolute right-2 top-1 size-5 min-w-5 rounded-full p-0 text-xs font-semibold tabular-nums transition-transform"
          :class="cartPulse ? 'scale-125 ring-2 ring-primary/25' : ''"
        >
          {{ cart.items_count }}
        </UiBadge>
      </NuxtLink>
    </div>
  </nav>
</template>
