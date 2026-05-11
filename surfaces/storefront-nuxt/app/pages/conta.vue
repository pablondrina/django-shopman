<script setup lang="ts">
import type { TabsItem } from '@nuxt/ui'

definePageMeta({ layout: 'default' })

const apiPath = useShopmanApiPath()
const { customerName, isAuthenticated } = useShopSession()

interface AddressItem {
  id: number
  label: string
  formatted_address: string
  is_default: boolean
  complement: string
  delivery_instructions: string
}

const profile = ref<{ ref: string, name: string, phone: string, email: string } | null>(null)
const addresses = ref<AddressItem[]>([])
const orders = ref<Array<{ ref: string, status: string, status_label: string, total_display: string, created_at_display: string }>>([])

const profilePending = ref(true)
const addressesPending = ref(true)
const ordersPending = ref(true)

const addressModalOpen = ref(false)
const addressBeingEdited = ref<AddressItem | null>(null)
const toast = useToast()

function openAddressModal (existing: AddressItem | null = null) {
  addressBeingEdited.value = existing
  addressModalOpen.value = true
}

async function deleteAddress (address: AddressItem) {
  if (!confirm(`Excluir o endereço "${address.label}"?`)) return
  try {
    await $fetch(apiPath(`/api/v1/account/addresses/${address.id}/`), {
      method: 'DELETE',
      credentials: 'include'
    })
    addresses.value = addresses.value.filter(a => a.id !== address.id)
    toast.add({ icon: 'i-lucide-circle-check', color: 'success', title: 'Endereço removido' })
  } catch (e: any) {
    toast.add({
      icon: 'i-lucide-circle-x',
      color: 'error',
      title: 'Não foi possível remover',
      description: e?.data?.detail || ''
    })
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
    toast.add({ icon: 'i-lucide-circle-check', color: 'success', title: 'Endereço padrão atualizado' })
  } catch (e: any) {
    toast.add({
      icon: 'i-lucide-circle-x',
      color: 'error',
      title: 'Não foi possível atualizar',
      description: e?.data?.detail || ''
    })
  }
}

async function onAddressSaved () {
  await loadAddresses()
  toast.add({ icon: 'i-lucide-circle-check', color: 'success', title: 'Endereço salvo' })
}

const { performReorder, pending: reorderPending } = useReorder()

async function reorderById (orderRef: string) {
  await performReorder(orderRef)
}

async function loadProfile () {
  profilePending.value = true
  try {
    profile.value = await $fetch(apiPath('/api/v1/account/profile/'), { credentials: 'include' })
  } catch {
    profile.value = null
  } finally {
    profilePending.value = false
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
    orders.value = await $fetch(apiPath('/api/v1/account/orders/'), { credentials: 'include' })
  } catch {
    orders.value = []
  } finally {
    ordersPending.value = false
  }
}

const tabs: TabsItem[] = [
  { label: 'Perfil', icon: 'i-lucide-user', slot: 'profile' as const },
  { label: 'Meus pedidos', icon: 'i-lucide-package', slot: 'orders' as const },
  { label: 'Endereços', icon: 'i-lucide-map-pin', slot: 'addresses' as const },
  { label: 'Fidelidade', icon: 'i-lucide-sparkles', slot: 'loyalty' as const }
]

onMounted(() => {
  if (!isAuthenticated.value) {
    navigateTo('/login?next=/conta')
    return
  }
  void Promise.all([loadProfile(), loadAddresses(), loadOrders()])
})

useHead({ title: 'Sua conta' })
</script>

<template>
  <UContainer class="py-8 sm:py-12">
    <UPageHeader title="Sua conta">
      <template #description>
        Tudo o que a casa sabe sobre seu jeito de pedir, em um só lugar.
      </template>
      <template #links>
        <UButton label="Sair" to="/sair" icon="i-lucide-log-out" color="neutral" variant="ghost" />
      </template>
    </UPageHeader>

    <UTabs :items="tabs" class="mt-8" variant="link" :ui="{ list: 'border-b border-default' }">
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
                <p class="text-sm text-muted">Cliente da casa</p>
              </div>
            </div>

            <USeparator />

            <dl class="grid gap-4 sm:grid-cols-2">
              <div>
                <dt class="text-xs uppercase tracking-wide font-semibold text-muted mb-1">Telefone</dt>
                <dd class="font-medium tabular-nums">{{ profile.phone || '—' }}</dd>
              </div>
              <div>
                <dt class="text-xs uppercase tracking-wide font-semibold text-muted mb-1">E-mail</dt>
                <dd class="font-medium">{{ profile.email || '—' }}</dd>
              </div>
            </dl>
          </div>
          <UEmpty v-else icon="i-lucide-user-x" title="Não foi possível carregar seu perfil" />
        </UCard>
      </template>

      <template #orders>
        <div class="mt-6 grid gap-3">
          <USkeleton v-if="ordersPending" class="h-24" />
          <UEmpty
            v-else-if="!orders.length"
            icon="i-lucide-package"
            title="Você ainda não fez pedidos"
            description="Seu primeiro pedido aparece aqui."
            :actions="[{ label: 'Ver cardápio', to: '/menu', icon: 'i-lucide-store' }]"
          />
          <UCard
            v-for="order in orders"
            :key="order.ref"
            :ui="{ body: 'p-4 sm:p-5' }"
          >
            <div class="flex items-center justify-between gap-4">
              <NuxtLink :to="`/tracking/${order.ref}`" class="flex-1 min-w-0 hover:text-primary transition-colors">
                <div class="flex items-center gap-2">
                  <strong class="text-base">Pedido {{ order.ref }}</strong>
                  <UBadge color="neutral" variant="subtle" size="xs">{{ order.status_label }}</UBadge>
                </div>
                <p class="text-sm text-muted mt-1">{{ order.created_at_display }}</p>
              </NuxtLink>
              <div class="text-right shrink-0">
                <strong class="text-lg tabular-nums">{{ order.total_display }}</strong>
              </div>
              <div class="flex items-center gap-1 shrink-0">
                <UButton
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
            icon="i-lucide-map-pin"
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
              <UIcon name="i-lucide-map-pin" class="size-5 text-muted shrink-0 mt-0.5" />
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2">
                  <strong>{{ address.label }}</strong>
                  <UBadge v-if="address.is_default" color="primary" variant="subtle" size="xs">Padrão</UBadge>
                </div>
                <p class="text-sm text-muted mt-1">{{ address.formatted_address }}</p>
                <p v-if="address.complement" class="text-sm text-muted mt-1">
                  Complemento: {{ address.complement }}
                </p>
                <p v-if="address.delivery_instructions" class="text-sm text-muted mt-1">
                  {{ address.delivery_instructions }}
                </p>
              </div>
              <div class="flex items-center gap-1 shrink-0">
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
                  @click="deleteAddress(address)"
                />
              </div>
            </div>
          </UCard>
        </div>

        <AddressFormModal
          v-model:open="addressModalOpen"
          :address="addressBeingEdited"
          @saved="onAddressSaved"
        />
      </template>

      <template #loyalty>
        <UCard class="mt-6" :ui="{ body: 'p-6 sm:p-8' }">
          <UEmpty
            icon="i-lucide-sparkles"
            title="Programa fidelidade"
            description="Em breve, seu saldo e histórico de pontos. Por enquanto, a casa cuida de aplicar os benefícios automaticamente no checkout."
          />
        </UCard>
      </template>
    </UTabs>
  </UContainer>
</template>
