<script setup lang="ts">
import type { AccountDeviceProjection, AccountDeviceResponse } from '~/types/shopman'
import { deviceIcon } from '~/presentation/account'

definePageMeta({ middleware: 'account' })

type RevokeDeviceMode = 'one' | 'all'

const apiPath = useShopmanApiPath()
const csrfHeaders = useShopmanCsrfHeaders()
const session = useShopSession()
const requestHeaders = import.meta.server ? useRequestHeaders(['cookie']) : undefined

const exportPending = ref(false)
const privacyIssue = ref('')
const deleteAccountOpen = ref(false)
const deleteAccountAcknowledged = ref(false)
const deleteAccountPending = ref(false)
const deviceIssue = ref('')
const revokeDeviceOpen = ref(false)
const revokeDeviceMode = ref<RevokeDeviceMode>('one')
const revokeDeviceCandidate = ref<AccountDeviceProjection | null>(null)
const revokeDevicePending = ref(false)

const { data: devicesResponse, pending: devicesPending, refresh: refreshDevices } = await useFetch<AccountDeviceResponse>(apiPath('/api/v1/account/devices/'), {
  credentials: 'include',
  headers: requestHeaders
})

const accountDevices = computed(() => devicesResponse.value?.devices || [])

async function exportData () {
  if (!import.meta.client || exportPending.value) return
  exportPending.value = true
  privacyIssue.value = ''
  try {
    window.location.assign(apiPath('/api/v1/account/export/'))
  } finally {
    setTimeout(() => { exportPending.value = false }, 1000)
  }
}

function askDeleteAccount () {
  privacyIssue.value = ''
  deleteAccountAcknowledged.value = false
  deleteAccountOpen.value = true
}

async function deleteAccount () {
  if (!deleteAccountAcknowledged.value || deleteAccountPending.value) return
  deleteAccountPending.value = true
  privacyIssue.value = ''
  try {
    await $fetch(apiPath('/api/v1/account/delete/'), {
      method: 'POST',
      headers: await csrfHeaders(),
      credentials: 'include',
      body: { acknowledged: true }
    })
    session.reset()
    deleteAccountOpen.value = false
    await navigateTo('/')
  } catch (e: any) {
    privacyIssue.value = e?.data?.detail || 'Não foi possível excluir a conta agora.'
  } finally {
    deleteAccountPending.value = false
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
    if (import.meta.client) {
      useSonner.success(revokeDeviceMode.value === 'all' ? 'Aparelhos removidos.' : 'Aparelho removido.')
    }
  } catch (e: any) {
    deviceIssue.value = e?.data?.detail || 'Não foi possível remover o aparelho agora.'
    if (import.meta.client) useSonner.error(deviceIssue.value)
  } finally {
    revokeDevicePending.value = false
  }
}

useSeoMeta({ title: 'Segurança e dados' })
</script>

<template>
  <main class="shop-section pt-0">
    <div class="shop-breadcrumb-bar mb-4">
      <div class="shop-container py-2">
        <UiBreadcrumbs :items="[{ label: 'Início', link: '/' }, { label: 'Conta', link: '/account' }, { label: 'Segurança e dados' }]" />
      </div>
    </div>
    <div class="shop-container shop-stack-block">

      <div>
        <h1 class="text-2xl font-semibold">Segurança e dados</h1>
        <p class="text-sm text-muted-foreground">Aparelhos confiáveis e o controle dos seus dados pessoais.</p>
      </div>

      <!-- Aparelhos confiáveis -->
      <section class="space-y-4">
        <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 class="text-lg font-semibold">Aparelhos confiáveis</h2>
            <p class="text-sm text-muted-foreground">
              {{ devicesPending ? 'Carregando…' : formatCount(accountDevices.length, 'aparelho autorizado', 'aparelhos autorizados') }}
            </p>
          </div>
          <UiButton v-if="accountDevices.length > 1" variant="outline" size="sm" icon="lucide:shield-x" @click="askRevokeAllDevices">
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
          <UiItem v-for="device in accountDevices" :key="device.id" variant="outline" class="bg-card">
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
              <UiButton variant="ghost" size="sm" icon="lucide:shield-x" @click="askRevokeDevice(device)">Remover</UiButton>
            </UiItemActions>
          </UiItem>
        </UiItemGroup>
      </section>

      <!-- Dados e privacidade -->
      <section class="shop-stack-block rounded-lg border bg-card p-4">
        <div>
          <h2 class="text-lg font-semibold">Dados e privacidade</h2>
          <p class="mt-1 text-sm text-muted-foreground">Baixe uma cópia dos seus dados ou encerre sua conta.</p>
        </div>
        <UiAlert v-if="privacyIssue" variant="destructive">
          <UiAlertTitle>Privacidade</UiAlertTitle>
          <UiAlertDescription>{{ privacyIssue }}</UiAlertDescription>
        </UiAlert>
        <div class="grid grid-cols-1 gap-2 sm:grid-cols-2">
          <UiButton variant="outline" class="justify-start" icon="lucide:download" :loading="exportPending" @click="exportData">
            Exportar meus dados
          </UiButton>
          <UiButton variant="destructive" class="justify-start" icon="lucide:user-x" @click="askDeleteAccount">
            Excluir minha conta
          </UiButton>
        </div>
      </section>

      <UiAlertDialog v-model:open="deleteAccountOpen">
        <UiAlertDialogContent>
          <UiAlertDialogHeader>
            <UiAlertDialogTitle>Excluir sua conta?</UiAlertDialogTitle>
            <UiAlertDialogDescription>
              Seus dados pessoais serão anonimizados e você sairá da loja neste aparelho.
            </UiAlertDialogDescription>
          </UiAlertDialogHeader>
          <UiAlert v-if="privacyIssue" variant="destructive">
            <UiAlertTitle>Não foi possível excluir</UiAlertTitle>
            <UiAlertDescription>{{ privacyIssue }}</UiAlertDescription>
          </UiAlert>
          <UiField orientation="horizontal">
            <UiFieldContent>
              <UiFieldLabel for="delete-account-ack">Entendi o efeito desta ação</UiFieldLabel>
              <UiFieldDescription>Histórico operacional de pedidos pode permanecer anonimizado para auditoria.</UiFieldDescription>
            </UiFieldContent>
            <UiCheckbox id="delete-account-ack" v-model="deleteAccountAcknowledged" />
          </UiField>
          <UiAlertDialogFooter>
            <UiAlertDialogCancel :disabled="deleteAccountPending">Voltar</UiAlertDialogCancel>
            <UiAlertDialogAction variant="destructive" :disabled="!deleteAccountAcknowledged || deleteAccountPending" @click="deleteAccount">
              Excluir conta
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
            <UiAlertDialogAction variant="destructive" :disabled="revokeDevicePending" @click="confirmRevokeDevice">Remover</UiAlertDialogAction>
          </UiAlertDialogFooter>
        </UiAlertDialogContent>
      </UiAlertDialog>
    </div>
  </main>
</template>
