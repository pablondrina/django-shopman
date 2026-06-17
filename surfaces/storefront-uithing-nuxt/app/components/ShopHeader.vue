<script setup lang="ts">
const session = useShopSession()
const route = useRoute()
const { cart } = useCartState()
const { cartPulse } = useCartPulse()

const menuOpen = ref(false)

const shop = computed(() => session.shop.value)
const openingHours = computed(() => session.openingHours.value)
const statusLabel = computed(() => session.shopStatus.value?.label?.trim() || '')
const statusOpen = computed(() => !!session.shopStatus.value?.is_open)
const whatsappUrl = computed(() => session.publicConfig.value?.whatsapp_url || shop.value?.whatsapp_url || '')
const socialLinks = computed(() => shop.value?.social_links || [])
const addressLinesValue = computed(() => addressLines(shop.value?.full_address))

// Navegação primária — espelha o bottom-nav, com o carrinho ganhando contador.
const primaryNav = computed(() => [
  { to: '/', label: 'Início', icon: 'lucide:home' },
  { to: '/menu', label: 'Cardápio', icon: 'lucide:utensils' },
  { to: '/cart', label: 'Carrinho', icon: 'lucide:shopping-cart', badge: cart.value.is_empty ? '' : String(cart.value.items_count) },
  { to: '/account', label: 'Conta e pedidos', icon: 'lucide:user-round' }
] as const)

const desktopNav = [
  { to: '/', label: 'Início', icon: 'lucide:home' },
  { to: '/menu', label: 'Cardápio', icon: 'lucide:utensils' },
  { to: '/account', label: 'Conta', icon: 'lucide:user-round' }
]

function navActive (to: string) {
  if (to === '/') return route.path === '/'
  return route.path.startsWith(to)
}

function closeMenu () {
  menuOpen.value = false
}
</script>

<template>
  <header class="shop-header-bar sticky top-0 z-40">
    <div class="shop-container flex h-16 items-center gap-3">
      <NuxtLink to="/" class="flex min-w-0 items-center gap-2.5" @click="closeMenu">
        <div class="flex size-9 shrink-0 items-center justify-center rounded-full bg-muted text-foreground">
          <Icon name="lucide:store" class="size-5" />
        </div>
        <p class="truncate text-xl font-semibold leading-6 tracking-tight">
          {{ shop?.brand_name || 'Shopman' }}
        </p>
      </NuxtLink>

      <nav class="ml-auto hidden items-center gap-1 md:flex" aria-label="Navegação principal">
        <UiButton
          v-for="item in desktopNav"
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

      <UiSheet v-model:open="menuOpen">
        <UiSheetTrigger as-child>
          <UiButton
            variant="ghost"
            size="icon"
            class="relative ml-auto size-11 rounded-full text-foreground md:hidden"
            aria-label="Abrir menu"
            data-shop-menu-trigger
          >
            <Icon name="lucide:menu" class="size-6" />
            <span
              v-if="!cart.is_empty"
              class="absolute right-1.5 top-1.5 size-2 rounded-full bg-primary ring-2 ring-background"
              aria-hidden="true"
            />
          </UiButton>
        </UiSheetTrigger>

        <UiSheetContent side="right" class="w-[88%] max-w-sm gap-0 p-0" data-shop-menu>
          <template #close>
            <UiSheetClose
              class="absolute right-3 top-3.5 inline-flex size-9 items-center justify-center rounded-full text-muted-foreground transition hover:bg-muted hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
              aria-label="Fechar menu"
            >
              <Icon name="lucide:x" class="size-5" />
            </UiSheetClose>
          </template>
          <div class="flex h-full flex-col">
            <div class="flex items-center gap-2.5 border-b px-5 py-4 pr-14">
              <div class="flex size-9 shrink-0 items-center justify-center rounded-full bg-muted text-foreground">
                <Icon name="lucide:store" class="size-5" />
              </div>
              <div class="min-w-0">
                <UiSheetTitle class="truncate text-base font-semibold leading-5 tracking-tight">
                  {{ shop?.brand_name || 'Shopman' }}
                </UiSheetTitle>
                <UiSheetDescription v-if="statusLabel" class="truncate text-xs" :class="statusOpen ? 'text-primary' : 'text-muted-foreground'">
                  {{ statusLabel }}
                </UiSheetDescription>
                <UiSheetDescription v-else class="sr-only">Menu da loja</UiSheetDescription>
              </div>
            </div>

            <nav class="flex-1 space-y-6 overflow-y-auto px-3 py-4" aria-label="Menu">
              <ul class="space-y-1">
                <li v-for="item in primaryNav" :key="item.to">
                  <NuxtLink
                    :to="item.to"
                    class="flex items-center gap-3 rounded-lg px-3 py-3 text-base font-semibold transition"
                    :class="navActive(item.to) ? 'bg-muted text-foreground' : 'text-foreground hover:bg-muted'"
                    :aria-current="navActive(item.to) ? 'page' : undefined"
                    @click="closeMenu"
                  >
                    <Icon :name="item.icon" class="size-5 shrink-0 text-muted-foreground" />
                    <span class="flex-1">{{ item.label }}</span>
                    <UiBadge v-if="item.badge" variant="default" size="sm" class="tabular-nums">{{ item.badge }}</UiBadge>
                    <Icon name="lucide:chevron-right" class="size-4 shrink-0 text-muted-foreground/60" />
                  </NuxtLink>
                </li>
                <li>
                  <NuxtLink
                    to="/#como-funciona"
                    class="flex items-center gap-3 rounded-lg px-3 py-3 text-base font-semibold text-foreground transition hover:bg-muted"
                    @click="closeMenu"
                  >
                    <Icon name="lucide:sparkles" class="size-5 shrink-0 text-muted-foreground" />
                    <span class="flex-1">Como funciona</span>
                    <Icon name="lucide:chevron-right" class="size-4 shrink-0 text-muted-foreground/60" />
                  </NuxtLink>
                </li>
              </ul>

              <div class="space-y-3 rounded-xl border bg-card p-4">
                <p class="shop-kicker">Visite a loja</p>

                <a
                  v-if="shop?.maps_url && addressLinesValue.length"
                  :href="shop.maps_url"
                  target="_blank"
                  rel="noopener"
                  class="flex items-start gap-3 text-sm text-foreground transition hover:text-primary"
                  @click="closeMenu"
                >
                  <Icon name="lucide:map-pin" class="mt-0.5 size-5 shrink-0 text-muted-foreground" />
                  <span class="min-w-0">
                    <span v-for="line in addressLinesValue" :key="line" class="block leading-5">{{ line }}</span>
                    <span class="mt-0.5 block text-xs text-primary">Como chegar</span>
                  </span>
                </a>

                <div v-if="openingHours.length" class="flex items-start gap-3 text-sm">
                  <Icon name="lucide:clock" class="mt-0.5 size-5 shrink-0 text-muted-foreground" />
                  <div class="min-w-0 space-y-0.5">
                    <p v-for="entry in openingHours" :key="entry.label" class="leading-5">
                      <span class="text-muted-foreground">{{ entry.label }}:</span>
                      {{ entry.hours }}
                    </p>
                  </div>
                </div>

                <a
                  v-if="shop?.phone_url && shop.phone_display"
                  :href="shop.phone_url"
                  class="flex items-center gap-3 text-sm text-foreground transition hover:text-primary"
                  @click="closeMenu"
                >
                  <Icon name="lucide:phone" class="size-5 shrink-0 text-muted-foreground" />
                  {{ shop.phone_display }}
                </a>

                <a
                  v-if="shop?.email"
                  :href="`mailto:${shop.email}`"
                  class="flex items-center gap-3 text-sm text-foreground transition hover:text-primary"
                  @click="closeMenu"
                >
                  <Icon name="lucide:mail" class="size-5 shrink-0 text-muted-foreground" />
                  <span class="truncate">{{ shop.email }}</span>
                </a>
              </div>

              <UiButton
                v-if="whatsappUrl"
                :href="whatsappUrl"
                target="_blank"
                rel="noopener"
                size="lg"
                variant="outline"
                icon="lucide:message-circle"
                class="w-full"
                @click="closeMenu"
              >
                Falar no WhatsApp
              </UiButton>

              <div v-if="socialLinks.length" class="space-y-2">
                <p class="px-1 shop-kicker">Redes sociais</p>
                <div class="flex flex-wrap gap-2">
                  <a
                    v-for="link in socialLinks"
                    :key="link.url"
                    :href="link.url"
                    target="_blank"
                    rel="noopener"
                    :title="link.label"
                    :aria-label="link.label"
                    class="inline-flex size-11 items-center justify-center rounded-full border text-foreground transition hover:bg-muted hover:text-primary"
                    @click="closeMenu"
                  >
                    <span class="size-5" v-html="link.icon_svg" />
                  </a>
                </div>
              </div>
            </nav>

            <div class="border-t px-5 py-3 shop-meta">
              {{ shop?.brand_name || 'Shopman' }}
            </div>
          </div>
        </UiSheetContent>
      </UiSheet>
    </div>
  </header>
</template>
