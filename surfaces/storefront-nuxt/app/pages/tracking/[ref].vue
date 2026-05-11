<script setup lang="ts">
import type { TrackingResponse } from '~/types/shopman'

const route = useRoute()
const orderRef = computed(() => String(route.params.ref || ''))
const apiPath = useShopmanApiPath()
const { shop } = useShopSession()

const { data, pending, error, refresh } = await useFetch<TrackingResponse>(
  () => apiPath(`/api/v1/tracking/${encodeURIComponent(orderRef.value)}/`),
  { credentials: 'include' }
)

const STATUS_ICONS: Record<string, string> = {
  created: 'i-lucide-receipt-text',
  confirmed: 'i-lucide-circle-check',
  in_production: 'i-lucide-flame',
  ready: 'i-lucide-package-check',
  fulfilled: 'i-lucide-check-circle-2',
  delivered: 'i-lucide-truck',
  cancelled: 'i-lucide-circle-x'
}

const TERMINAL_STATUSES = new Set(['fulfilled', 'delivered', 'cancelled'])

const timelineItems = computed(() => (data.value?.timeline ?? []).map(event => ({
  date: event.timestamp_display,
  title: event.label,
  icon: STATUS_ICONS[event.event_type] || 'i-lucide-circle-dot'
})))

const isTerminal = computed(() => data.value?.status ? TERMINAL_STATUSES.has(data.value.status) : false)
const isReady = computed(() => data.value?.status === 'ready')
const fulfillment = computed(() => data.value?.fulfillments?.[0])

const statusCopy = computed(() => {
  switch (data.value?.status) {
    case 'created':
    case 'confirmed':
      return { tone: 'info' as const, message: 'Recebemos seu pedido. Logo a casa começa a preparar.' }
    case 'in_production':
      return { tone: 'warning' as const, message: 'Tá no forno! Logo logo fica pronto.' }
    case 'ready':
      return { tone: 'success' as const, message: 'Pronto pra retirar/sair pra entrega. A casa te avisa quando despachar.' }
    case 'fulfilled':
    case 'delivered':
      return { tone: 'success' as const, message: 'Pedido entregue. Volte sempre!' }
    case 'cancelled':
      return { tone: 'error' as const, message: 'Pedido cancelado. Se precisar, fale com a casa.' }
    default:
      return { tone: 'info' as const, message: 'Acompanhando seu pedido em tempo real.' }
  }
})

const whatsappHelpUrl = computed(() => {
  const base = shop.value?.whatsapp_url
  if (!base) return null
  const message = `Oi! Posso ajudar com o pedido ${orderRef.value}?`
  const sep = base.includes('?') ? '&' : '?'
  return `${base}${sep}text=${encodeURIComponent(message)}`
})

if (import.meta.client) {
  let pollTimer: ReturnType<typeof setInterval> | null = null
  let eventSource: EventSource | null = null

  function startPolling () {
    stopPolling()
    pollTimer = setInterval(() => { refresh() }, 10_000)
  }
  function stopPolling () {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  function startSse () {
    stopSse()
    if (!orderRef.value) return
    try {
      const url = apiPath(`/pedido/${encodeURIComponent(orderRef.value)}/events`)
      eventSource = new EventSource(url, { withCredentials: true })
      eventSource.addEventListener('message', () => { refresh() })
      eventSource.addEventListener('order-update', () => { refresh() })
      eventSource.addEventListener('error', () => {
        // upstream may close; polling fallback continues
      })
    } catch {
      // EventSource not supported — polling continues
    }
  }
  function stopSse () {
    if (eventSource) {
      eventSource.close()
      eventSource = null
    }
  }

  watch(isTerminal, (terminal) => {
    if (!terminal) {
      startPolling()
      startSse()
    } else {
      stopPolling()
      stopSse()
    }
  }, { immediate: true })

  onBeforeUnmount(() => {
    stopPolling()
    stopSse()
  })
}

useHead(() => ({
  title: data.value ? `Pedido ${data.value.ref}` : 'Pedido'
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
      description="Confira o link do pedido ou fale com a casa."
    />

    <section v-else>
      <UPageHeader :title="`Pedido ${data.ref}`">
        <template #description>
          {{ data.status_label }} · {{ data.total_display }}
        </template>
        <template #links>
          <UButton label="Cardápio" to="/menu" icon="i-lucide-store" color="neutral" variant="ghost" />
          <UButton
            v-if="whatsappHelpUrl"
            :to="whatsappHelpUrl"
            target="_blank"
            rel="noopener"
            label="Ajuda"
            icon="i-lucide-message-circle"
            color="success"
            variant="soft"
          />
        </template>
      </UPageHeader>

      <UAlert
        :color="statusCopy.tone"
        variant="subtle"
        :icon="STATUS_ICONS[data.status] || 'i-lucide-info'"
        :title="data.status_label"
        :description="statusCopy.message"
        class="mt-6"
      />

      <div class="mt-6 grid lg:grid-cols-[1fr_360px] gap-6 items-start">
        <UCard>
          <template #header>
            <div class="flex items-center justify-between">
              <strong>Linha do tempo</strong>
              <UBadge v-if="!isTerminal" color="info" variant="subtle" class="gap-1.5">
                <span class="size-1.5 rounded-full bg-info animate-pulse" />
                Atualizando ao vivo
              </UBadge>
              <UBadge v-else color="neutral" variant="subtle">Finalizado</UBadge>
            </div>
          </template>

          <UTimeline :items="timelineItems" />

          <UAlert
            v-if="isReady"
            color="success"
            variant="soft"
            icon="i-lucide-package-check"
            title="Tudo pronto!"
            description="Seu pedido está pronto para retirada. A casa aguarda você."
            class="mt-6"
          />

          <div v-if="fulfillment?.tracking_url" class="mt-6">
            <UButton
              :to="fulfillment.tracking_url"
              target="_blank"
              rel="noopener"
              :label="fulfillment.carrier ? `Acompanhar via ${fulfillment.carrier}` : 'Acompanhar entrega'"
              icon="i-lucide-truck"
              color="neutral"
              variant="outline"
              trailing-icon="i-lucide-external-link"
            />
          </div>
        </UCard>

        <UCard variant="subtle" class="lg:sticky lg:top-[calc(var(--ui-header-height)+24px)]">
          <template #header>
            <strong>Itens</strong>
          </template>

          <div class="grid gap-2">
            <div
              v-for="line in data.items"
              :key="line.sku"
              class="flex justify-between gap-3"
            >
              <span class="text-sm text-muted truncate">{{ line.qty }}× {{ line.name }}</span>
              <span class="text-sm whitespace-nowrap tabular-nums">{{ line.total_display }}</span>
            </div>
          </div>

          <USeparator class="my-3" />

          <div class="flex justify-between items-baseline">
            <span class="font-medium">Total</span>
            <strong class="text-xl tabular-nums">{{ data.total_display }}</strong>
          </div>

          <UBadge v-if="data.payment_status" color="neutral" variant="subtle" class="mt-3">
            {{ data.payment_status }}
          </UBadge>
        </UCard>
      </div>
    </section>
  </UContainer>
</template>
