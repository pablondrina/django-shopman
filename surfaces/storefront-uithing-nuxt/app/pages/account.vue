<script setup lang="ts">
import type { AuthSessionResponse, SavedAddressProjection, SurfaceActionProjection } from '~/types/shopman'

type OrderFilter = 'todos' | 'ativos' | 'anteriores'

interface AccountSummary {
  customer_first_name: string
  recent_order_count: number
  active_order_count: number
  last_order: {
    ref: string
    created_at_display: string
    total_display: string
    status_label: string
    item_count: number
    actions?: SurfaceActionProjection[]
  } | null
  loyalty: {
    tier_display: string
    points_balance: number
    stamps_current: number
    stamps_target: number
    stamps_range: number[]
    transactions: Array<{ points: number, description: string, date_display: string, is_credit: boolean }>
  } | null
  food_preferences: Array<{ key: string, label: string, is_active: boolean }>
  notification_preferences: Array<{ key: string, label: string, description: string, enabled: boolean }>
}

interface OrderItem {
  ref: string
  status: string
  status_label: string
  total_display: string
  item_count?: number
  created_at_display?: string
  actions?: SurfaceActionProjection[]
}

const apiPath = useShopmanApiPath()
const csrfHeaders = useShopmanCsrfHeaders()
const session = useShopSession()
const { performAction, conflict, pending: reorderPending } = useReorder()
const requestHeaders = import.meta.server ? useRequestHeaders(['cookie']) : undefined

const activeTab = ref('overview')
const orderFilter = ref<OrderFilter>('todos')
const preferencePending = ref<Record<string, boolean>>({})

const { data: auth } = await useFetch<AuthSessionResponse>(apiPath('/api/auth/session/'), {
  credentials: 'include',
  headers: requestHeaders
})
session.setFromAuthSession(auth.value)

watchEffect(() => {
  if (auth.value?.is_authenticated === false && import.meta.client) {
    void navigateTo('/login?next=/account')
  }
})

const { data: summary, pending: summaryPending, refresh: refreshSummary } = await useFetch<AccountSummary>(apiPath('/api/v1/account/summary/'), {
  credentials: 'include',
  headers: requestHeaders,
  immediate: !!auth.value?.is_authenticated
})

const { data: orders, pending: ordersPending, refresh: refreshOrders } = await useFetch<OrderItem[]>(apiPath('/api/v1/account/orders/'), {
  credentials: 'include',
  headers: requestHeaders,
  query: computed(() => ({ filter: orderFilter.value })),
  immediate: !!auth.value?.is_authenticated
})

const { data: addresses, pending: addressesPending } = await useFetch<SavedAddressProjection[]>(apiPath('/api/v1/account/addresses/'), {
  credentials: 'include',
  headers: requestHeaders,
  immediate: !!auth.value?.is_authenticated
})

async function toggleFood (pref: { key: string, is_active: boolean }) {
  preferencePending.value = { ...preferencePending.value, [pref.key]: true }
  try {
    await $fetch(apiPath('/api/v1/account/preferences/food/'), {
      method: 'POST',
      headers: await csrfHeaders(),
      credentials: 'include',
      body: { key: pref.key, enabled: !pref.is_active }
    })
    await refreshSummary()
  } finally {
    const next = { ...preferencePending.value }
    delete next[pref.key]
    preferencePending.value = next
  }
}

async function toggleNotification (pref: { key: string, enabled: boolean }) {
  preferencePending.value = { ...preferencePending.value, [pref.key]: true }
  try {
    await $fetch(apiPath('/api/v1/account/preferences/notifications/'), {
      method: 'POST',
      headers: await csrfHeaders(),
      credentials: 'include',
      body: { channel: pref.key, enabled: !pref.enabled }
    })
    await refreshSummary()
  } finally {
    const next = { ...preferencePending.value }
    delete next[pref.key]
    preferencePending.value = next
  }
}

function dismissConflict () {
  conflict.value = null
}

async function logout () {
  await $fetch(apiPath('/api/auth/logout/'), {
    method: 'POST',
    headers: await csrfHeaders(),
    credentials: 'include'
  })
  session.reset()
  await navigateTo('/')
}

function reorderAction (order: OrderItem) {
  return order.actions?.find(action => action.ref === 'reorder' && action.enabled) || null
}

useSeoMeta({
  title: 'Conta'
})
</script>

<template>
  <main class="shop-section">
    <div class="shop-container space-y-5">
      <div class="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p class="shop-kicker">Conta</p>
          <h1 class="mt-1 text-3xl font-semibold">Historico, enderecos e recompra</h1>
        </div>
        <UiButton variant="outline" icon="lucide:log-out" @click="logout">Sair</UiButton>
      </div>

      <UiAlert v-if="auth?.is_authenticated === false" variant="warning">
        <UiAlertTitle>Entre para ver sua conta</UiAlertTitle>
        <UiAlertDescription>
          <UiButton to="/login?next=/account" class="mt-2">Entrar por telefone</UiButton>
        </UiAlertDescription>
      </UiAlert>

      <UiTabs v-else v-model="activeTab">
        <UiTabsList class="no-scrollbar overflow-x-auto">
          <UiTabsTrigger value="overview">Resumo</UiTabsTrigger>
          <UiTabsTrigger value="orders">Pedidos</UiTabsTrigger>
          <UiTabsTrigger value="addresses">Enderecos</UiTabsTrigger>
          <UiTabsTrigger value="preferences">Preferencias</UiTabsTrigger>
        </UiTabsList>

        <UiTabsContent value="overview">
          <div class="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <UiCard class="lg:col-span-2">
              <UiCardHeader>
                <UiCardTitle>{{ summary?.customer_first_name || session.customerName.value || 'Cliente' }}</UiCardTitle>
                <UiCardDescription>{{ summaryPending ? 'Carregando...' : formatCount(summary?.recent_order_count || 0, 'pedido recente', 'pedidos recentes') }}</UiCardDescription>
              </UiCardHeader>
              <UiCardContent class="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <div class="rounded-lg border p-3">
                  <p class="text-sm text-muted-foreground">Ativos</p>
                  <p class="text-2xl font-semibold">{{ summary?.active_order_count || 0 }}</p>
                </div>
                <div class="rounded-lg border p-3">
                  <p class="text-sm text-muted-foreground">Historico</p>
                  <p class="text-2xl font-semibold">{{ summary?.recent_order_count || 0 }}</p>
                </div>
                <div class="rounded-lg border p-3">
                  <p class="text-sm text-muted-foreground">Pontos</p>
                  <p class="text-2xl font-semibold">{{ summary?.loyalty?.points_balance || 0 }}</p>
                </div>
              </UiCardContent>
            </UiCard>

            <UiCard v-if="summary?.last_order">
              <UiCardHeader>
                <UiCardTitle>Ultimo pedido</UiCardTitle>
                <UiCardDescription>{{ summary.last_order.created_at_display }}</UiCardDescription>
              </UiCardHeader>
              <UiCardContent class="space-y-2">
                <p class="font-medium">{{ summary.last_order.total_display }}</p>
                <p class="text-sm text-muted-foreground">{{ summary.last_order.status_label }}</p>
              </UiCardContent>
              <UiCardFooter>
                <UiButton
                  v-if="summary.last_order.actions?.[0]"
                  :loading="!!reorderPending[summary.last_order.ref]"
                  @click="performAction(summary.last_order.actions[0])"
                >
                  Refazer
                </UiButton>
              </UiCardFooter>
            </UiCard>
          </div>
        </UiTabsContent>

        <UiTabsContent value="orders">
          <UiCard>
            <UiCardHeader>
              <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <UiCardTitle>Pedidos</UiCardTitle>
                  <UiCardDescription>{{ ordersPending ? 'Carregando...' : formatCount(orders?.length || 0, 'pedido', 'pedidos') }}</UiCardDescription>
                </div>
                <UiSelect v-model="orderFilter">
                  <UiSelectTrigger class="w-44" />
                  <UiSelectContent>
                    <UiSelectItem value="todos">Todos</UiSelectItem>
                    <UiSelectItem value="ativos">Em andamento</UiSelectItem>
                    <UiSelectItem value="anteriores">Finalizados</UiSelectItem>
                  </UiSelectContent>
                </UiSelect>
              </div>
            </UiCardHeader>
            <UiCardContent class="space-y-3">
              <UiSkeleton v-if="ordersPending" class="h-32 rounded-lg" />
              <UiItem v-for="order in orders || []" v-else :key="order.ref" class="rounded-lg border p-3">
                <UiItemContent>
                  <UiItemTitle>{{ order.ref }}</UiItemTitle>
                  <UiItemDescription>{{ order.status_label }} · {{ order.created_at_display }}</UiItemDescription>
                </UiItemContent>
                <UiItemActions class="flex gap-2">
                  <UiButton :to="orderTrackingRoute(order.ref)" variant="outline" size="sm">Acompanhar</UiButton>
                  <UiButton
                    v-if="reorderAction(order)"
                    size="sm"
                    :loading="!!reorderPending[order.ref]"
                    @click="performAction(reorderAction(order)!)"
                  >
                    Refazer
                  </UiButton>
                </UiItemActions>
              </UiItem>
            </UiCardContent>
          </UiCard>
        </UiTabsContent>

        <UiTabsContent value="addresses">
          <UiCard>
            <UiCardHeader>
              <UiCardTitle>Enderecos</UiCardTitle>
              <UiCardDescription>{{ addressesPending ? 'Carregando...' : formatCount(addresses?.length || 0, 'endereco salvo', 'enderecos salvos') }}</UiCardDescription>
            </UiCardHeader>
            <UiCardContent class="grid grid-cols-1 gap-3 md:grid-cols-2">
              <UiItem v-for="address in addresses || []" :key="address.id" class="rounded-lg border p-3">
                <UiItemContent>
                  <UiItemTitle>{{ address.label }}</UiItemTitle>
                  <UiItemDescription>{{ address.formatted_address }}</UiItemDescription>
                </UiItemContent>
                <UiItemActions>
                  <UiBadge v-if="address.is_default" variant="success">Padrao</UiBadge>
                </UiItemActions>
              </UiItem>
            </UiCardContent>
          </UiCard>
        </UiTabsContent>

        <UiTabsContent value="preferences">
          <div class="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <UiCard>
              <UiCardHeader>
                <UiCardTitle>Preferencias alimentares</UiCardTitle>
              </UiCardHeader>
              <UiCardContent class="space-y-3">
                <label v-for="pref in summary?.food_preferences || []" :key="pref.key" class="flex items-center justify-between rounded-lg border p-3">
                  <span>{{ pref.label }}</span>
                  <UiSwitch :checked="pref.is_active" :disabled="!!preferencePending[pref.key]" @update:checked="toggleFood(pref)" />
                </label>
              </UiCardContent>
            </UiCard>
            <UiCard>
              <UiCardHeader>
                <UiCardTitle>Notificacoes</UiCardTitle>
              </UiCardHeader>
              <UiCardContent class="space-y-3">
                <label v-for="pref in summary?.notification_preferences || []" :key="pref.key" class="flex items-center justify-between gap-3 rounded-lg border p-3">
                  <span>
                    <span class="block font-medium">{{ pref.label }}</span>
                    <span class="block text-sm text-muted-foreground">{{ pref.description }}</span>
                  </span>
                  <UiSwitch :checked="pref.enabled" :disabled="!!preferencePending[pref.key]" @update:checked="toggleNotification(pref)" />
                </label>
              </UiCardContent>
            </UiCard>
          </div>
        </UiTabsContent>
      </UiTabs>

      <UiAlertDialog :open="!!conflict" @update:open="open => { if (!open) dismissConflict() }">
        <UiAlertDialogContent>
          <UiAlertDialogHeader>
            <UiAlertDialogTitle>{{ conflict?.copy.title.title || 'Carrinho ja tem itens' }}</UiAlertDialogTitle>
            <UiAlertDialogDescription>{{ conflict?.copy.message.message || conflict?.detail }}</UiAlertDialogDescription>
          </UiAlertDialogHeader>
          <UiAlertDialogFooter>
            <UiAlertDialogCancel>Cancelar</UiAlertDialogCancel>
            <UiAlertDialogAction v-if="conflict" @click="performAction(conflict.actions.find(action => action.ref.includes('replace')) || conflict.actions[0])">
              Substituir
            </UiAlertDialogAction>
          </UiAlertDialogFooter>
        </UiAlertDialogContent>
      </UiAlertDialog>
    </div>
  </main>
</template>
