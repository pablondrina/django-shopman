<script setup lang="ts">
import type { TabsItem } from '@nuxt/ui'
import type { AuthSessionResponse, SurfaceActionProjection } from '~/types/shopman'

type UiColor = 'neutral' | 'primary' | 'success' | 'warning' | 'error' | 'info'
type OrderFilter = 'todos' | 'ativos' | 'anteriores'
type AccountTab = 'profile' | 'orders' | 'addresses' | 'loyalty' | 'preferences' | 'security'

definePageMeta({
  layout: 'default',
  path: '/conta'
})

const route = useRoute()
const router = useRouter()
const apiPath = useShopmanApiPath()
const session = useShopSession()
const { customerName } = session
const { clearCart } = useCartState()
const requestHeaders = import.meta.server ? useRequestHeaders(['cookie']) : undefined
const toast = useToast()

const { data: authSession } = await useFetch<AuthSessionResponse>(apiPath('/api/auth/session/'), {
  credentials: 'include',
  headers: requestHeaders,
  key: 'shopman-account-auth-session'
})

session.setFromAuthSession(authSession.value)

if (!authSession.value?.is_authenticated) {
  await navigateTo('/login?next=/conta')
}

interface AddressItem {
  id: number
  label: string
  formatted_address: string
  is_default: boolean
  complement: string
  delivery_instructions: string
}

interface OrderItem {
  ref: string
  status: string
  status_label: string
  status_color?: string
  total_display: string
  item_count?: number
  created_at?: string
  created_at_display?: string
  actions?: SurfaceActionProjection[]
}

interface LoyaltyTransaction {
  points: number
  description: string
  date_display: string
  is_credit: boolean
}

interface AccountSummary {
  customer_first_name: string
  recent_order_count: number
  active_order_count: number
  last_order: { ref: string, created_at_display: string, total_display: string, status_label: string, item_count: number, actions?: SurfaceActionProjection[] } | null
  loyalty: {
    tier: string
    tier_display: string
    points_balance: number
    stamps_current: number
    stamps_target: number
    stamps_completed: number
    stamps_range: number[]
    transactions: LoyaltyTransaction[]
  } | null
  food_preferences: Array<{ key: string, label: string, is_active: boolean }>
  notification_preferences: Array<{ key: string, label: string, description: string, enabled: boolean }>
}

interface DeviceItem {
  id: string
  label: string
  created_at: string | null
  created_at_display: string
  last_used_at: string | null
  last_used_at_display: string
  location: string
  is_current: boolean
}

interface ProfilePayload {
  ref: string
  name: string
  first_name?: string
  last_name?: string
  phone: string
  email: string
  birthday?: string
}

const profile = ref<ProfilePayload | null>(null)
const addresses = ref<AddressItem[]>([])
const orders = ref<OrderItem[]>([])
const devices = ref<DeviceItem[]>([])
const accountSummary = ref<AccountSummary | null>(null)

const profilePending = ref(true)
const profileSaving = ref(false)
const profileError = ref<string | null>(null)
const addressesPending = ref(true)
const ordersPending = ref(true)
const summaryPending = ref(true)
const devicesPending = ref(true)
const orderFilter = ref<OrderFilter>('todos')

const addressModalOpen = ref(false)
const addressBeingEdited = ref<AddressItem | null>(null)
const deleteModalOpen = ref(false)
const addressToDelete = ref<AddressItem | null>(null)
const deletePending = ref(false)
const prefPending = ref<Record<string, boolean>>({})
const notificationPending = ref<Record<string, boolean>>({})
const devicePending = ref<Record<string, boolean>>({})
const revokeDeviceCandidate = ref<DeviceItem | null>(null)
const revokeDeviceOpen = computed({
  get: () => !!revokeDeviceCandidate.value,
  set: (open) => {
    if (!open) revokeDeviceCandidate.value = null
  }
})
const revokeAllDevicesOpen = ref(false)
const revokeAllDevicesPending = ref(false)
const deleteAccountOpen = ref(false)
const deleteAccountAcknowledged = ref(false)
const deleteAccountPending = ref(false)
const profileForm = reactive({
  first_name: '',
  last_name: '',
  email: '',
  birthday: ''
})

const orderFilterOptions: Array<{ value: OrderFilter, label: string }> = [
  { value: 'todos', label: 'Todos' },
  { value: 'ativos', label: 'Em andamento' },
  { value: 'anteriores', label: 'Finalizados' }
]
const logoutRoute = { path: '/sair', query: { cancel: '/conta' } }
const accountTabValues: AccountTab[] = ['profile', 'orders', 'addresses', 'loyalty', 'preferences', 'security']
const activeTab = ref<AccountTab>(normalizeAccountTab(route.query.tab))

const { performReorderAction, pending: reorderPending } = useReorder()

function normalizeAccountTab (value: unknown): AccountTab {
  const candidate = Array.isArray(value) ? value[0] : value
  return accountTabValues.includes(candidate as AccountTab) ? candidate as AccountTab : 'profile'
}

function openAddressModal (existing: AddressItem | null = null) {
  addressBeingEdited.value = existing
  addressModalOpen.value = true
}

function openDeleteAddress (address: AddressItem) {
  addressToDelete.value = address
  deleteModalOpen.value = true
}

async function confirmDeleteAddress () {
  if (!addressToDelete.value) return
  deletePending.value = true
  try {
    const address = addressToDelete.value
    await $fetch(apiPath(`/api/v1/account/addresses/${address.id}/`), {
      method: 'DELETE',
      credentials: 'include'
    })
    addresses.value = addresses.value.filter(a => a.id !== address.id)
    deleteModalOpen.value = false
    addressToDelete.value = null
    toast.add({ color: 'success', title: 'Endereço removido' })
  } catch (e: any) {
    toast.add({
      color: 'error',
      title: 'Não foi possível remover',
      description: e?.data?.detail || ''
    })
  } finally {
    deletePending.value = false
  }
}

async function setDefaultAddress (address: AddressItem) {
  try {
    await $fetch(apiPath(`/api/v1/account/addresses/${address.id}/`), {
      method: 'POST',
      body: { action: 'default' },
      credentials: 'include'
    })
    await loadAddresses()
    toast.add({ color: 'success', title: 'Endereço padrão atualizado' })
  } catch (e: any) {
    toast.add({
      color: 'error',
      title: 'Não foi possível atualizar',
      description: e?.data?.detail || ''
    })
  }
}

async function onAddressSaved () {
  await loadAddresses()
  toast.add({ color: 'success', title: 'Endereço salvo' })
}

async function reorderById (orderRef: string) {
  const order = orders.value.find(candidate => candidate.ref === orderRef)
  const action = order?.actions?.find(candidate => candidate.ref === 'reorder' && candidate.enabled !== false)
  if (action) await performReorderAction(action, orderRef)
}

function reorderActionForOrder (order: OrderItem): SurfaceActionProjection | null {
  return order.actions?.find(action => action.ref === 'reorder' && action.enabled !== false) || null
}

async function loadProfile () {
  profilePending.value = true
  try {
    const response = await $fetch<ProfilePayload>(apiPath('/api/v1/account/profile/'), { credentials: 'include' })
    profile.value = response
    syncProfileForm(response)
  } catch {
    profile.value = null
  } finally {
    profilePending.value = false
  }
}

function syncProfileForm (next: ProfilePayload | null) {
  const [fallbackFirstName, ...fallbackLastName] = (next?.name || '').trim().split(/\s+/).filter(Boolean)
  profileForm.first_name = next?.first_name || fallbackFirstName || ''
  profileForm.last_name = next?.last_name || fallbackLastName.join(' ')
  profileForm.email = next?.email || ''
  profileForm.birthday = next?.birthday || ''
  profileError.value = null
}

async function saveProfile () {
  profileError.value = null
  if (!profileForm.first_name.trim()) {
    profileError.value = 'Informe seu primeiro nome.'
    return
  }
  profileSaving.value = true
  try {
    const response = await $fetch<ProfilePayload>(apiPath('/api/v1/account/profile/'), {
      method: 'PATCH',
      credentials: 'include',
      body: {
        first_name: profileForm.first_name.trim(),
        last_name: profileForm.last_name.trim(),
        email: profileForm.email.trim(),
        birthday: profileForm.birthday
      }
    })
    profile.value = response
    syncProfileForm(response)
    session.setIdentity({ name: response.name, phone: response.phone, isAuthenticated: true })
    await loadAccountSummary()
    await refreshNuxtData('shopman-auth-session')
    await refreshNuxtData('shopman-shell-home')
    toast.add({ color: 'success', title: 'Perfil atualizado' })
  } catch (e: any) {
    profileError.value = e?.data?.detail || 'Não foi possível atualizar o perfil.'
  } finally {
    profileSaving.value = false
  }
}

async function loadAddresses () {
  addressesPending.value = true
  try {
    addresses.value = await $fetch(apiPath('/api/v1/account/addresses/'), { credentials: 'include' })
  } catch {
    addresses.value = []
  } finally {
    addressesPending.value = false
  }
}

async function loadOrders () {
  ordersPending.value = true
  try {
    orders.value = await $fetch(apiPath('/api/v1/account/orders/'), {
      credentials: 'include',
      query: { filter: orderFilter.value }
    })
  } catch {
    orders.value = []
  } finally {
    ordersPending.value = false
  }
}

async function loadAccountSummary () {
  summaryPending.value = true
  try {
    accountSummary.value = await $fetch<AccountSummary>(apiPath('/api/v1/account/summary/'), { credentials: 'include' })
  } catch {
    accountSummary.value = null
  } finally {
    summaryPending.value = false
  }
}

async function loadDevices () {
  devicesPending.value = true
  try {
    const response = await $fetch<{ devices: DeviceItem[] }>(apiPath('/api/v1/account/devices/'), { credentials: 'include' })
    devices.value = response.devices || []
  } catch {
    devices.value = []
  } finally {
    devicesPending.value = false
  }
}

async function toggleFoodPreference (key: string) {
  prefPending.value = { ...prefPending.value, [key]: true }
  try {
    const response = await $fetch<{ food_preferences: AccountSummary['food_preferences'] }>(apiPath('/api/v1/account/preferences/food/'), {
      method: 'POST',
      credentials: 'include',
      body: { key }
    })
    if (accountSummary.value) accountSummary.value.food_preferences = response.food_preferences
  } catch (e: any) {
    toast.add({ color: 'error', title: 'Não foi possível salvar a preferência', description: e?.data?.detail || '' })
  } finally {
    prefPending.value = { ...prefPending.value, [key]: false }
  }
}

async function toggleNotificationPreference (channel: string) {
  notificationPending.value = { ...notificationPending.value, [channel]: true }
  try {
    const response = await $fetch<{ notification_preferences: AccountSummary['notification_preferences'] }>(apiPath('/api/v1/account/preferences/notifications/'), {
      method: 'POST',
      credentials: 'include',
      body: { channel }
    })
    if (accountSummary.value) accountSummary.value.notification_preferences = response.notification_preferences
  } catch (e: any) {
    toast.add({ color: 'error', title: 'Não foi possível salvar o canal', description: e?.data?.detail || '' })
  } finally {
    notificationPending.value = { ...notificationPending.value, [channel]: false }
  }
}

async function revokeDevice (device: DeviceItem) {
  devicePending.value = { ...devicePending.value, [device.id]: true }
  try {
    await $fetch(apiPath(`/api/v1/account/devices/${device.id}/`), {
      method: 'DELETE',
      credentials: 'include'
    })
    await loadDevices()
    toast.add({ color: 'success', title: 'Dispositivo revogado' })
  } catch (e: any) {
    toast.add({ color: 'error', title: 'Não foi possível revogar', description: e?.data?.detail || '' })
  } finally {
    devicePending.value = { ...devicePending.value, [device.id]: false }
  }
}

async function confirmRevokeDevice () {
  const device = revokeDeviceCandidate.value
  if (!device) return
  await revokeDevice(device)
  revokeDeviceCandidate.value = null
}

async function revokeAllDevices () {
  revokeAllDevicesPending.value = true
  try {
    await $fetch(apiPath('/api/v1/account/devices/'), {
      method: 'DELETE',
      credentials: 'include'
    })
    devices.value = []
    revokeAllDevicesOpen.value = false
    toast.add({ color: 'success', title: 'Dispositivos revogados' })
  } catch (e: any) {
    toast.add({ color: 'error', title: 'Não foi possível revogar os dispositivos', description: e?.data?.detail || '' })
  } finally {
    revokeAllDevicesPending.value = false
  }
}

async function deleteAccount () {
  if (!deleteAccountAcknowledged.value || deleteAccountPending.value) return
  deleteAccountPending.value = true
  try {
    await $fetch(apiPath('/api/v1/account/delete/'), {
      method: 'POST',
      credentials: 'include',
      body: { acknowledged: true }
    })
    session.reset()
    clearCart()
    clearNuxtData('shopman-auth-session')
    clearNuxtData('shopman-account-auth-session')
    clearNuxtData('shopman-shell-home')
    clearNuxtData('shopman-account-profile')
    await navigateTo('/')
  } catch (e: any) {
    toast.add({ color: 'error', title: 'Não foi possível excluir a conta', description: e?.data?.detail || '' })
  } finally {
    deleteAccountPending.value = false
  }
}

function formatOrderDate (order: { created_at?: string, created_at_display?: string }) {
  if (order.created_at_display) return order.created_at_display
  if (!order.created_at) return 'Data não informada'
  const date = new Date(order.created_at)
  if (Number.isNaN(date.getTime())) return 'Data não informada'
  return date.toLocaleDateString('pt-BR', { day: '2-digit', month: 'short', year: 'numeric' })
}

function orderColor (order: OrderItem): UiColor {
  if (['completed', 'delivered'].includes(order.status)) return 'success'
  if (['cancelled', 'returned'].includes(order.status)) return 'error'
  if (['preparing', 'ready'].includes(order.status)) return 'warning'
  if (['new', 'confirmed', 'dispatched'].includes(order.status)) return 'info'
  return 'neutral'
}

const exportUrl = computed(() => apiPath('/api/v1/account/export/'))
const lastOrder = computed(() => orders.value[0] || accountSummary.value?.last_order || null)
const defaultAddress = computed(() => addresses.value.find(address => address.is_default) || addresses.value[0] || null)
const activeFoodPreferences = computed(() => accountSummary.value?.food_preferences.filter(pref => pref.is_active) || [])
const enabledNotificationChannels = computed(() => accountSummary.value?.notification_preferences.filter(pref => pref.enabled) || [])
const loyaltyProgress = computed(() => {
  const loyalty = accountSummary.value?.loyalty
  if (!loyalty?.stamps_target) return 0
  return Math.min(100, Math.round((loyalty.stamps_current / loyalty.stamps_target) * 100))
})

const accountMemoryCards = computed(() => [
  {
    label: 'Pedidos',
    value: summaryPending.value ? 'Carregando' : `${accountSummary.value?.recent_order_count ?? orders.value.length}`,
    detail: accountSummary.value?.active_order_count ? `${accountSummary.value.active_order_count} em andamento` : 'Nenhum pedido em andamento'
  },
  {
    label: 'Último pedido',
    value: lastOrder.value ? `Pedido ${lastOrder.value.ref}` : 'Sem pedidos',
    detail: lastOrder.value ? `${lastOrder.value.total_display} · ${lastOrder.value.status_label}` : 'Seu histórico aparece depois do primeiro pedido',
    to: lastOrder.value ? `/tracking/${lastOrder.value.ref}` : '/menu'
  },
  {
    label: 'Endereço padrão',
    value: defaultAddress.value?.label || 'Não salvo',
    detail: defaultAddress.value?.formatted_address || 'Usado para acelerar o checkout'
  },
  {
    label: 'Preferências',
    value: activeFoodPreferences.value.length ? `${activeFoodPreferences.value.length} ativa(s)` : 'Nenhuma ativa',
    detail: activeFoodPreferences.value.length ? activeFoodPreferences.value.map(pref => pref.label).join(', ') : 'Configure restrições alimentares'
  }
])

const tabs = computed<TabsItem[]>(() => [
  { label: 'Perfil', value: 'profile', slot: 'profile' as const },
  { label: 'Pedidos', value: 'orders', slot: 'orders' as const },
  { label: 'Endereços', value: 'addresses', slot: 'addresses' as const },
  { label: 'Fidelidade', value: 'loyalty', slot: 'loyalty' as const },
  { label: 'Preferências', value: 'preferences', slot: 'preferences' as const },
  { label: 'Segurança', value: 'security', slot: 'security' as const }
])

watch(orderFilter, () => {
  void loadOrders()
})

watch(() => route.query.tab, (tab) => {
  activeTab.value = normalizeAccountTab(tab)
})

watch(activeTab, (tab) => {
  const current = normalizeAccountTab(route.query.tab)
  if (tab === current) return
  const query = { ...route.query }
  if (tab === 'profile') delete query.tab
  else query.tab = tab
  void router.replace({ path: '/conta', query })
})

onMounted(() => {
  void Promise.all([loadProfile(), loadAddresses(), loadOrders(), loadAccountSummary(), loadDevices()])
})

watch(deleteAccountOpen, (open) => {
  if (!open) deleteAccountAcknowledged.value = false
})

useHead({ title: 'Sua conta' })
</script>

<template>
  <UContainer class="py-8 sm:py-12">
    <UPageHeader title="Sua conta">
      <template #description>
        Perfil, pedidos, endereços e preferências do cliente.
      </template>
      <template #links>
        <UButton label="Sair" :to="logoutRoute" icon="i-lucide-log-out" color="neutral" variant="ghost" />
      </template>
    </UPageHeader>

    <div class="mt-8 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <UCard
        v-for="card in accountMemoryCards"
        :key="card.label"
        :ui="{ body: 'p-4' }"
      >
        <NuxtLink
          v-if="card.to"
          :to="card.to"
          class="block min-w-0 hover:text-primary"
        >
          <span class="text-xs font-semibold uppercase text-muted">{{ card.label }}</span>
          <strong class="mt-1 block truncate text-base text-highlighted">{{ card.value }}</strong>
          <span class="mt-1 line-clamp-2 text-sm leading-relaxed text-muted">{{ card.detail }}</span>
        </NuxtLink>
        <div v-else class="min-w-0">
          <span class="text-xs font-semibold uppercase text-muted">{{ card.label }}</span>
          <strong class="mt-1 block truncate text-base text-highlighted">{{ card.value }}</strong>
          <span class="mt-1 line-clamp-2 text-sm leading-relaxed text-muted">{{ card.detail }}</span>
        </div>
      </UCard>
    </div>

    <UTabs
      v-model="activeTab"
      :items="tabs"
      class="mt-8"
      variant="link"
      :ui="{ list: 'border-b border-default overflow-x-auto' }"
    >
      <template #profile>
        <UCard class="mt-6" :ui="{ body: 'p-6 sm:p-8' }">
          <USkeleton v-if="profilePending" class="h-32" />
          <div v-else-if="profile" class="grid gap-6">
            <div class="flex items-center gap-4">
              <UAvatar
                :text="(customerName || profile.name).split(' ').slice(0,2).map(p => p[0]).join('').toUpperCase()"
                size="xl"
                class="bg-primary/10 text-primary font-semibold"
              />
              <div>
                <h2 class="text-xl font-semibold">{{ profile.name || 'Sem nome' }}</h2>
                <p class="text-sm text-muted">Cliente cadastrado</p>
              </div>
            </div>

            <USeparator />

            <dl class="grid gap-4 sm:grid-cols-2">
              <div>
                <dt class="mb-1 text-xs font-semibold uppercase text-muted">Telefone</dt>
                <dd class="font-medium tabular-nums">{{ profile.phone || '—' }}</dd>
              </div>
              <div>
                <dt class="mb-1 text-xs font-semibold uppercase text-muted">E-mail</dt>
                <dd class="font-medium">{{ profile.email || '—' }}</dd>
              </div>
            </dl>

            <form class="grid gap-4 rounded-lg border border-default bg-elevated/40 p-4 sm:grid-cols-2" @submit.prevent="saveProfile">
              <UAlert
                v-if="profileError"
                color="error"
                variant="soft"
                :title="profileError"
                class="sm:col-span-2"
              />
              <UFormField label="Primeiro nome" name="first_name" required>
                <UInput
                  v-model="profileForm.first_name"
                  autocomplete="given-name"
                  placeholder="Seu primeiro nome"
                  class="w-full"
                />
              </UFormField>
              <UFormField label="Sobrenome" name="last_name">
                <UInput
                  v-model="profileForm.last_name"
                  autocomplete="family-name"
                  placeholder="Seu sobrenome"
                  class="w-full"
                />
              </UFormField>
              <UFormField label="E-mail" name="email">
                <UInput
                  v-model="profileForm.email"
                  type="email"
                  autocomplete="email"
                  placeholder="voce@example.com"
                  class="w-full"
                />
              </UFormField>
              <UFormField label="Aniversário" name="birthday">
                <UInput
                  v-model="profileForm.birthday"
                  type="date"
                  autocomplete="bday"
                  class="w-full"
                />
              </UFormField>
              <div class="flex flex-wrap justify-end gap-2 sm:col-span-2">
                <UButton
                  type="button"
                  color="neutral"
                  variant="ghost"
                  label="Desfazer alterações"
                  :disabled="profileSaving"
                  @click="syncProfileForm(profile)"
                />
                <UButton
                  type="submit"
                  icon="i-lucide-save"
                  label="Salvar perfil"
                  :loading="profileSaving"
                />
              </div>
            </form>
          </div>
          <UEmpty v-else title="Não foi possível carregar seu perfil" />
        </UCard>
      </template>

      <template #orders>
        <div class="mt-6 grid gap-4">
          <div class="flex flex-wrap items-center justify-between gap-3">
            <div class="inline-flex rounded-lg border border-default bg-elevated p-1">
              <button
                v-for="option in orderFilterOptions"
                :key="option.value"
                type="button"
                class="rounded-md px-3 py-1.5 text-sm transition-colors"
                :class="orderFilter === option.value ? 'bg-default text-highlighted shadow-sm' : 'text-muted hover:text-highlighted'"
                @click="orderFilter = option.value"
              >
                {{ option.label }}
              </button>
            </div>
            <UButton label="Atualizar" color="neutral" variant="outline" size="sm" :loading="ordersPending" @click="loadOrders" />
          </div>

          <USkeleton v-if="ordersPending" class="h-24" />
          <UEmpty
            v-else-if="!orders.length"
            title="Nenhum pedido neste filtro"
            description="Altere o filtro ou faça um novo pedido pelo cardápio."
            :actions="[{ label: 'Ver cardápio', to: '/menu' }]"
          />
          <UCard
            v-for="order in orders"
            :key="order.ref"
            :ui="{ body: 'p-4 sm:p-5' }"
          >
            <div class="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto_auto] sm:items-center">
              <NuxtLink :to="`/tracking/${order.ref}`" class="min-w-0 hover:text-primary transition-colors">
                <div class="flex flex-wrap items-center gap-2">
                  <strong class="text-base">Pedido {{ order.ref }}</strong>
                  <UBadge :color="orderColor(order)" variant="subtle" size="xs">{{ order.status_label }}</UBadge>
                </div>
                <p class="mt-1 text-sm text-muted">
                  {{ formatOrderDate(order) }}
                  <span v-if="order.item_count"> · {{ order.item_count }} {{ order.item_count === 1 ? 'item' : 'itens' }}</span>
                </p>
              </NuxtLink>
              <strong class="text-left text-lg tabular-nums sm:text-right">{{ order.total_display }}</strong>
              <div class="flex items-center gap-1">
                <UButton
                  v-if="reorderActionForOrder(order)"
                  size="xs"
                  color="neutral"
                  variant="ghost"
                  icon="i-lucide-rotate-ccw"
                  aria-label="Repetir pedido"
                  :loading="reorderPending"
                  @click="reorderById(order.ref)"
                />
                <UButton
                  size="xs"
                  color="neutral"
                  variant="ghost"
                  icon="i-lucide-chevron-right"
                  :to="`/tracking/${order.ref}`"
                  aria-label="Ver detalhes"
                />
              </div>
            </div>
          </UCard>
        </div>
      </template>

      <template #addresses>
        <div class="mt-6 grid gap-3">
          <div class="flex justify-end">
            <UButton
              icon="i-lucide-plus"
              label="Novo endereço"
              size="sm"
              @click="openAddressModal(null)"
            />
          </div>

          <USkeleton v-if="addressesPending" class="h-24" />
          <UEmpty
            v-else-if="!addresses.length"
            title="Nenhum endereço salvo"
            description="Salve um endereço para acelerar próximos pedidos."
            :actions="[{ label: 'Adicionar endereço', icon: 'i-lucide-plus', onClick: () => openAddressModal(null) }]"
          />
          <UCard
            v-for="address in addresses"
            :key="address.id"
            :ui="{ body: 'p-4 sm:p-5' }"
          >
            <div class="flex items-start gap-3">
              <div class="min-w-0 flex-1">
                <div class="flex items-center gap-2">
                  <strong>{{ address.label }}</strong>
                  <UBadge v-if="address.is_default" color="primary" variant="subtle" size="xs">Padrão</UBadge>
                </div>
                <p class="mt-1 text-sm leading-relaxed text-muted">{{ address.formatted_address }}</p>
                <p v-if="address.complement" class="mt-1 text-sm text-muted">
                  Complemento: {{ address.complement }}
                </p>
                <p v-if="address.delivery_instructions" class="mt-1 text-sm text-muted">
                  {{ address.delivery_instructions }}
                </p>
              </div>
              <div class="flex shrink-0 items-center gap-1">
                <UButton
                  v-if="!address.is_default"
                  size="xs"
                  color="neutral"
                  variant="ghost"
                  icon="i-lucide-star"
                  aria-label="Marcar como padrão"
                  @click="setDefaultAddress(address)"
                />
                <UButton
                  size="xs"
                  color="neutral"
                  variant="ghost"
                  icon="i-lucide-pencil"
                  aria-label="Editar endereço"
                  @click="openAddressModal(address)"
                />
                <UButton
                  size="xs"
                  color="error"
                  variant="ghost"
                  icon="i-lucide-trash-2"
                  aria-label="Excluir endereço"
                  @click="openDeleteAddress(address)"
                />
              </div>
            </div>
          </UCard>
        </div>
      </template>

      <template #loyalty>
        <UCard class="mt-6" :ui="{ body: 'p-6 sm:p-8' }">
          <USkeleton v-if="summaryPending" class="h-40" />
          <UEmpty v-else-if="!accountSummary?.loyalty" title="Fidelidade indisponível" description="Nenhuma conta de fidelidade associada a este cliente." />
          <div v-else class="grid gap-6">
            <div class="grid gap-4 sm:grid-cols-[1fr_auto] sm:items-end">
              <div>
                <p class="text-xs font-semibold uppercase text-muted">Nível</p>
                <h2 class="mt-1 text-2xl font-bold text-highlighted">{{ accountSummary.loyalty.tier_display }}</h2>
                <p class="mt-1 text-sm text-muted">{{ accountSummary.loyalty.points_balance }} pontos disponíveis</p>
              </div>
              <UBadge color="primary" variant="subtle" class="w-fit">
                {{ accountSummary.loyalty.stamps_current }}/{{ accountSummary.loyalty.stamps_target }} selos
              </UBadge>
            </div>

            <div>
              <div class="mb-2 flex justify-between text-sm">
                <span class="text-muted">Progresso do cartão</span>
                <span class="font-medium">{{ loyaltyProgress }}%</span>
              </div>
              <UProgress :model-value="loyaltyProgress" />
            </div>

            <div v-if="accountSummary.loyalty.transactions.length" class="grid gap-2">
              <h3 class="text-sm font-semibold text-highlighted">Últimas movimentações</h3>
              <div
                v-for="txn in accountSummary.loyalty.transactions"
                :key="`${txn.date_display}-${txn.description}-${txn.points}`"
                class="flex items-center justify-between gap-4 rounded-lg border border-default px-3 py-2 text-sm"
              >
                <span class="min-w-0">
                  <span class="block truncate font-medium">{{ txn.description }}</span>
                  <span class="text-muted">{{ txn.date_display }}</span>
                </span>
                <strong :class="txn.is_credit ? 'text-success' : 'text-muted'" class="tabular-nums">
                  {{ txn.is_credit ? '+' : '' }}{{ txn.points }}
                </strong>
              </div>
            </div>
          </div>
        </UCard>
      </template>

      <template #preferences>
        <div class="mt-6 grid gap-4 lg:grid-cols-2">
          <UCard :ui="{ body: 'p-5 sm:p-6' }">
            <template #header>
              <strong>Preferências alimentares</strong>
            </template>
            <USkeleton v-if="summaryPending" class="h-28" />
            <div v-else class="grid gap-3">
              <div
                v-for="pref in accountSummary?.food_preferences || []"
                :key="pref.key"
                class="flex items-center justify-between gap-4 rounded-lg border border-default px-3 py-2"
              >
                <span class="text-sm font-medium">{{ pref.label }}</span>
                <USwitch
                  :model-value="pref.is_active"
                  :loading="prefPending[pref.key]"
                  :aria-label="`Alternar ${pref.label}`"
                  @update:model-value="toggleFoodPreference(pref.key)"
                />
              </div>
            </div>
          </UCard>

          <UCard :ui="{ body: 'p-5 sm:p-6' }">
            <template #header>
              <strong>Comunicação</strong>
            </template>
            <USkeleton v-if="summaryPending" class="h-28" />
            <div v-else class="grid gap-3">
              <div
                v-for="channel in accountSummary?.notification_preferences || []"
                :key="channel.key"
                class="grid gap-2 rounded-lg border border-default px-3 py-2"
              >
                <div class="flex items-center justify-between gap-4">
                  <span class="text-sm font-medium">{{ channel.label }}</span>
                  <USwitch
                    :model-value="channel.enabled"
                    :loading="notificationPending[channel.key]"
                    :aria-label="`Alternar ${channel.label}`"
                    @update:model-value="toggleNotificationPreference(channel.key)"
                  />
                </div>
                <p class="text-xs leading-relaxed text-muted">{{ channel.description }}</p>
              </div>
            </div>
          </UCard>
        </div>
      </template>

      <template #security>
        <div class="mt-6 grid gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
          <UCard :ui="{ body: 'p-5 sm:p-6' }">
            <template #header>
              <div class="flex flex-wrap items-center justify-between gap-3">
                <strong>Dispositivos confiáveis</strong>
                <UButton
                  v-if="devices.length"
                  label="Revogar todos"
                  color="error"
                  variant="outline"
                  size="sm"
                  @click="revokeAllDevicesOpen = true"
                />
              </div>
            </template>

            <USkeleton v-if="devicesPending" class="h-28" />
            <UEmpty v-else-if="!devices.length" title="Nenhum dispositivo confiável" description="Dispositivos salvos para login rápido aparecem aqui." />
            <div v-else class="grid gap-3">
              <div
                v-for="device in devices"
                :key="device.id"
                class="grid gap-3 rounded-lg border border-default p-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center"
              >
                <div class="min-w-0">
                  <div class="flex flex-wrap items-center gap-2">
                    <strong class="truncate">{{ device.label }}</strong>
                    <UBadge v-if="device.is_current" color="primary" variant="subtle" size="xs">Atual</UBadge>
                  </div>
                  <p class="mt-1 text-sm text-muted">Último uso: {{ device.last_used_at_display }}</p>
                  <p v-if="device.location" class="mt-1 text-xs text-muted">{{ device.location }}</p>
                </div>
                <UButton
                  label="Revogar"
                  color="error"
                  variant="ghost"
                  size="sm"
                  :loading="devicePending[device.id]"
                  @click="revokeDeviceCandidate = device"
                />
              </div>
            </div>
          </UCard>

          <UCard :ui="{ body: 'p-5 sm:p-6' }">
            <template #header>
              <strong>Dados da conta</strong>
            </template>
            <div class="grid gap-3">
              <p class="text-sm leading-relaxed text-muted">
                Exporte os dados vinculados ao cliente ou solicite a exclusão da conta.
              </p>
              <UButton
                :to="exportUrl"
                target="_blank"
                rel="noopener"
                label="Exportar dados"
                color="neutral"
                variant="outline"
                block
              />
              <UButton
                label="Excluir conta"
                color="error"
                variant="soft"
                block
                @click="deleteAccountOpen = true"
              />
            </div>
          </UCard>
        </div>
      </template>
    </UTabs>

    <AddressFormModal
      v-model:open="addressModalOpen"
      :address="addressBeingEdited"
      @saved="onAddressSaved"
    />

    <UModal v-model:open="deleteModalOpen" title="Excluir endereço" :ui="{ content: 'max-w-lg' }">
      <template #body>
        <div class="grid gap-4">
          <UAlert
            color="warning"
            variant="soft"
            title="Essa ação remove um endereço salvo"
            description="Próximos checkouts deixam de sugerir esse endereço. Pedidos já enviados não mudam."
          />
          <div v-if="addressToDelete" class="rounded-lg border border-default p-4">
            <p class="font-semibold text-highlighted">{{ addressToDelete.label }}</p>
            <p class="mt-1 text-sm leading-relaxed text-muted">{{ addressToDelete.formatted_address }}</p>
            <p v-if="addressToDelete.complement" class="mt-1 text-sm text-muted">{{ addressToDelete.complement }}</p>
          </div>
          <div class="grid gap-3 sm:grid-cols-2">
            <UButton
              color="neutral"
              variant="outline"
              label="Manter endereço"
              block
              @click="deleteModalOpen = false"
            />
            <UButton
              color="error"
              variant="solid"
              label="Excluir endereço"
              icon="i-lucide-trash-2"
              block
              :loading="deletePending"
              @click="confirmDeleteAddress"
            />
          </div>
        </div>
      </template>
    </UModal>

    <UModal v-model:open="revokeDeviceOpen" title="Revogar dispositivo?" :ui="{ content: 'max-w-lg' }">
      <template #body>
        <div class="grid gap-4">
          <UAlert
            color="warning"
            variant="soft"
            title="Login rápido será removido deste dispositivo"
            description="Na próxima tentativa, este dispositivo terá que passar por OTP novamente."
          />
          <div v-if="revokeDeviceCandidate" class="rounded-lg border border-default p-4">
            <p class="font-semibold text-highlighted">{{ revokeDeviceCandidate.label }}</p>
            <p class="mt-1 text-sm text-muted">Último uso: {{ revokeDeviceCandidate.last_used_at_display }}</p>
            <p v-if="revokeDeviceCandidate.location" class="mt-1 text-xs text-muted">{{ revokeDeviceCandidate.location }}</p>
          </div>
          <div class="grid gap-3 sm:grid-cols-2">
            <UButton color="neutral" variant="outline" label="Manter dispositivo" block @click="revokeDeviceCandidate = null" />
            <UButton
              color="error"
              variant="solid"
              label="Revogar dispositivo"
              block
              :loading="revokeDeviceCandidate ? devicePending[revokeDeviceCandidate.id] : false"
              @click="confirmRevokeDevice"
            />
          </div>
        </div>
      </template>
    </UModal>

    <UModal v-model:open="revokeAllDevicesOpen" title="Revogar dispositivos" :ui="{ content: 'max-w-lg' }">
      <template #body>
        <div class="grid gap-4">
          <UAlert
            color="warning"
            variant="soft"
            title="Login rápido será removido"
            description="Os dispositivos confiáveis terão que passar por OTP novamente no próximo acesso."
          />
          <div class="grid gap-3 sm:grid-cols-2">
            <UButton color="neutral" variant="outline" label="Cancelar" block @click="revokeAllDevicesOpen = false" />
            <UButton color="error" label="Revogar todos" block :loading="revokeAllDevicesPending" @click="revokeAllDevices" />
          </div>
        </div>
      </template>
    </UModal>

    <UModal v-model:open="deleteAccountOpen" title="Excluir conta" :ui="{ content: 'max-w-lg' }">
      <template #body>
        <div class="grid gap-4">
          <UAlert
            color="error"
            variant="soft"
            title="A conta será anonimizada"
            description="Dados pessoais, consentimentos e endereços serão removidos. Pedidos operacionais podem permanecer sem dados pessoais para auditoria transacional."
          />
          <UCheckbox
            v-model="deleteAccountAcknowledged"
            label="Entendo que esta ação não pode ser desfeita."
          />
          <div class="grid gap-3 sm:grid-cols-2">
            <UButton color="neutral" variant="outline" label="Cancelar" block @click="deleteAccountOpen = false" />
            <UButton
              color="error"
              label="Excluir conta"
              block
              :disabled="!deleteAccountAcknowledged"
              :loading="deleteAccountPending"
              @click="deleteAccount"
            />
          </div>
        </div>
      </template>
    </UModal>
  </UContainer>
</template>
