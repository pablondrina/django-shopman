<script setup lang="ts">
import type { TrackingResponse } from '~/types/shopman'

const route = useRoute()
const orderRef = computed(() => String(route.params.ref || ''))
const apiPath = useShopmanApiPath()
const requestHeaders = import.meta.server ? useRequestHeaders(['cookie']) : undefined
const shareCopied = ref(false)
const shareError = ref('')

definePageMeta({
  path: '/pedido/:ref/confirmacao'
})

const { data, pending, error } = await useFetch<TrackingResponse>(
  () => apiPath(`/api/v1/tracking/${encodeURIComponent(orderRef.value)}/`),
  {
    credentials: 'include',
    headers: requestHeaders
  }
)

const paymentUrl = computed(() => data.value?.payment_gate_url || (data.value?.payment_pending ? `/pedido/${encodeURIComponent(orderRef.value)}/pagamento` : null))
const supportUrl = computed(() => data.value?.whatsapp_url || '')
const shareText = computed(() => data.value?.share_text || `Pedido ${orderRef.value}`)

const promiseRows = computed(() => {
  if (!data.value?.promise) return []
  const promise = data.value.promise
  return [
    promise.next_event ? { label: 'Próximo passo', value: promise.next_event } : null,
    promise.recovery ? { label: 'Recuperação', value: promise.recovery } : null,
    promise.active_notification ? { label: 'Aviso', value: promise.active_notification } : null
  ].filter(Boolean)
})

async function shareOrder () {
  shareError.value = ''
  const url = import.meta.client ? window.location.href : ''
  try {
    if (navigator.share) {
      await navigator.share({
        title: `Pedido ${data.value?.ref || orderRef.value}`,
        text: shareText.value,
        url
      })
      return
    }
    await navigator.clipboard.writeText(url ? `${shareText.value}\n${url}` : shareText.value)
    shareCopied.value = true
    window.setTimeout(() => { shareCopied.value = false }, 1800)
  } catch {
    shareError.value = 'Não foi possível compartilhar automaticamente.'
  }
}

useHead(() => ({
  title: data.value ? `Pedido ${data.value.ref} confirmado` : 'Pedido confirmado'
}))
</script>

<template>
  <UContainer class="py-8 sm:py-12">
    <USkeleton v-if="pending" class="h-80 w-full" />
    <UAlert
      v-else-if="error || !data"
      color="error"
      variant="soft"
      title="Pedido não encontrado"
      description="Confira o link ou use o acompanhamento do pedido."
    />
    <section v-else class="grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px] lg:items-start">
      <div class="grid gap-6">
        <UPageCard
          :title="`Pedido ${data.ref}`"
          :description="`${data.status_label} · ${data.total_display}`"
          :ui="{ container: 'p-6 sm:p-8' }"
        >
          <div class="mt-6 flex flex-wrap gap-3">
            <UButton
              v-if="paymentUrl"
              label="Concluir pagamento"
              :to="paymentUrl"
              color="warning"
            />
            <UButton label="Acompanhar pedido" :to="`/tracking/${data.ref}`" color="neutral" variant="outline" />
            <UButton :label="shareCopied ? 'Link copiado' : 'Compartilhar'" icon="i-lucide-share-2" color="neutral" variant="outline" @click="shareOrder" />
            <UButton v-if="supportUrl" label="Falar com suporte" icon="i-lucide-message-circle" :to="supportUrl" target="_blank" rel="noopener" color="neutral" variant="ghost" />
            <UButton label="Cardápio" to="/menu" color="neutral" variant="ghost" />
          </div>
        </UPageCard>

        <UAlert
          :color="data.promise.tone === 'danger' ? 'error' : data.promise.tone === 'warning' ? 'warning' : data.promise.tone === 'success' ? 'success' : 'info'"
          variant="subtle"
          :title="data.promise.title"
          :description="data.promise.message"
        />

        <UCard v-if="promiseRows.length" variant="subtle">
          <div class="grid gap-3 sm:grid-cols-2">
            <div v-for="row in promiseRows" :key="row.label">
              <p class="text-xs font-semibold uppercase text-muted">{{ row.label }}</p>
              <p class="mt-1 text-sm leading-relaxed text-highlighted">{{ row.value }}</p>
            </div>
          </div>
        </UCard>

        <UAlert
          v-if="shareError"
          color="warning"
          variant="soft"
          :title="shareError"
          description="Use o acompanhamento do pedido para copiar o link quando precisar."
        />
      </div>

      <UCard class="lg:sticky lg:top-[calc(var(--ui-header-height)+24px)]">
        <template #header>
          <strong>Resumo</strong>
        </template>
        <div class="grid gap-2">
          <div
            v-for="line in data.items"
            :key="line.sku"
            class="flex justify-between gap-3 text-sm"
          >
            <span class="min-w-0 truncate text-muted">{{ line.qty }}× {{ line.name }}</span>
            <span class="shrink-0 tabular-nums">{{ line.total_display }}</span>
          </div>
        </div>
        <USeparator class="my-3" />
        <div class="flex items-baseline justify-between gap-4">
          <span class="font-medium">Total</span>
          <strong class="text-xl tabular-nums">{{ data.total_display }}</strong>
        </div>
        <p v-if="data.eta_display" class="mt-2 text-sm text-muted">{{ data.eta_display }}</p>
      </UCard>
    </section>
  </UContainer>
</template>
