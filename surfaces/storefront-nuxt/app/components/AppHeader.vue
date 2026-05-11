<script setup lang="ts">
import type { DropdownMenuItem, NavigationMenuItem } from '@nuxt/ui'

const { cart } = useCartState()
const { customerName, isAuthenticated, shopStatus, shop } = useShopSession()

const navItems = computed<NavigationMenuItem[]>(() => [
  { label: 'Início', to: '/', icon: 'i-lucide-home' },
  { label: 'Cardápio', to: '/menu', icon: 'i-lucide-utensils' }
])

const accountInitials = computed(() => {
  const name = customerName.value
  if (!name) return ''
  const parts = name.split(' ').filter(Boolean)
  if (!parts.length) return ''
  return parts.slice(0, 2).map(p => p[0]?.toUpperCase() || '').join('')
})

const accountMenu = computed<DropdownMenuItem[][]>(() => {
  if (isAuthenticated.value) {
    return [
      [
        {
          label: customerName.value || 'Sua conta',
          slot: 'profile',
          type: 'label'
        }
      ],
      [
        { label: 'Minha conta', icon: 'i-lucide-user', to: '/conta' },
        { label: 'Meus pedidos', icon: 'i-lucide-package', to: '/conta/pedidos' },
        { label: 'Endereços', icon: 'i-lucide-map-pin', to: '/conta/enderecos' }
      ],
      [
        { label: 'Sair', icon: 'i-lucide-log-out', to: '/sair' }
      ]
    ]
  }
  return [[
    { label: 'Entrar', icon: 'i-lucide-log-in', to: '/login' },
    { label: 'Criar conta', icon: 'i-lucide-user-plus', to: '/login?novo=1' }
  ]]
})

const cartCount = computed(() => cart.value.items_count || 0)

const statusLabel = computed(() => {
  const status = shopStatus.value
  if (!status?.message) return ''
  return status.message
})
</script>

<template>
  <UHeader :to="'/'" :title="shop?.brand_name || 'Shopman'">
    <UNavigationMenu :items="navItems" variant="link" highlight class="hidden lg:flex" />

    <template #right>
      <UButton
        to="/cart"
        color="neutral"
        variant="ghost"
        icon="i-lucide-shopping-bag"
        :badge="cartCount || undefined"
        aria-label="Ver carrinho"
      />

      <UDropdownMenu :items="accountMenu" :ui="{ content: 'min-w-56' }">
        <UButton
          color="neutral"
          variant="ghost"
          :icon="isAuthenticated ? undefined : 'i-lucide-user'"
          :aria-label="isAuthenticated ? `Menu da conta de ${customerName}` : 'Entrar ou criar conta'"
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
              <p class="text-sm font-semibold text-highlighted truncate">{{ customerName }}</p>
              <p class="text-sm text-muted">Cliente da casa</p>
            </div>
          </div>
        </template>
      </UDropdownMenu>
    </template>

    <template #body>
      <div v-if="statusLabel" class="mb-4 rounded-lg bg-elevated/50 px-3 py-2 text-sm text-muted">
        {{ statusLabel }}
      </div>
      <UNavigationMenu :items="navItems" orientation="vertical" class="-mx-2.5" />
      <USeparator class="my-4" />
      <div v-if="!cart.is_empty" class="text-center text-sm text-muted">
        {{ cart.items_count === 1 ? '1 item' : `${cart.items_count} itens` }} · {{ cart.grand_total_display }}
      </div>
    </template>
  </UHeader>
</template>
