<script setup lang="ts">
import type { TrackingResponse } from '~/types/shopman'

type UiColor = 'neutral' | 'info' | 'success' | 'warning' | 'error'

interface RateLimitRecovery {
  detail: string
  retryAfterSeconds: number | null
}

const route = useRoute()
const orderRef = computed(() => String(route.params.ref || ''))
const apiPath = useShopmanApiPath()
const csrfHeaders = useShopmanCsrfHeaders()
const { shop } = useShopSession()
const toast = useToast()

const { data, pending, error, refresh } = await useFetch<TrackingResponse>(
  () => apiPath(`/api/v1/tracking/${encodeURIComponent(orderRef.value)}/`),
  { credentials: 'include' }
)

const STATUS_ICONS: Record<string, string> = {
  new: 'i-lucide-receipt-text',
  created: 'i-lucide-receipt-text',
  confirmed: 'i-lucide-circle-check',
  preparing: 'i-lucide-flame',
  ready: 'i-lucide-package-check',
  dispatched: 'i-lucide-truck',
  delivered: 'i-lucide-package-check',
  completed: 'i-lucide-check-circle-2',
  cancelled: 'i-lucide-circle-x',
  returned: 'i-lucide-undo-2',
  'payment.captured': 'i-lucide-credit-card',
  'payment.refunded': 'i-lucide-rotate-ccw',
  'fulfillment.dispatched': 'i-lucide-truck',
  'fulfillment.delivered': 'i-lucide-package-check'
}

function toneToColor (tone?: string): UiColor {
  if (tone === 'danger' || tone === 'error') return 'error'
  if (tone === 'warning') return 'warning'
  if (tone === 'success') return 'success'
  if (tone === 'info') return 'info'
  return 'neutral'
}

function stepIcon (key: string, state: string) {
  if (state === 'cancelled') return 'i-lucide-circle-x'
  if (state === 'completed') return 'i-lucide-check-circle-2'
  if (state === 'current') return STATUS_ICONS[key] || 'i-lucide-circle-dot'
  return 'i-lucide-circle'
}

const progressItems = computed(() => (data.value?.progress_steps ?? []).map(step => ({
  date: step.timestamp_display || '',
  title: step.label,
  icon: stepIcon(step.key, step.state),
  color: step.state === 'cancelled' ? 'error' : step.state === 'pending' ? 'neutral' : 'primary'
})))

const timelineItems = computed(() => (data.value?.timeline ?? []).map(event => ({
  date: event.timestamp_display,
  title: event.label,
  icon: STATUS_ICONS[event.event_type] || 'i-lucide-circle-dot'
})))

const isTerminal = computed(() => data.value ? !data.value.is_active : false)
const isReady = computed(() => data.value?.status === 'ready')
const fulfillment = computed(() => data.value?.fulfillments?.[0])
const promiseColor = computed(() => toneToColor(data.value?.promise?.tone))
const statusIcon = computed(() => STATUS_ICONS[data.value?.status || ''] || 'i-lucide-info')
const paymentUrl = computed(() => data.value?.ref ? `/pedido/${encodeURIComponent(data.value.ref)}/pagamento` : null)
const paymentGateUrl = computed(() => data.value?.payment_gate_url || paymentUrl.value)
const liveConnected = ref(false)
const cancelOpen = ref(false)
const cancelAcknowledged = ref(false)
const cancelling = ref(false)
const cancelError = ref<string | null>(null)
const nowMs = ref(Date.now())
const rating = ref<number | null>(null)
const ratingComment = ref('')
const ratingPending = ref(false)
const ratingError = ref('')
const rateLimitRecovery = ref<RateLimitRecovery | null>(null)

function rateLimitFromFetchError (err: any): RateLimitRecovery | null {
  const payload = err?.data || {}
  const statusCode = err?.statusCode || err?.status || err?.response?.status
  if (statusCode !== 429 && payload.error_code !== 'rate_limited') return null
  return {
    detail: payload.detail || operationalCopy.recovery.rateLimit,
    retryAfterSeconds: typeof payload.retry_after_seconds === 'number' ? payload.retry_after_seconds : null
  }
}

const initialRateLimitRecovery = computed(() => rateLimitFromFetchError(error.value))
const activeRateLimitRecovery = computed(() => rateLimitRecovery.value || initialRateLimitRecovery.value)

function captureRateLimitRecovery (err: any): boolean {
  const recovery = rateLimitFromFetchError(err)
  if (!recovery) return false
  rateLimitRecovery.value = recovery
  return true
}

async function enforcePaymentGate () {
  if (!data.value?.requires_payment_gate || !paymentGateUrl.value) return
  await navigateTo(paymentGateUrl.value, { replace: true })
}

await enforcePaymentGate()

watch(() => data.value?.requires_payment_gate, () => {
  void enforcePaymentGate()
})

const whatsappHelpUrl = computed(() => {
  const base = data.value?.whatsapp_url || shop.value?.whatsapp_url
  if (!base) return null
  const message = `Oi! Posso ajudar com o pedido ${orderRef.value}?`
  const sep = base.includes('?') ? '&' : '?'
  return `${base}${sep}text=${encodeURIComponent(message)}`
})

function formatCountdown (deadline: string | null | undefined) {
  if (!deadline) return ''
  const target = new Date(deadline).getTime()
  if (Number.isNaN(target)) return ''
  const diff = Math.max(0, target - nowMs.value)
  const minutes = Math.floor(diff / 60_000)
  const seconds = Math.floor((diff % 60_000) / 1000)
  if (minutes >= 60) {
    const hours = Math.floor(minutes / 60)
    const rest = minutes % 60
    return `${hours}h ${String(rest).padStart(2, '0')}min`
  }
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
}

const promiseDeadlineLabel = computed(() => {
  const countdown = formatCountdown(data.value?.promise?.deadline_at)
  if (!countdown) return ''
  if (data.value?.promise?.timer_mode === 'countdown') return `Prazo: ${countdown}`
  return `Referência: ${countdown}`
})

const promiseRows = computed(() => {
  const p = data.value?.promise
  if (!p) return []
  return [
    promiseDeadlineLabel.value ? { label: 'Prazo', value: promiseDeadlineLabel.value } : null,
    p.next_event ? { label: 'Próximo passo', value: p.next_event } : null,
    p.customer_action_label ? { label: 'Ação necessária', value: p.customer_action_label, url: p.customer_action_url } : null,
    p.recovery ? { label: 'Recuperação', value: p.recovery } : null,
    p.active_notification ? { label: 'Aviso ativo', value: p.active_notification } : null,
    data.value?.last_updated_display ? { label: 'Última atualização', value: data.value.last_updated_display } : null
  ].filter(Boolean)
})

async function cancelOrder () {
  if (!data.value?.can_cancel || !cancelAcknowledged.value || cancelling.value) return
  cancelling.value = true
  cancelError.value = null
  try {
    const response = await $fetch<TrackingResponse>(
      apiPath(`/api/v1/orders/${encodeURIComponent(orderRef.value)}/cancel/`),
      { method: 'POST', headers: await csrfHeaders(), credentials: 'include' }
    )
    data.value = response
    cancelOpen.value = false
    cancelAcknowledged.value = false
    toast.add({
      icon: 'i-lucide-circle-check',
      color: 'success',
      title: 'Pedido cancelado',
      description: 'A casa recebeu o cancelamento. Acompanhe o status nesta página.'
    })
  } catch (err: any) {
    if (captureRateLimitRecovery(err)) return
    cancelError.value = err?.data?.detail || 'Não foi possível cancelar este pedido agora.'
  } finally {
    cancelling.value = false
  }
}

async function submitRating () {
  if (!data.value?.can_rate || !rating.value || ratingPending.value) return
  ratingPending.value = true
  ratingError.value = ''
  try {
    await $fetch(data.value.rating_url ? apiPath(data.value.rating_url) : apiPath(`/api/v1/orders/${encodeURIComponent(orderRef.value)}/rate/`), {
      method: 'POST',
      headers: await csrfHeaders(),
      credentials: 'include',
      body: {
        rating: rating.value,
        comment: ratingComment.value
      }
    })
    data.value = {
      ...data.value,
      can_rate: false,
      rating_url: null
    }
    toast.add({ color: 'success', title: 'Avaliação registrada' })
  } catch (err: any) {
    if (captureRateLimitRecovery(err)) return
    ratingError.value = err?.data?.detail || 'Não foi possível registrar a avaliação agora.'
  } finally {
    ratingPending.value = false
  }
}

async function refreshAfterRateLimit () {
  rateLimitRecovery.value = null
  await refresh()
}

async function refreshAfterGesture () {
  rateLimitRecovery.value = null
  await refresh()
}

watch(cancelOpen, (open) => {
  if (!open) {
    cancelAcknowledged.value = false
    cancelError.value = null
  }
})

if (import.meta.client) {
  let pollTimer: ReturnType<typeof setInterval> | null = null
  let clockTimer: ReturnType<typeof setInterval> | null = null
  let eventSource: EventSource | null = null

  function startPolling () {
    stopPolling()
    const staleSeconds = data.value?.stale_after_seconds || 45
    const intervalMs = Math.max(10_000, Math.min(staleSeconds * 1000, 60_000))
    pollTimer = setInterval(() => { refresh() }, intervalMs)
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
      eventSource.onopen = () => { liveConnected.value = true }
      eventSource.addEventListener('message', () => { refresh() })
      eventSource.addEventListener('order-update', () => { refresh() })
      eventSource.addEventListener('error', () => {
        liveConnected.value = false
      })
    } catch {
      liveConnected.value = false
    }
  }
  function stopSse () {
    if (eventSource) {
      eventSource.close()
      eventSource = null
    }
    liveConnected.value = false
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
    if (clockTimer) clearInterval(clockTimer)
  })

  onMounted(() => {
    clockTimer = setInterval(() => {
      nowMs.value = Date.now()
    }, 1000)
  })
}

useHead(() => ({
  title: data.value ? `Pedido ${data.value.ref}` : 'Pedido'
}))
</script>

<template>
  <UContainer class="py-8 sm:py-12" data-pull-refresh @shopman-pull-refresh="refreshAfterGesture">
    <USkeleton v-if="pending" class="h-80 w-full" />

    <div v-else-if="activeRateLimitRecovery && !data" class="grid gap-3">
      <UAlert
        color="info"
        variant="soft"
        icon="i-lucide-clock"
        title="Aguarde um instante"
        :description="retryAfterDescription(activeRateLimitRecovery.detail, activeRateLimitRecovery.retryAfterSeconds)"
      />
      <div class="flex flex-wrap gap-2">
        <UButton label="Tentar novamente" icon="i-lucide-refresh-cw" @click="refreshAfterRateLimit" />
        <UButton
          v-if="whatsappHelpUrl"
          :to="whatsappHelpUrl"
          target="_blank"
          rel="noopener"
          label="Falar com a casa"
          icon="i-lucide-message-circle"
          color="success"
          variant="soft"
        />
      </div>
    </div>

    <UAlert
      v-else-if="(error && !activeRateLimitRecovery) || !data"
      color="error"
      variant="soft"
      title="Pedido não encontrado"
      description="Confira o link do pedido ou fale com a casa."
    />

    <section v-else>
      <div class="shop-soft-panel rounded-lg p-4 sm:p-6">
        <div class="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p class="shop-section-kicker">
              <UIcon :name="statusIcon" class="size-3.5" />
              Acompanhamento
            </p>
            <h1 class="mt-2 text-3xl font-bold leading-tight text-highlighted sm:text-4xl">Pedido {{ data.ref }}</h1>
            <p class="mt-2 text-sm leading-relaxed text-muted sm:text-base">
              {{ data.status_label }} · {{ data.total_display }}
            </p>
          </div>
          <div class="flex flex-wrap gap-2">
            <UButton
              v-if="data.payment_pending && paymentUrl"
              label="Pagar pedido"
              :to="paymentUrl"
              icon="i-lucide-credit-card"
              color="warning"
              variant="solid"
            />
            <UButton label="Cardápio" to="/menu" icon="i-lucide-store" color="neutral" variant="outline" />
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
          </div>
        </div>
      </div>

      <UAlert
        :color="promiseColor"
        variant="subtle"
        :icon="statusIcon"
        :title="data.promise?.title || data.status_label"
        :description="data.promise?.message || 'Acompanhando atualizações do pedido.'"
        class="mt-6"
      />

      <UAlert
        v-if="activeRateLimitRecovery"
        color="info"
        variant="soft"
        icon="i-lucide-clock"
        title="Atualização pausada por um instante"
        :description="retryAfterDescription(activeRateLimitRecovery.detail, activeRateLimitRecovery.retryAfterSeconds)"
        class="mt-4"
      >
        <template #actions>
          <UButton
            size="xs"
            color="info"
            variant="solid"
            label="Tentar novamente"
            icon="i-lucide-refresh-cw"
            @click="refreshAfterRateLimit"
          />
          <UButton
            v-if="whatsappHelpUrl"
            size="xs"
            color="success"
            variant="outline"
            label="Falar com a casa"
            icon="i-lucide-message-circle"
            :to="whatsappHelpUrl"
            target="_blank"
            rel="noopener"
          />
        </template>
      </UAlert>

      <UCard v-if="promiseRows.length" class="mt-4" :ui="{ body: 'p-4 sm:p-5' }">
        <div class="grid gap-3 sm:grid-cols-2">
          <div
            v-for="row in promiseRows"
            :key="row.label"
            class="min-w-0"
          >
            <p class="text-xs font-semibold uppercase text-muted">{{ row.label }}</p>
            <UButton
              v-if="row.url"
              :to="row.url"
              color="neutral"
              variant="link"
              class="mt-1 justify-start p-0 text-left"
            >
              {{ row.value }}
            </UButton>
            <p v-else class="mt-1 break-words text-sm leading-relaxed text-highlighted">{{ row.value }}</p>
          </div>
        </div>
      </UCard>

      <div
        v-if="data.show_payment_confirmed_notice"
        class="mt-4 rounded-lg border border-success/30 bg-success/10 p-4 text-sm text-success"
      >
        Pagamento confirmado. Acompanhe o próximo passo nesta página.
      </div>

      <div class="mt-6 grid lg:grid-cols-[1fr_360px] gap-6 items-start">
        <UCard class="shop-soft-panel">
          <template #header>
            <div class="flex flex-wrap items-center justify-between gap-3">
              <strong>Progresso</strong>
              <UBadge v-if="!isTerminal && liveConnected" color="info" variant="subtle" class="gap-1.5">
                <span class="size-1.5 rounded-full bg-info animate-pulse" />
                Ao vivo
              </UBadge>
              <UBadge v-else-if="!isTerminal" color="neutral" variant="subtle">
                Atualização periódica
              </UBadge>
              <UBadge v-else color="neutral" variant="subtle">Finalizado</UBadge>
            </div>
          </template>

          <UTimeline v-if="progressItems.length" :items="progressItems" />
          <UTimeline v-else :items="timelineItems" />

          <UAlert
            v-if="isReady"
            color="success"
            variant="soft"
            icon="i-lucide-package-check"
            title="Tudo pronto!"
            description="Seu pedido está pronto para retirada ou para sair em entrega."
            class="mt-6"
          />

          <div v-if="data.pickup_info" class="mt-6 rounded-lg border border-default p-4">
            <p class="text-sm font-semibold text-highlighted">Retirada</p>
            <p class="mt-1 text-sm text-muted">{{ data.pickup_info.address }}</p>
            <p class="mt-1 text-sm text-muted">{{ data.pickup_info.opening_hours }}</p>
            <UButton
              v-if="data.pickup_info.google_maps_url"
              :to="data.pickup_info.google_maps_url"
              target="_blank"
              rel="noopener"
              label="Abrir mapa"
              icon="i-lucide-map-pin"
              color="neutral"
              variant="outline"
              size="sm"
              class="mt-3"
            />
          </div>

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

          <div v-if="timelineItems.length" class="mt-8">
            <h2 class="text-sm font-semibold text-highlighted">Eventos do pedido</h2>
            <UTimeline :items="timelineItems" class="mt-3" />
          </div>
        </UCard>

        <UCard variant="subtle" class="shop-soft-panel lg:sticky lg:top-[calc(var(--ui-header-height)+24px)]">
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

          <p v-if="data.delivery_fee_display" class="mt-1 text-xs text-muted">
            Entrega: {{ data.delivery_fee_display }}
          </p>

          <div class="mt-4 grid gap-2">
            <UBadge v-if="data.payment_status" color="neutral" variant="subtle">
              {{ data.payment_status }}
            </UBadge>
            <UButton
              v-if="data.payment_pending && paymentUrl"
              :to="paymentUrl"
              label="Concluir pagamento"
              icon="i-lucide-credit-card"
              color="warning"
              variant="solid"
              block
            />
            <UButton
              v-if="data.can_cancel"
              label="Cancelar pedido"
              icon="i-lucide-circle-x"
              color="error"
              variant="outline"
              block
              @click="cancelOpen = true"
            />
          </div>

          <div v-if="data.can_rate" class="mt-5 border-t border-default pt-5">
            <p class="text-sm font-semibold text-highlighted">Avaliar pedido</p>
            <div class="mt-3 grid grid-cols-5 gap-2">
              <button
                v-for="score in [1, 2, 3, 4, 5]"
                :key="score"
                type="button"
                class="rounded-md border px-2 py-2 text-sm font-semibold transition-colors"
                :class="rating === score ? 'border-primary bg-primary text-inverted' : 'border-default bg-default text-muted hover:text-highlighted'"
                @click="rating = score"
              >
                {{ score }}
              </button>
            </div>
            <UTextarea
              v-model="ratingComment"
              class="mt-3"
              :rows="3"
              placeholder="Comentário opcional"
              aria-label="Comentário da avaliação"
            />
            <UAlert v-if="ratingError" color="error" variant="soft" :title="ratingError" class="mt-3" />
            <UButton
              label="Enviar avaliação"
              block
              class="mt-3"
              :disabled="!rating"
              :loading="ratingPending"
              @click="submitRating"
            />
          </div>
        </UCard>
      </div>
    </section>

    <UModal v-model:open="cancelOpen"
      title="Cancelar pedido"
      :ui="{ content: 'max-w-lg' }"
      data-swipe-dismiss
      @shopman-swipe-dismiss="cancelOpen = false"
    >
      <template #body>
        <div class="grid gap-4">
          <UAlert
            color="warning"
            variant="soft"
            icon="i-lucide-triangle-alert"
            title="Essa ação altera o pedido em andamento"
            description="O cancelamento só é permitido enquanto o pagamento não foi capturado e a loja ainda permite reversão."
          />

          <UCheckbox
            v-model="cancelAcknowledged"
            label="Entendo que o pedido será cancelado e que a casa deixará de prepará-lo."
          />

          <UAlert v-if="cancelError" color="error" variant="soft" :title="cancelError" />

          <div class="grid sm:grid-cols-2 gap-3">
            <UButton
              color="neutral"
              variant="outline"
              label="Manter pedido"
              block
              @click="cancelOpen = false"
            />
            <UButton
              color="error"
              variant="solid"
              label="Cancelar pedido"
              icon="i-lucide-circle-x"
              block
              :loading="cancelling"
              :disabled="!cancelAcknowledged"
              data-haptic="confirm"
              @click="cancelOrder"
            />
          </div>
        </div>
      </template>
    </UModal>
  </UContainer>
</template>
