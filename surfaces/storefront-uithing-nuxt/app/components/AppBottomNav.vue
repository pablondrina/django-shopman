<script setup lang="ts">
const route = useRoute()
const { cart, drawerOpen } = useCartState()

const items = [
  { to: '/', label: 'Inicio', icon: 'lucide:home' },
  { to: '/menu', label: 'Cardapio', icon: 'lucide:search' },
  { to: '/account', label: 'Conta', icon: 'lucide:user-round' }
]

function active (to: string) {
  if (to === '/') return route.path === '/'
  return route.path.startsWith(to)
}
</script>

<template>
  <nav class="fixed inset-x-0 bottom-0 z-40 border-t bg-background/95 pb-[env(safe-area-inset-bottom)] backdrop-blur md:hidden">
    <div class="mx-auto grid h-16 max-w-md grid-cols-4 items-center px-2">
      <NuxtLink
        v-for="item in items"
        :key="item.to"
        :to="item.to"
        class="flex min-w-0 flex-col items-center gap-1 rounded-md px-1 py-2 text-[11px] font-medium"
        :class="active(item.to) ? 'text-primary' : 'text-muted-foreground'"
      >
        <Icon :name="item.icon" class="size-5" />
        <span class="truncate">{{ item.label }}</span>
      </NuxtLink>
      <UiButton
        variant="ghost"
        class="relative h-auto min-w-0 flex-col gap-1 px-1 py-2 text-[11px] font-medium text-muted-foreground"
        @click="drawerOpen = true"
      >
        <Icon name="lucide:shopping-cart" class="size-5" />
        <span class="truncate">Carrinho</span>
        <UiBadge v-if="!cart.is_empty" variant="default" class="absolute right-2 top-1 px-1">
          {{ cart.items_count }}
        </UiBadge>
      </UiButton>
    </div>
  </nav>
</template>
