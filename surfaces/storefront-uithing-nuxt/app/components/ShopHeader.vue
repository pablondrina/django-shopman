<script setup lang="ts">
const session = useShopSession()
const { cart } = useCartState()
const mobileMenuOpen = ref(false)
const cartPulse = ref(false)
let cartPulseTimer: ReturnType<typeof setTimeout> | null = null

const navItems = [
  { to: '/', label: 'Início', icon: 'lucide:home' },
  { to: '/menu', label: 'Cardápio', icon: 'lucide:utensils' },
  { to: '/account', label: 'Conta', icon: 'lucide:user-round' }
]

const whatsappUrl = computed(() => session.publicConfig.value?.whatsapp_url || session.shop.value?.whatsapp_url || '')

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
  <header class="sticky top-0 z-40 border-b bg-background">
    <div class="shop-container flex h-16 items-center gap-3">
      <NuxtLink to="/" class="flex min-w-0 items-center gap-3">
        <div class="flex size-8 shrink-0 items-center justify-center text-foreground">
          <Icon name="lucide:store" class="size-5" />
        </div>
        <div class="min-w-0">
          <p class="truncate text-sm font-semibold leading-5">
            {{ session.shop.value?.brand_name || 'Shopman' }}
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

      <UiSheet v-model:open="mobileMenuOpen">
        <UiButton
          variant="ghost"
          size="icon"
          icon="lucide:menu"
          class="ml-auto md:hidden"
          aria-label="Abrir menu"
          @click="mobileMenuOpen = true"
        />
        <UiSheetContent side="bottom" variant="floating" class="mx-auto max-w-md">
          <UiSheetHeader>
            <UiSheetTitle title="Menu" />
            <UiSheetDescription :description="session.shop.value?.brand_name || 'Shopman'" />
          </UiSheetHeader>
          <div class="grid gap-2 px-4 pb-4">
            <UiButton
              v-for="item in navItems"
              :key="item.to"
              :to="item.to"
              variant="ghost"
              class="w-full justify-start"
              :icon="item.icon"
              @click="mobileMenuOpen = false"
            >
              {{ item.label }}
            </UiButton>
            <UiButton
              v-if="whatsappUrl"
              :href="whatsappUrl"
              target="_blank"
              variant="outline"
              class="w-full justify-start"
              icon="lucide:message-circle"
              @click="mobileMenuOpen = false"
            >
              WhatsApp
            </UiButton>
          </div>
        </UiSheetContent>
      </UiSheet>
    </div>
  </header>
</template>
