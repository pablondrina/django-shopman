<script setup lang="ts">
const route = useRoute()
const { cart } = useCartState()
const cartPulse = ref(false)
let cartPulseTimer: ReturnType<typeof setTimeout> | null = null

const items = [
  { to: '/', label: 'Início', icon: 'lucide:home' },
  { to: '/menu', label: 'Cardápio', icon: 'lucide:search' },
  { to: '/account', label: 'Conta', icon: 'lucide:user-round' }
]

function active (to: string) {
  if (to === '/') return route.path === '/'
  return route.path.startsWith(to)
}

watch(() => cart.value.items_count, (next, previous) => {
  if (previous == null || next <= previous) return
  cartPulse.value = true
  if (cartPulseTimer) clearTimeout(cartPulseTimer)
  cartPulseTimer = setTimeout(() => {
    cartPulse.value = false
    cartPulseTimer = null
  }, 900)
})

onBeforeUnmount(() => {
  if (cartPulseTimer) clearTimeout(cartPulseTimer)
})
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
      <NuxtLink
        to="/cart"
        class="relative flex min-w-0 flex-col items-center gap-1 rounded-md px-1 py-2 text-[11px] font-medium"
        :class="[active('/cart') ? 'text-primary' : 'text-muted-foreground', cartPulse ? 'scale-105 text-primary' : '']"
      >
        <Icon name="lucide:shopping-cart" class="size-5 transition-transform" :class="cartPulse ? 'scale-110' : ''" />
        <span class="truncate">Carrinho</span>
        <UiBadge
          v-if="!cart.is_empty"
          variant="default"
          size="sm"
          class="absolute right-2 top-1 size-5 min-w-5 rounded-full p-0 text-[11px] font-semibold tabular-nums transition-transform"
          :class="cartPulse ? 'scale-125 ring-2 ring-primary/25' : ''"
        >
          {{ cart.items_count }}
        </UiBadge>
      </NuxtLink>
    </div>
  </nav>
</template>
