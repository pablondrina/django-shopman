<script setup lang="ts">
import type { DropdownMenuItem, NavigationMenuItem } from '@nuxt/ui'
import type { AuthSessionResponse, HomeResponse } from '~/types/shopman'

const route = useRoute()
const { cart, setFromServer } = useCartState()
const { customerName, isAuthenticated, shopStatus, shop, setFromHome, setFromAuthSession } = useShopSession()
const apiPath = useShopmanApiPath()
const requestHeaders = import.meta.server ? useRequestHeaders(['cookie']) : undefined

const mobileOpen = ref(false)

const { data: shellHome } = await useFetch<HomeResponse>(apiPath('/api/v1/storefront/home/'), {
  credentials: 'include',
  headers: requestHeaders,
  key: 'shopman-shell-home'
})

const { data: authSession } = await useFetch<AuthSessionResponse>(apiPath('/api/auth/session/'), {
  credentials: 'include',
  headers: requestHeaders,
  key: 'shopman-auth-session'
})

const shellShop = computed(() => shellHome.value?.home.shop || shop.value)
const shellShopStatus = computed(() => shellHome.value?.home.shop_status || shopStatus.value)
const displayBrand = computed(() => shellShop.value?.brand_name || 'Shopman')

setFromHome(shellHome.value?.home)
setFromServer(shellHome.value?.cart)
setFromAuthSession(authSession.value)

watch(shellHome, (next) => {
  setFromHome(next?.home)
  setFromServer(next?.cart)
})

watch(authSession, (next) => {
  setFromAuthSession(next)
})

const navItems = computed<NavigationMenuItem[]>(() => [
  { label: 'Início', to: '/' },
  { label: 'Cardápio', to: '/menu' }
])

const accountInitials = computed(() => {
  const name = customerName.value
  if (!name) return 'C'
  const parts = name.split(' ').filter(Boolean)
  if (!parts.length) return 'C'
  return parts.slice(0, 2).map(p => p[0]?.toUpperCase() || '').join('')
})

const accountDisplayName = computed(() => customerName.value || 'Sua conta')
const accountAriaLabel = computed(() => {
  if (!isAuthenticated.value) return 'Entrar ou criar conta'
  return customerName.value ? `Menu da conta de ${customerName.value}` : 'Menu da conta'
})

const accountMenu = computed<DropdownMenuItem[][]>(() => {
  if (isAuthenticated.value) {
    return [
      [
        {
          label: accountDisplayName.value,
          slot: 'profile',
          type: 'label'
        }
      ],
      [
        { label: 'Minha conta', to: '/conta' },
        { label: 'Meus pedidos', to: '/conta' },
        { label: 'Endereços', to: '/conta' }
      ],
      [
        {
          label: 'Sair da conta',
          to: { path: '/sair', query: { cancel: route.fullPath || '/' } }
        }
      ]
    ]
  }
  return [[
    { label: 'Entrar', to: '/login' },
    { label: 'Criar conta', to: '/login?novo=1' }
  ]]
})

const cartCount = computed(() => cart.value.items_count || 0)
const statusLabel = computed(() => shellShopStatus.value?.message || '')
const statusColor = computed(() => shellShopStatus.value?.is_open ? 'success' : 'warning')
const accountTo = computed(() => isAuthenticated.value ? '/conta' : '/login')

watch(() => route.fullPath, () => {
  mobileOpen.value = false
})
</script>

<template>
  <header class="sticky top-0 z-50 border-b border-default bg-default/88 backdrop-blur-xl">
    <UContainer class="flex h-(--ui-header-height) min-w-0 items-center justify-between gap-3">
      <NuxtLink
        to="/"
        class="group flex min-w-0 shrink items-center gap-2.5 focus-visible:outline-primary"
        :aria-label="displayBrand"
      >
        <span class="grid size-9 place-items-center overflow-hidden rounded-lg bg-primary/12 text-primary ring-1 ring-primary/20">
          <img
            v-if="shellShop?.logo_url"
            :src="shellShop.logo_url"
            :alt="displayBrand"
            class="size-full object-contain p-1"
          >
          <UIcon v-else name="i-lucide-wheat" class="size-5" />
        </span>
          <span class="grid min-w-0 leading-tight">
            <span class="max-w-[11rem] truncate text-base font-bold text-highlighted sm:max-w-xs">{{ displayBrand }}</span>
            <span v-if="shellShop?.tagline" class="hidden text-xs text-muted sm:block">{{ shellShop.tagline }}</span>
          </span>
      </NuxtLink>

      <UNavigationMenu
        :items="navItems"
        variant="link"
        highlight
        class="hidden lg:flex"
      />

      <div class="flex shrink-0 items-center gap-1.5 sm:gap-2">
        <UBadge
          v-if="statusLabel"
          :color="statusColor"
          variant="subtle"
          class="hidden max-w-52 truncate lg:inline-flex"
        >
          <span class="size-1.5 rounded-full" :class="shellShopStatus?.is_open ? 'bg-success' : 'bg-warning'" />
          {{ statusLabel }}
        </UBadge>

        <UButton
          to="/cart"
          color="neutral"
          :variant="cartCount ? 'soft' : 'ghost'"
          icon="i-lucide-shopping-bag"
          class="hidden sm:inline-flex"
          :badge="cartCount || undefined"
          :aria-label="cartCount ? `Ver carrinho com ${cartCount} itens` : 'Ver carrinho'"
        />

        <div class="hidden sm:block">
          <UDropdownMenu :items="accountMenu" :ui="{ content: 'min-w-56' }">
            <UButton
              color="neutral"
              variant="ghost"
              :icon="isAuthenticated ? undefined : 'i-lucide-user'"
              :aria-label="accountAriaLabel"
            >
              <UAvatar
                v-if="isAuthenticated"
                :text="accountInitials"
                size="sm"
                class="bg-primary/10 text-primary font-semibold"
              />
            </UButton>

            <template #profile>
              <div class="flex items-center gap-3 p-1">
                <UAvatar :text="accountInitials" size="md" class="bg-primary/10 text-primary font-semibold" />
                <div class="min-w-0">
                  <p class="text-sm font-semibold text-highlighted truncate">{{ accountDisplayName }}</p>
                  <p class="text-sm text-muted">Cliente da casa</p>
                </div>
              </div>
            </template>
          </UDropdownMenu>
        </div>

        <UButton
          class="lg:hidden"
          color="neutral"
          variant="ghost"
          :icon="mobileOpen ? 'i-lucide-x' : 'i-lucide-menu'"
          :aria-label="mobileOpen ? 'Fechar menu' : 'Abrir menu'"
          :aria-expanded="mobileOpen"
          aria-controls="mobile-main-menu"
          @click="mobileOpen = !mobileOpen"
        />
      </div>
    </UContainer>

    <div
      v-if="mobileOpen"
      id="mobile-main-menu"
      class="lg:hidden border-t border-default bg-default/98 shadow-xl"
    >
      <UContainer class="py-4">
        <div v-if="statusLabel" class="mb-3 rounded-lg border border-default bg-elevated/65 px-3 py-2 text-sm">
          <div class="flex items-center gap-2">
            <span class="size-2 rounded-full" :class="shellShopStatus?.is_open ? 'bg-success' : 'bg-warning'" />
            <span class="text-muted">{{ statusLabel }}</span>
          </div>
        </div>

        <nav aria-label="Menu principal" class="grid gap-1.5">
          <NuxtLink
            v-for="item in navItems"
            :key="item.to"
            :to="item.to || '/'"
            class="flex items-center rounded-lg px-3 py-2.5 text-sm text-muted hover:bg-elevated hover:text-highlighted"
            :class="route.path === item.to && 'bg-elevated text-highlighted'"
          >
            <span>{{ item.label }}</span>
          </NuxtLink>
          <NuxtLink
            :to="accountTo"
            class="flex items-center rounded-lg px-3 py-2.5 text-sm text-muted hover:bg-elevated hover:text-highlighted"
          >
            <span>{{ isAuthenticated ? 'Minha conta' : 'Entrar' }}</span>
          </NuxtLink>
        </nav>

        <div v-if="!cart.is_empty" class="mt-4 rounded-lg border border-primary/25 bg-primary/8 p-3 text-sm">
          <div class="flex items-center justify-between gap-3">
            <span class="text-muted">{{ cart.items_count === 1 ? '1 item' : `${cart.items_count} itens` }}</span>
            <strong class="tabular-nums text-highlighted">{{ cart.summary_pending ? 'Atualizando...' : cart.grand_total_display }}</strong>
          </div>
          <UButton
            to="/cart"
            label="Ver carrinho"
            block
            size="sm"
            class="mt-3"
          />
        </div>
      </UContainer>
    </div>
  </header>
</template>
