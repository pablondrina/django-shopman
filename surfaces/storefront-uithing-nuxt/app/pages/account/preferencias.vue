<script setup lang="ts">
import type { AccountSummary } from '~/types/shopman'

definePageMeta({ middleware: 'account' })

const apiPath = useShopmanApiPath()
const csrfHeaders = useShopmanCsrfHeaders()
const requestHeaders = import.meta.server ? useRequestHeaders(['cookie']) : undefined

const preferencePending = ref<Record<string, boolean>>({})

const { data: summary, pending, refresh: refreshSummary } = await useFetch<AccountSummary>(apiPath('/api/v1/account/summary/'), {
  credentials: 'include',
  headers: requestHeaders
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

useSeoMeta({ title: 'Preferências' })
</script>

<template>
  <main class="shop-section">
    <div class="shop-container space-y-5">
      <UiBreadcrumbs :items="[{ label: 'Início', link: '/' }, { label: 'Conta', link: '/account' }, { label: 'Preferências' }]" />

      <div>
        <h1 class="text-2xl font-semibold">Preferências</h1>
        <p class="text-sm text-muted-foreground">Conte como você gosta de ser atendido. Você pode mudar quando quiser.</p>
      </div>

      <UiSkeleton v-if="pending" class="h-48 rounded-lg" />

      <div v-else class="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <UiFieldSet class="rounded-lg border bg-card p-4">
          <UiFieldLegend>Preferências alimentares</UiFieldLegend>
          <UiFieldGroup>
            <UiField v-for="pref in summary?.food_preferences || []" :key="pref.key" orientation="horizontal">
              <UiFieldContent>
                <UiFieldLabel :for="`food-pref-${pref.key}`">{{ pref.label }}</UiFieldLabel>
              </UiFieldContent>
              <UiSwitch
                :id="`food-pref-${pref.key}`"
                :model-value="pref.is_active"
                :disabled="!!preferencePending[pref.key]"
                @update:model-value="toggleFood(pref)"
              />
            </UiField>
          </UiFieldGroup>
        </UiFieldSet>

        <UiFieldSet class="rounded-lg border bg-card p-4">
          <UiFieldLegend>Notificações</UiFieldLegend>
          <UiFieldGroup>
            <UiField v-for="pref in summary?.notification_preferences || []" :key="pref.key" orientation="horizontal">
              <UiFieldContent>
                <UiFieldLabel :for="`notification-pref-${pref.key}`">{{ pref.label }}</UiFieldLabel>
                <UiFieldDescription>{{ pref.description }}</UiFieldDescription>
              </UiFieldContent>
              <UiSwitch
                :id="`notification-pref-${pref.key}`"
                :model-value="pref.enabled"
                :disabled="!!preferencePending[pref.key]"
                @update:model-value="toggleNotification(pref)"
              />
            </UiField>
          </UiFieldGroup>
        </UiFieldSet>
      </div>
    </div>
  </main>
</template>
