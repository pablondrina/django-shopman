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

function navActive (to: string) {
  if (to === '/') return route.path === '/'
  return route.path.startsWith(to)
}

function closeMenu () {
  menuOpen.value = false
}

function toggleMenu () {
  menuOpen.value = !menuOpen.value
}

// Fecha ao navegar.
watch(() => route.fullPath, closeMenu)

// Trava o scroll do corpo e fecha no Esc enquanto o menu está aberto (client-only).
function onKeydown (event: KeyboardEvent) {
  if (event.key === 'Escape') closeMenu()
}

watch(menuOpen, open => {
  if (!import.meta.client) return
  document.body.style.overflow = open ? 'hidden' : ''
  if (open) window.addEventListener('keydown', onKeydown)
  else window.removeEventListener('keydown', onKeydown)
})

onBeforeUnmount(() => {
  if (!import.meta.client) return
  document.body.style.overflow = ''
  window.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <header class="shop-header-bar sticky top-0 z-40">
    <!-- Barra de status: horário/status (esq) · telefone (dir). Substitui o banner genérico. -->
    <div class="bg-ink text-ink-foreground">
      <div class="shop-container flex h-9 items-center justify-between gap-3 text-sm">
        <span class="flex min-w-0 items-center gap-2 opacity-90">
          <Icon name="lucide:clock" class="size-3.5 shrink-0" />
          <span class="truncate">{{ statusLabel || 'Confira nossos horários' }}</span>
        </span>
        <a
          v-if="statusOpen && shop?.phone_url"
          :href="shop.phone_url"
          class="flex shrink-0 items-center gap-2 font-medium opacity-90 transition hover:opacity-100"
          :aria-label="`Ligar para ${shop?.brand_name || 'a loja'}`"
        >
          <span>Ligar</span>
          <Icon name="lucide:phone" class="size-3.5" />
        </a>
        <a
          v-else-if="!statusOpen && whatsappUrl"
          :href="whatsappUrl"
          target="_blank"
          rel="noopener"
          class="flex shrink-0 items-center gap-2 font-medium opacity-90 transition hover:opacity-100"
          :aria-label="`Enviar mensagem para ${shop?.brand_name || 'a loja'}`"
        >
          <span>Mensagem</span>
          <Icon name="lucide:message-circle" class="size-3.5" />
        </a>
      </div>
    </div>

    <!-- Barra principal: hambúrguer (esq) · logo central · carrinho (dir). -->
    <div class="shop-container relative flex h-16 items-center">
      <UiButton
        variant="ghost"
        size="icon"
        class="relative -ml-2 size-11 rounded-full text-foreground"
        :aria-label="menuOpen ? 'Fechar menu' : 'Abrir menu'"
        aria-haspopup="true"
        :aria-expanded="menuOpen"
        aria-controls="shop-menu-panel"
        data-shop-menu-trigger
        @click="toggleMenu"
      >
        <Icon :name="menuOpen ? 'lucide:x' : 'lucide:menu'" class="size-6" />
      </UiButton>

      <!-- Logo centralizado. SVG oficial Nelson Boulangerie. -->
      <NuxtLink
        to="/"
        class="absolute left-1/2 flex -translate-x-1/2 items-center"
        aria-label="Página inicial"
        @click="closeMenu"
      >
        <ShopLogo class="h-12 w-auto" />
      </NuxtLink>

      <UiButton
        to="/cart"
        variant="ghost"
        size="icon"
        class="relative -mr-2 ml-auto size-11 rounded-full text-foreground"
        :class="cartPulse ? 'scale-105' : ''"
        aria-label="Ver carrinho"
      >
        <Icon name="lucide:shopping-cart" class="size-6" />
        <UiBadge
          v-if="!cart.is_empty"
          variant="default"
          size="sm"
          class="absolute -right-1 -top-1 size-5 min-w-5 rounded-full p-0 text-[11px] font-semibold tabular-nums ring-2 ring-background"
          :class="cartPulse ? 'scale-110' : ''"
        >{{ cart.items_count }}</UiBadge>
      </UiButton>
    </div>

    <!-- Menu: brota verticalmente sob a navbar, seção full-width em fundo da marca.
         Teleportado p/ o body — fora do remap de tokens do .shop-header-bar (que
         deixaria o fundo burgundy), então usa o canvas real da marca (amarelinho). -->
    <Teleport to="body">
      <Transition name="shop-menu-drop">
        <div
          v-if="menuOpen"
          id="shop-menu-panel"
          class="fixed inset-x-0 top-25 z-40 border-t border-border bg-background text-foreground shadow-xl"
          data-shop-menu-panel
        >
          <nav class="shop-container max-h-[calc(100dvh-6.25rem)] shop-stack-block overflow-y-auto py-4" aria-label="Menu">
          <ul class="shop-stack-micro">
            <li v-for="item in primaryNav" :key="item.to">
              <NuxtLink
                :to="item.to"
                class="shop-gold-hover flex items-center gap-3 rounded-lg px-3 py-3 text-base font-semibold transition"
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
                class="shop-gold-hover flex items-center gap-3 rounded-lg px-3 py-3 text-base font-semibold text-foreground transition hover:bg-muted"
                @click="closeMenu"
              >
                <Icon name="lucide:sparkles" class="size-5 shrink-0 text-muted-foreground" />
                <span class="flex-1">Como funciona</span>
                <Icon name="lucide:chevron-right" class="size-4 shrink-0 text-muted-foreground/60" />
              </NuxtLink>
            </li>
          </ul>

          <div class="shop-stack-tight rounded-lg border bg-card p-4">
            <p class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Visite a loja</p>

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
              <div class="min-w-0 shop-stack-micro">
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
            <p class="px-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Redes sociais</p>
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
        </div>
      </Transition>
    </Teleport>

    <!-- Scrim: escurece a página sob a navbar (z menor que o header). -->
    <Teleport to="body">
      <Transition name="shop-menu-fade">
        <div
          v-if="menuOpen"
          class="fixed inset-0 z-30 bg-foreground/40 backdrop-blur-[2px]"
          aria-hidden="true"
          @click="closeMenu"
        />
      </Transition>
    </Teleport>
  </header>
</template>

<style scoped>
.shop-menu-drop-enter-active,
.shop-menu-drop-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}
.shop-menu-drop-enter-from,
.shop-menu-drop-leave-to {
  opacity: 0;
  transform: translateY(-0.5rem);
}
.shop-menu-fade-enter-active,
.shop-menu-fade-leave-active {
  transition: opacity 0.2s ease;
}
.shop-menu-fade-enter-from,
.shop-menu-fade-leave-to {
  opacity: 0;
}
</style>
