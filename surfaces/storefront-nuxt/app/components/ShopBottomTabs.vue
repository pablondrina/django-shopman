<script setup lang="ts">
import type { NavigationMenuItem } from '@nuxt/ui'
import type { AuthSessionResponse } from '~/types/shopman'

const route = useRoute()
const apiPath = useShopmanApiPath()
const requestHeaders = import.meta.server ? useRequestHeaders(['cookie']) : undefined
const { cart } = useCartState()
const { isAuthenticated, setFromAuthSession } = useShopSession()
const activeOrderCount = ref(0)
const isHydrated = ref(false)

const { data: authSession } = await useFetch<AuthSessionResponse>(apiPath('/api/auth/session/'), {
  credentials: 'include',
  headers: requestHeaders,
  key: 'shopman-auth-session'
})

watch(authSession, (next) => {
  setFromAuthSession(next)
}, { immediate: true })

async function loadActiveOrders () {
  if (!isAuthenticated.value) {
    activeOrderCount.value = 0
    return
  }
  try {
    const response = await $fetch<{ count: number }>(apiPath('/api/v1/account/orders/active/'), {
      credentials: 'include'
    })
    activeOrderCount.value = response.count || 0
  } catch {
    activeOrderCount.value = 0
  }
}

watch(isAuthenticated, () => {
  void loadActiveOrders()
}, { immediate: true })

if (import.meta.client) {
  let activeOrdersTimer: ReturnType<typeof setInterval> | null = null
  onMounted(() => {
    isHydrated.value = true
    activeOrdersTimer = setInterval(() => { void loadActiveOrders() }, 30_000)
  })
  onBeforeUnmount(() => {
    if (activeOrdersTimer) clearInterval(activeOrdersTimer)
  })
}

const accountTo = computed(() => isAuthenticated.value ? '/conta' : '/login')
const accountLabel = computed(() => isAuthenticated.value ? 'Conta' : 'Entrar')
const accountIcon = computed(() => isAuthenticated.value ? 'i-lucide-user' : 'i-lucide-log-in')

const items = computed<NavigationMenuItem[]>(() => [
  {
    label: 'Início',
    icon: 'i-lucide-home',
    to: '/',
    active: route.path === '/'
  },
  {
    label: 'Cardápio',
    icon: 'i-lucide-utensils',
    to: '/menu',
    active: route.path.startsWith('/menu') || route.path.startsWith('/produto')
  },
  {
    label: 'Carrinho',
    icon: 'i-lucide-shopping-bag',
    to: '/cart',
    active: route.path.startsWith('/cart') || route.path.startsWith('/checkout'),
    badge: isHydrated.value ? cart.value.items_count || undefined : undefined
  },
  {
    label: accountLabel.value,
    icon: accountIcon.value,
    to: accountTo.value,
    active: route.path.startsWith('/conta') || route.path.startsWith('/login'),
    badge: activeOrderCount.value || undefined
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
        link: 'flex-col gap-1 px-3 min-w-16 relative',
        linkLeadingIcon: 'size-5',
        linkLabel: 'text-xs leading-4 font-medium',
        linkTrailing: 'absolute -top-1 -end-1',
        linkTrailingBadge: 'min-w-5 justify-center rounded-full'
      }"
      class="w-full"
    />
  </nav>
</template>
