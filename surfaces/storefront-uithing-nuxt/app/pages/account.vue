<script setup lang="ts">
import type { AuthSessionResponse, SavedAddressProjection, SurfaceActionProjection } from '~/types/shopman'

type OrderFilter = 'todos' | 'ativos' | 'anteriores'
type AddressMode = 'create' | 'edit'

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

interface AccountDeviceProjection {
  id: string
  label: string
  created_at: string | null
  created_at_display: string
  last_used_at: string | null
  last_used_at_display: string
  location: string
  is_current: boolean
}

interface AccountDeviceResponse {
  devices: AccountDeviceProjection[]
}

type RevokeDeviceMode = 'one' | 'all'

const apiPath = useShopmanApiPath()
const csrfHeaders = useShopmanCsrfHeaders()
const session = useShopSession()
const { performAction, conflict, pending: reorderPending } = useReorder()
const requestHeaders = import.meta.server ? useRequestHeaders(['cookie']) : undefined

const activeTab = ref('overview')
const orderFilter = ref<OrderFilter>('todos')
const preferencePending = ref<Record<string, boolean>>({})
const deviceIssue = ref('')
const revokeDeviceOpen = ref(false)
const revokeDeviceMode = ref<RevokeDeviceMode>('one')
const revokeDeviceCandidate = ref<AccountDeviceProjection | null>(null)
const revokeDevicePending = ref(false)
const addressSheetOpen = ref(false)
const addressMode = ref<AddressMode>('create')
const addressEditingId = ref<number | null>(null)
const addressOriginalFormatted = ref('')
const addressPending = ref(false)
const addressIssue = ref('')
const addressForm = reactive({
  label: 'home',
  label_custom: '',
  formatted_address: '',
  complement: '',
  delivery_instructions: '',
  is_default: false
})

const { data: auth } = await useFetch<AuthSessionResponse>(apiPath('/api/auth/session/'), {
  credentials: 'include',
  headers: requestHeaders
})

watch(() => auth.value, value => {
  session.setFromAuthSession(value)
}, { immediate: true })

watch(() => auth.value?.is_authenticated, isAuthenticated => {
  if (isAuthenticated === false && import.meta.client) {
    void navigateTo('/login?next=/account')
  }
}, { immediate: true })

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

const { data: addresses, pending: addressesPending, refresh: refreshAddresses } = await useFetch<SavedAddressProjection[]>(apiPath('/api/v1/account/addresses/'), {
  credentials: 'include',
  headers: requestHeaders,
  immediate: !!auth.value?.is_authenticated
})

const { data: devicesResponse, pending: devicesPending, refresh: refreshDevices } = await useFetch<AccountDeviceResponse>(apiPath('/api/v1/account/devices/'), {
  credentials: 'include',
  headers: requestHeaders,
  immediate: !!auth.value?.is_authenticated
})

const accountDevices = computed(() => devicesResponse.value?.devices || [])
const addressSheetTitle = computed(() => addressMode.value === 'create' ? 'Adicionar endereço' : 'Editar endereço')
const addressSheetDescription = computed(() => addressMode.value === 'create'
  ? 'Informe o local de entrega uma vez. Na próxima compra ele aparece pronto.'
  : 'Ajuste o que mudou e salve para os próximos pedidos.'
)
const accountTabsRootClass = 'gap-0'
const accountTabsPanelClass = 'gap-0 overflow-hidden py-0'
const accountTabsHeaderClass = 'after:bg-border relative gap-0 bg-card px-4 py-1.5 sm:px-6 after:absolute after:inset-x-0 after:bottom-0 after:h-px'
const accountTabsListClass = 'no-scrollbar h-auto w-full justify-start gap-1.5 overflow-x-auto rounded-none bg-transparent p-0'
const accountTabsTriggerClass = 'min-w-max rounded-md px-3 py-1.5 data-[state=active]:bg-muted data-[state=active]:text-foreground data-[state=active]:shadow-none'
const accountTabsContentClass = 'm-0'

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

function deviceIcon (label: string) {
  const normalized = label.toLowerCase()
  if (normalized.includes('iphone') || normalized.includes('android')) return 'lucide:smartphone'
  if (normalized.includes('mac') || normalized.includes('windows')) return 'lucide:laptop'
  return 'lucide:monitor'
}

function resetAddressForm () {
  addressForm.label = 'home'
  addressForm.label_custom = ''
  addressForm.formatted_address = ''
  addressForm.complement = ''
  addressForm.delivery_instructions = ''
  addressForm.is_default = !(addresses.value || []).length
  addressEditingId.value = null
  addressOriginalFormatted.value = ''
  addressIssue.value = ''
}

function openCreateAddress () {
  addressMode.value = 'create'
  resetAddressForm()
  addressSheetOpen.value = true
}

function openEditAddress (address: SavedAddressProjection) {
  addressMode.value = 'edit'
  addressEditingId.value = address.id
  addressOriginalFormatted.value = address.formatted_address || ''
  addressForm.label = address.label_key || 'home'
  addressForm.label_custom = address.label_custom || ''
  addressForm.formatted_address = address.formatted_address || ''
  addressForm.complement = address.complement || ''
  addressForm.delivery_instructions = address.delivery_instructions || ''
  addressForm.is_default = !!address.is_default
  addressIssue.value = ''
  addressSheetOpen.value = true
}

function addressPayload () {
  const formattedAddress = addressForm.formatted_address.trim()
  const payload: Record<string, unknown> = {
    label: addressForm.label,
    label_custom: addressForm.label === 'other' ? addressForm.label_custom.trim() : '',
    formatted_address: formattedAddress,
    complement: addressForm.complement.trim(),
    delivery_instructions: addressForm.delivery_instructions.trim(),
    is_default: addressForm.is_default
  }
  if (addressMode.value === 'create' || formattedAddress !== addressOriginalFormatted.value.trim()) {
    payload.place_id = null
  }
  return payload
}

async function saveAddress () {
  if (addressPending.value) return
  if (!addressForm.formatted_address.trim()) {
    addressIssue.value = 'Informe o endereço.'
    return
  }
  if (addressForm.label === 'other' && !addressForm.label_custom.trim()) {
    addressIssue.value = 'Dê um nome para este endereço.'
    return
  }

  addressPending.value = true
  addressIssue.value = ''
  try {
    const body = addressPayload()
    if (addressMode.value === 'edit' && addressEditingId.value) {
      await $fetch(apiPath(`/api/v1/account/addresses/${encodeURIComponent(addressEditingId.value)}/`), {
        method: 'PATCH',
        headers: await csrfHeaders(),
        credentials: 'include',
        body
      })
    } else {
      await $fetch(apiPath('/api/v1/account/addresses/'), {
        method: 'POST',
        headers: await csrfHeaders(),
        credentials: 'include',
        body
      })
    }
    await refreshAddresses()
    addressSheetOpen.value = false
  } catch (e: any) {
    addressIssue.value = e?.data?.detail || 'Não foi possível salvar o endereço agora.'
  } finally {
    addressPending.value = false
  }
}

function askRevokeDevice (device: AccountDeviceProjection) {
  revokeDeviceMode.value = 'one'
  revokeDeviceCandidate.value = device
  deviceIssue.value = ''
  revokeDeviceOpen.value = true
}

function askRevokeAllDevices () {
  revokeDeviceMode.value = 'all'
  revokeDeviceCandidate.value = null
  deviceIssue.value = ''
  revokeDeviceOpen.value = true
}

async function confirmRevokeDevice () {
  if (revokeDevicePending.value) return
  revokeDevicePending.value = true
  deviceIssue.value = ''
  try {
    if (revokeDeviceMode.value === 'all') {
      await $fetch(apiPath('/api/v1/account/devices/'), {
        method: 'DELETE',
        headers: await csrfHeaders(),
        credentials: 'include'
      })
    } else if (revokeDeviceCandidate.value) {
      await $fetch(apiPath(`/api/v1/account/devices/${encodeURIComponent(revokeDeviceCandidate.value.id)}/`), {
        method: 'DELETE',
        headers: await csrfHeaders(),
        credentials: 'include'
      })
    }
    await refreshDevices()
    revokeDeviceOpen.value = false
  } catch (e: any) {
    deviceIssue.value = e?.data?.detail || 'Não foi possível remover o aparelho agora.'
  } finally {
    revokeDevicePending.value = false
  }
}

useSeoMeta({
  title: 'Conta'
})
</script>

<template>
  <main class="shop-section">
    <div class="shop-container space-y-5">
      <UiBreadcrumbs
        :items="[
          { label: 'Início', link: '/' },
          { label: 'Conta' }
        ]"
      />

      <div class="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p class="shop-kicker">Conta</p>
          <h1 class="mt-1 text-3xl font-semibold">Histórico, endereços e recompra</h1>
        </div>
        <UiButton variant="outline" icon="lucide:log-out" @click="logout">Sair</UiButton>
      </div>

      <UiAlert v-if="auth?.is_authenticated === false" variant="warning">
        <UiAlertTitle>Entre para ver sua conta</UiAlertTitle>
        <UiAlertDescription>
          <UiButton to="/login?next=/account" class="mt-2">Entrar por telefone</UiButton>
        </UiAlertDescription>
      </UiAlert>

      <UiTabs v-else v-model="activeTab" :class="accountTabsRootClass">
        <UiCard :class="accountTabsPanelClass">
          <UiCardHeader :class="accountTabsHeaderClass">
            <UiTabsList :class="accountTabsListClass">
              <UiTabsTrigger value="overview" :class="accountTabsTriggerClass">Resumo</UiTabsTrigger>
              <UiTabsTrigger value="orders" :class="accountTabsTriggerClass">Pedidos</UiTabsTrigger>
              <UiTabsTrigger value="addresses" :class="accountTabsTriggerClass">Endereços</UiTabsTrigger>
              <UiTabsTrigger value="preferences" :class="accountTabsTriggerClass">Preferências</UiTabsTrigger>
              <UiTabsTrigger value="devices" :class="accountTabsTriggerClass">Aparelhos</UiTabsTrigger>
            </UiTabsList>
          </UiCardHeader>

          <UiCardContent class="px-4 py-4 sm:px-6">
            <UiTabsContent value="overview" :class="accountTabsContentClass">
              <div class="grid grid-cols-1 gap-4 lg:grid-cols-3">
                <section class="space-y-3 lg:col-span-2">
                  <div>
                    <h2 class="text-lg font-semibold">{{ summary?.customer_first_name || session.customerName.value || 'Cliente' }}</h2>
                    <p class="text-sm text-muted-foreground">
                      {{ summaryPending ? 'Carregando...' : formatCount(summary?.recent_order_count || 0, 'pedido recente', 'pedidos recentes') }}
                    </p>
                  </div>
                  <div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
                    <div class="rounded-lg border bg-background p-3">
                      <p class="text-sm text-muted-foreground">Ativos</p>
                      <p class="text-2xl font-semibold">{{ summary?.active_order_count || 0 }}</p>
                    </div>
                    <div class="rounded-lg border bg-background p-3">
                      <p class="text-sm text-muted-foreground">Histórico</p>
                      <p class="text-2xl font-semibold">{{ summary?.recent_order_count || 0 }}</p>
                    </div>
                    <div class="rounded-lg border bg-background p-3">
                      <p class="text-sm text-muted-foreground">Pontos</p>
                      <p class="text-2xl font-semibold">{{ summary?.loyalty?.points_balance || 0 }}</p>
                    </div>
                  </div>
                </section>

                <UiItem v-if="summary?.last_order" variant="outline" class="bg-background lg:self-start">
                  <UiItemContent>
                    <UiItemTitle>Último pedido</UiItemTitle>
                    <UiItemDescription>{{ summary.last_order.created_at_display }}</UiItemDescription>
                    <p class="mt-2 font-medium">{{ summary.last_order.total_display }}</p>
                    <p class="text-sm text-muted-foreground">{{ summary.last_order.status_label }}</p>
                  </UiItemContent>
                  <UiItemActions>
                    <UiButton
                      v-if="summary.last_order.actions?.[0]"
                      :loading="!!reorderPending[summary.last_order.ref]"
                      @click="performAction(summary.last_order.actions[0])"
                    >
                      Refazer
                    </UiButton>
                  </UiItemActions>
                </UiItem>
              </div>
            </UiTabsContent>

            <UiTabsContent value="orders" :class="accountTabsContentClass">
              <section class="space-y-4">
                <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <h2 class="text-lg font-semibold">Pedidos</h2>
                    <p class="text-sm text-muted-foreground">
                      {{ ordersPending ? 'Carregando...' : formatCount(orders?.length || 0, 'pedido', 'pedidos') }}
                    </p>
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
                <UiSkeleton v-if="ordersPending" class="h-32 rounded-lg" />
                <UiItemGroup v-else class="gap-3">
                  <UiItem v-for="order in orders || []" :key="order.ref" variant="outline" class="bg-background">
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
                </UiItemGroup>
              </section>
            </UiTabsContent>

            <UiTabsContent value="addresses" :class="accountTabsContentClass">
              <section class="space-y-4">
                <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <h2 class="text-lg font-semibold">Endereços</h2>
                    <p class="text-sm text-muted-foreground">
                      {{ addressesPending ? 'Carregando...' : formatCount(addresses?.length || 0, 'endereço salvo', 'endereços salvos') }}
                    </p>
                  </div>
                  <UiButton icon="lucide:plus" @click="openCreateAddress">Adicionar endereço</UiButton>
                </div>

                <UiSkeleton v-if="addressesPending" class="h-32 rounded-lg" />
                <UiEmpty v-else-if="!(addresses || []).length" class="border">
                  <UiEmptyMedia variant="icon">
                    <Icon name="lucide:map-pin" />
                  </UiEmptyMedia>
                  <UiEmptyHeader>
                    <UiEmptyTitle>Nenhum endereço salvo</UiEmptyTitle>
                    <UiEmptyDescription>Adicione um endereço para finalizar a próxima entrega com menos passos.</UiEmptyDescription>
                  </UiEmptyHeader>
                  <div class="flex justify-center">
                    <UiButton icon="lucide:plus" @click="openCreateAddress">Adicionar endereço</UiButton>
                  </div>
                </UiEmpty>

                <UiItemGroup v-else class="grid grid-cols-1 gap-3 md:grid-cols-2">
                  <UiItem v-for="address in addresses || []" :key="address.id" variant="outline" class="bg-background">
                    <UiItemMedia variant="icon" class="size-10 rounded-md">
                      <Icon name="lucide:map-pin" />
                    </UiItemMedia>
                    <UiItemContent>
                      <UiItemTitle>
                        {{ address.label }}
                        <UiBadge v-if="address.is_default" variant="secondary">Padrão</UiBadge>
                      </UiItemTitle>
                      <UiItemDescription>
                        {{ address.formatted_address }}
                        <span v-if="address.complement"> · {{ address.complement }}</span>
                      </UiItemDescription>
                    </UiItemContent>
                    <UiItemActions>
                      <UiButton variant="ghost" size="sm" icon="lucide:pencil" @click="openEditAddress(address)">
                        Editar
                      </UiButton>
                    </UiItemActions>
                  </UiItem>
                </UiItemGroup>
              </section>
            </UiTabsContent>

            <UiTabsContent value="preferences" :class="accountTabsContentClass">
              <div class="grid grid-cols-1 gap-4 lg:grid-cols-2">
                <UiFieldSet class="rounded-lg border bg-background p-4">
                  <UiFieldLegend>Preferências alimentares</UiFieldLegend>
                  <UiFieldGroup>
                    <UiField
                      v-for="pref in summary?.food_preferences || []"
                      :key="pref.key"
                      orientation="horizontal"
                    >
                      <UiFieldContent>
                        <UiFieldLabel :for="`food-pref-${pref.key}`">{{ pref.label }}</UiFieldLabel>
                      </UiFieldContent>
                      <UiSwitch
                        :id="`food-pref-${pref.key}`"
                        :checked="pref.is_active"
                        :disabled="!!preferencePending[pref.key]"
                        @update:checked="toggleFood(pref)"
                      />
                    </UiField>
                  </UiFieldGroup>
                </UiFieldSet>
                <UiFieldSet class="rounded-lg border bg-background p-4">
                  <UiFieldLegend>Notificações</UiFieldLegend>
                  <UiFieldGroup>
                    <UiField
                      v-for="pref in summary?.notification_preferences || []"
                      :key="pref.key"
                      orientation="horizontal"
                    >
                      <UiFieldContent>
                        <UiFieldLabel :for="`notification-pref-${pref.key}`">{{ pref.label }}</UiFieldLabel>
                        <UiFieldDescription>{{ pref.description }}</UiFieldDescription>
                      </UiFieldContent>
                      <UiSwitch
                        :id="`notification-pref-${pref.key}`"
                        :checked="pref.enabled"
                        :disabled="!!preferencePending[pref.key]"
                        @update:checked="toggleNotification(pref)"
                      />
                    </UiField>
                  </UiFieldGroup>
                </UiFieldSet>
              </div>
            </UiTabsContent>

            <UiTabsContent value="devices" :class="accountTabsContentClass">
              <section class="space-y-4">
                <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <h2 class="text-lg font-semibold">Aparelhos confiáveis</h2>
                    <p class="text-sm text-muted-foreground">
                      {{ devicesPending ? 'Carregando...' : formatCount(accountDevices.length, 'aparelho autorizado', 'aparelhos autorizados') }}
                    </p>
                  </div>
                  <UiButton
                    v-if="accountDevices.length > 1"
                    variant="outline"
                    size="sm"
                    icon="lucide:shield-x"
                    @click="askRevokeAllDevices"
                  >
                    Remover todos
                  </UiButton>
                </div>

                <UiAlert v-if="deviceIssue" variant="destructive">
                  <UiAlertTitle>Não foi possível atualizar</UiAlertTitle>
                  <UiAlertDescription>{{ deviceIssue }}</UiAlertDescription>
                </UiAlert>

                <UiSkeleton v-if="devicesPending" class="h-32 rounded-lg" />

                <UiEmpty v-else-if="!accountDevices.length" class="border">
                  <UiEmptyMedia variant="icon">
                    <Icon name="lucide:monitor" />
                  </UiEmptyMedia>
                  <UiEmptyHeader>
                    <UiEmptyTitle>Nenhum aparelho confiável</UiEmptyTitle>
                    <UiEmptyDescription>Quando você optar por confiar neste aparelho no login, ele aparecerá aqui.</UiEmptyDescription>
                  </UiEmptyHeader>
                </UiEmpty>

                <UiItemGroup v-else class="gap-3">
                  <UiItem v-for="device in accountDevices" :key="device.id" variant="outline" class="bg-background">
                    <UiItemMedia variant="icon" class="size-10 rounded-md">
                      <Icon :name="deviceIcon(device.label)" />
                    </UiItemMedia>
                    <UiItemContent>
                      <UiItemTitle>
                        {{ device.label || 'Dispositivo' }}
                        <UiBadge v-if="device.is_current" variant="secondary">Atual</UiBadge>
                      </UiItemTitle>
                      <UiItemDescription>
                        <span>{{ device.last_used_at_display }}</span>
                        <span v-if="device.location"> · {{ device.location }}</span>
                        <span> · Registrado em {{ device.created_at_display }}</span>
                      </UiItemDescription>
                    </UiItemContent>
                    <UiItemActions>
                      <UiButton variant="ghost" size="sm" icon="lucide:shield-x" @click="askRevokeDevice(device)">
                        Remover
                      </UiButton>
                    </UiItemActions>
                  </UiItem>
                </UiItemGroup>
              </section>
            </UiTabsContent>
          </UiCardContent>
        </UiCard>
      </UiTabs>

      <UiSheet v-model:open="addressSheetOpen">
        <UiSheetContent side="bottom" variant="floating" class="mx-auto max-h-[90dvh] max-w-2xl overflow-y-auto">
          <UiSheetHeader>
            <UiSheetTitle>{{ addressSheetTitle }}</UiSheetTitle>
            <UiSheetDescription>{{ addressSheetDescription }}</UiSheetDescription>
          </UiSheetHeader>

          <form class="space-y-4 px-4 pb-4" @submit.prevent="saveAddress">
            <UiAlert v-if="addressIssue" variant="destructive">
              <UiAlertTitle>Revise o endereço</UiAlertTitle>
              <UiAlertDescription>{{ addressIssue }}</UiAlertDescription>
            </UiAlert>

            <div class="grid grid-cols-1 gap-4 sm:grid-cols-[180px_minmax(0,1fr)]">
              <UiField>
                <UiFieldLabel for="account-address-label">Tipo</UiFieldLabel>
                <UiSelect v-model="addressForm.label">
                  <UiSelectTrigger id="account-address-label" />
                  <UiSelectContent>
                    <UiSelectItem value="home">Casa</UiSelectItem>
                    <UiSelectItem value="work">Trabalho</UiSelectItem>
                    <UiSelectItem value="other">Outro</UiSelectItem>
                  </UiSelectContent>
                </UiSelect>
              </UiField>

              <UiField v-if="addressForm.label === 'other'">
                <UiFieldLabel for="account-address-label-custom">Nome do endereço</UiFieldLabel>
                <UiInput id="account-address-label-custom" v-model="addressForm.label_custom" placeholder="Ex: Casa da mãe" />
              </UiField>
            </div>

            <UiField>
              <UiFieldLabel for="account-address-formatted">Endereço</UiFieldLabel>
              <UiTextarea
                id="account-address-formatted"
                v-model="addressForm.formatted_address"
                :rows="3"
                placeholder="Rua, número, bairro, cidade"
                required
              />
              <UiFieldDescription>Use o endereço completo para evitar confirmação manual no checkout.</UiFieldDescription>
            </UiField>

            <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <UiField>
                <UiFieldLabel for="account-address-complement">Complemento</UiFieldLabel>
                <UiInput id="account-address-complement" v-model="addressForm.complement" placeholder="Apto, bloco, referência" />
              </UiField>
              <UiField>
                <UiFieldLabel for="account-address-instructions">Instruções de entrega</UiFieldLabel>
                <UiInput id="account-address-instructions" v-model="addressForm.delivery_instructions" placeholder="Portaria, interfone, melhor acesso" />
              </UiField>
            </div>

            <UiField orientation="horizontal">
              <UiFieldContent>
                <UiFieldLabel for="account-address-default">Usar como padrão</UiFieldLabel>
                <UiFieldDescription>Este endereço aparece primeiro na próxima compra.</UiFieldDescription>
              </UiFieldContent>
              <UiSwitch id="account-address-default" v-model:checked="addressForm.is_default" />
            </UiField>

            <UiSheetFooter class="px-0">
              <UiButton type="button" variant="ghost" :disabled="addressPending" @click="addressSheetOpen = false">Cancelar</UiButton>
              <UiButton type="submit" :loading="addressPending" icon="lucide:check">
                {{ addressMode === 'create' ? 'Salvar endereço' : 'Salvar alterações' }}
              </UiButton>
            </UiSheetFooter>
          </form>
        </UiSheetContent>
      </UiSheet>

      <UiAlertDialog :open="!!conflict" @update:open="open => { if (!open) dismissConflict() }">
        <UiAlertDialogContent>
          <UiAlertDialogHeader>
            <UiAlertDialogTitle>{{ conflict?.copy.title.title || 'Carrinho já tem itens' }}</UiAlertDialogTitle>
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

      <UiAlertDialog v-model:open="revokeDeviceOpen">
        <UiAlertDialogContent>
          <UiAlertDialogHeader>
            <UiAlertDialogTitle>
              {{ revokeDeviceMode === 'all' ? 'Remover todos os aparelhos?' : 'Remover aparelho?' }}
            </UiAlertDialogTitle>
            <UiAlertDialogDescription>
              {{ revokeDeviceMode === 'all'
                ? 'Você precisará confirmar o telefone novamente nos próximos acessos.'
                : `Você precisará confirmar o telefone novamente neste aparelho: ${revokeDeviceCandidate?.label || 'Dispositivo'}.` }}
            </UiAlertDialogDescription>
          </UiAlertDialogHeader>
          <UiAlertDialogFooter>
            <UiAlertDialogCancel :disabled="revokeDevicePending">Cancelar</UiAlertDialogCancel>
            <UiAlertDialogAction variant="destructive" :disabled="revokeDevicePending" @click="confirmRevokeDevice">
              Remover
            </UiAlertDialogAction>
          </UiAlertDialogFooter>
        </UiAlertDialogContent>
      </UiAlertDialog>
    </div>
  </main>
</template>
