<script setup lang="ts">
import type { SavedAddressProjection } from '~/types/shopman'
import { addressSheetDescription, addressSheetTitle } from '~/presentation/account'

definePageMeta({ middleware: 'account' })

type AddressMode = 'create' | 'edit'

const apiPath = useShopmanApiPath()
const csrfHeaders = useShopmanCsrfHeaders()
const requestHeaders = import.meta.server ? useRequestHeaders(['cookie']) : undefined

const addressSheetOpen = ref(false)
const addressMode = ref<AddressMode>('create')
const addressEditing = ref<SavedAddressProjection | null>(null)
const addressIssue = ref('')
const addressDeleteOpen = ref(false)
const addressDeleteCandidate = ref<SavedAddressProjection | null>(null)
const addressDeletePending = ref(false)
const addressDefaultPending = ref<Record<number, boolean>>({})

const { data: addresses, pending, refresh: refreshAddresses } = await useFetch<SavedAddressProjection[]>(apiPath('/api/v1/account/addresses/'), {
  credentials: 'include',
  headers: requestHeaders
})

const sheetTitle = computed(() => addressSheetTitle(addressMode.value))
const sheetDescription = computed(() => addressSheetDescription(addressMode.value))

function openCreateAddress () {
  addressMode.value = 'create'
  addressEditing.value = null
  addressIssue.value = ''
  addressSheetOpen.value = true
}

function openEditAddress (address: SavedAddressProjection) {
  addressMode.value = 'edit'
  addressEditing.value = address
  addressIssue.value = ''
  addressSheetOpen.value = true
}

async function onAddressDone () {
  await refreshAddresses()
  addressSheetOpen.value = false
  addressEditing.value = null
}

async function setDefaultAddress (address: SavedAddressProjection) {
  addressDefaultPending.value = { ...addressDefaultPending.value, [address.id]: true }
  try {
    await $fetch(apiPath(`/api/v1/account/addresses/${encodeURIComponent(address.id)}/?action=default`), {
      method: 'POST',
      headers: await csrfHeaders(),
      credentials: 'include',
      body: { action: 'default' }
    })
    await refreshAddresses()
  } finally {
    const next = { ...addressDefaultPending.value }
    delete next[address.id]
    addressDefaultPending.value = next
  }
}

function askDeleteAddress (address: SavedAddressProjection) {
  addressDeleteCandidate.value = address
  addressIssue.value = ''
  addressDeleteOpen.value = true
}

async function deleteAddress () {
  const address = addressDeleteCandidate.value
  if (!address || addressDeletePending.value) return
  addressDeletePending.value = true
  addressIssue.value = ''
  try {
    await $fetch(apiPath(`/api/v1/account/addresses/${encodeURIComponent(address.id)}/`), {
      method: 'DELETE',
      headers: await csrfHeaders(),
      credentials: 'include'
    })
    await refreshAddresses()
    addressDeleteOpen.value = false
    addressDeleteCandidate.value = null
  } catch (e: any) {
    addressIssue.value = e?.data?.detail || 'Não foi possível remover o endereço agora.'
  } finally {
    addressDeletePending.value = false
  }
}

useSeoMeta({ title: 'Endereços' })
</script>

<template>
  <main class="shop-section pt-0">
    <div class="shop-breadcrumb-bar mb-5">
      <div class="shop-container py-2.5">
        <UiBreadcrumbs :items="[{ label: 'Início', link: '/' }, { label: 'Conta', link: '/account' }, { label: 'Endereços' }]" />
      </div>
    </div>
    <div class="shop-container space-y-5">

      <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 class="text-2xl font-semibold">Endereços</h1>
          <p class="text-sm text-muted-foreground">
            {{ pending ? 'Carregando…' : formatCount(addresses?.length || 0, 'endereço salvo', 'endereços salvos') }}
          </p>
        </div>
        <UiButton icon="lucide:plus" @click="openCreateAddress">Adicionar endereço</UiButton>
      </div>

      <UiSkeleton v-if="pending" class="h-32 rounded-lg" />

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

      <ul v-else class="grid grid-cols-1 gap-3 md:grid-cols-2">
        <li
          v-for="address in addresses || []"
          :key="address.id"
          class="flex flex-col gap-3 rounded-lg border bg-card p-4"
          :class="address.is_default ? 'border-primary/40' : ''"
        >
          <div class="flex items-start gap-3">
            <span class="flex size-10 shrink-0 items-center justify-center rounded-md bg-muted text-foreground">
              <Icon name="lucide:map-pin" class="size-5" />
            </span>
            <div class="min-w-0 flex-1">
              <p class="flex items-center gap-2 font-medium">
                {{ address.label }}
                <UiBadge v-if="address.is_default" variant="secondary">Padrão</UiBadge>
              </p>
              <p class="mt-0.5 text-sm text-muted-foreground">{{ address.formatted_address }}</p>
              <p v-if="address.complement" class="text-sm text-muted-foreground">{{ address.complement }}</p>
            </div>
          </div>
          <div class="flex flex-wrap gap-2 border-t pt-3">
            <UiButton
              v-if="!address.is_default"
              variant="ghost"
              size="sm"
              icon="lucide:star"
              :loading="!!addressDefaultPending[address.id]"
              @click="setDefaultAddress(address)"
            >
              Definir padrão
            </UiButton>
            <UiButton variant="ghost" size="sm" icon="lucide:pencil" @click="openEditAddress(address)">Editar</UiButton>
            <UiButton variant="ghost" size="sm" icon="lucide:trash-2" class="ml-auto text-muted-foreground hover:text-destructive" @click="askDeleteAddress(address)">Remover</UiButton>
          </div>
        </li>
      </ul>

      <UiSheet v-model:open="addressSheetOpen">
        <UiSheetContent side="bottom" variant="floating" class="mx-auto max-h-[90dvh] max-w-2xl overflow-y-auto">
          <UiSheetHeader>
            <UiSheetTitle>{{ sheetTitle }}</UiSheetTitle>
            <UiSheetDescription>{{ sheetDescription }}</UiSheetDescription>
          </UiSheetHeader>
          <div class="px-4 pb-4">
            <AddressPicker
              :key="addressEditing?.id ?? 'create'"
              context="account"
              :editing-address="addressEditing"
              :initial-is-default="!(addresses || []).length"
              @done="onAddressDone"
            />
          </div>
        </UiSheetContent>
      </UiSheet>

      <UiAlertDialog v-model:open="addressDeleteOpen">
        <UiAlertDialogContent>
          <UiAlertDialogHeader>
            <UiAlertDialogTitle>Remover endereço?</UiAlertDialogTitle>
            <UiAlertDialogDescription>
              {{ addressDeleteCandidate?.formatted_address || 'Este endereço deixará de aparecer no checkout.' }}
            </UiAlertDialogDescription>
          </UiAlertDialogHeader>
          <UiAlert v-if="addressIssue" variant="destructive">
            <UiAlertTitle>Não foi possível remover</UiAlertTitle>
            <UiAlertDescription>{{ addressIssue }}</UiAlertDescription>
          </UiAlert>
          <UiAlertDialogFooter>
            <UiAlertDialogCancel :disabled="addressDeletePending">Cancelar</UiAlertDialogCancel>
            <UiAlertDialogAction variant="destructive" :disabled="addressDeletePending" @click="deleteAddress">Remover</UiAlertDialogAction>
          </UiAlertDialogFooter>
        </UiAlertDialogContent>
      </UiAlertDialog>
    </div>
  </main>
</template>
