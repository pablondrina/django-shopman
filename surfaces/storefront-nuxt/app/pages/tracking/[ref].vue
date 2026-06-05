<script setup lang="ts">
import type { Action, TrackingResponse } from '~/types/shopman'
import { operationalCopy, retryAfterDescription } from '~/utils/operationalCopy'

type UiColor = 'neutral' | 'info' | 'success' | 'warning' | 'error'

interface RateLimitRecovery {
  title: string
  detail: string
  retryAfterSeconds: number | null
  retryLabel: string
}

const route = useRoute()
const orderRef = computed(() => String(route.params.ref || ''))
const apiPath = useShopmanApiPath()
const csrfHeaders = useShopmanCsrfHeaders()
const toast = useToast()
const { performReorderAction, pending: reorderPending } = useReorder()

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

const showInitialSkeleton = computed(() => pending.value && !data.value)
const isTerminal = computed(() => data.value ? !data.value.is_active : false)
const fulfillment = computed(() => {
  const current = data.value
  if (!current) return undefined
  return current.is_delivery
    ? current.delivery_fulfillments?.[0] || current.fulfillments?.[0]
    : current.pickup_fulfillments?.[0] || current.fulfillments?.[0]
})
const promiseColor = computed(() => toneToColor(data.value?.promise?.tone))
const statusIcon = computed(() => STATUS_ICONS[data.value?.status || ''] || 'i-lucide-info')
const trackingCopy = computed(() => data.value?.copy || null)
const paymentUrl = computed(() => data.value?.ref ? `/pedido/${encodeURIComponent(data.value.ref)}/pagamento` : null)
const paymentGateUrl = computed(() => data.value?.payment_gate_url || paymentUrl.value)
const promiseActionLink = computed(() => {
  const promise = data.value?.promise
  const action = (promise?.actions || []).find(candidate =>
    candidate.enabled !== false
    && candidate.ref === 'pay_now'
  )
  if (!action) return null
  const url = action.href || (action.ref === 'pay_now' ? paymentGateUrl.value : null)
  if (!url) return null
  const isExternal = action.kind === 'external' || /^https?:\/\//.test(url)
  const isPayment = action.ref.includes('pay')
  const isPickupDirections = action.ref.includes('pickup') || url.includes('google.com/maps')
  return {
    action: action.ref,
    label: action.label,
    url,
    icon: isPayment ? 'i-lucide-credit-card' : isPickupDirections ? 'i-lucide-map-pin' : isExternal ? 'i-lucide-external-link' : 'i-lucide-arrow-right',
    external: isExternal
  }
})
const trackingActions = computed(() => data.value?.actions || [])
const cancelOrderAction = computed(() => findTrackingAction('cancel_order'))
const cancelConfirmation = computed(() => cancelOrderAction.value?.confirmation || {})
const rateOrderAction = computed(() => findTrackingAction('rate_order'))
const mockConfirmPaymentAction = computed(() => findTrackingAction('mock_confirm_payment'))
const reorderAction = computed(() => findTrackingAction('reorder'))
const liveConnected = ref(false)
const cancelOpen = ref(false)
const cancelAcknowledged = ref(false)
const cancelling = ref(false)
const cancelError = ref<string | null>(null)
const cancelRequestId = ref<string | null>(null)
const mockPaymentPending = ref(false)
const nowMs = ref(Date.now())
const rating = ref<number | null>(null)
const ratingComment = ref('')
const ratingPending = ref(false)
const ratingError = ref('')
const ratingRequestId = ref<string | null>(null)
const rateLimitRecovery = ref<RateLimitRecovery | null>(null)

function findTrackingAction (ref: string): Action | null {
  return trackingActions.value.find(action => action.ref === ref && action.enabled !== false) || null
}

function mutationUrl (action: Action | null, fallback: string): string {
  return apiPath(action?.href || fallback)
}

function rateLimitFromFetchError (err: any): RateLimitRecovery | null {
  const payload = err?.data || {}
  const statusCode = err?.statusCode || err?.status || err?.response?.status
  if (statusCode !== 429 && payload.error_code !== 'rate_limited') return null
  const action = Array.isArray(payload.actions) ? payload.actions[0] : null
  return {
    title: payload.title || trackingCopy.value?.rate_limit_title || '',
    detail: payload.detail || operationalCopy.recovery.rateLimit,
    retryAfterSeconds: typeof payload.retry_after_seconds === 'number' ? payload.retry_after_seconds : null,
    retryLabel: action?.label || trackingCopy.value?.retry_label || operationalCopy.recovery.retry
  }
}

const initialRateLimitRecovery = computed(() => rateLimitFromFetchError(error.value))
const activeRateLimitRecovery = computed(() => rateLimitRecovery.value || initialRateLimitRecovery.value)
const errorPayload = computed(() => (error.value as any)?.data || {})
const notFoundTitle = computed(() => String(errorPayload.value?.title || ''))
const notFoundDescription = computed(() => String(errorPayload.value?.detail || ''))

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
  return data.value?.support_url || null
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

const promiseDeadlineValue = computed(() => {
  const countdown = formatCountdown(data.value?.promise?.deadline_at)
  if (!countdown) return ''
  return countdown
})

const promiseRows = computed(() => {
  const rows = [...(data.value?.promise_rows ?? [])]
  if (promiseDeadlineValue.value && data.value?.promise_deadline_label) {
    rows.unshift({
      label: data.value.promise_deadline_label,
      value: promiseDeadlineValue.value,
      url: null
    })
  }
  return rows
})

async function cancelOrder () {
  const action = cancelOrderAction.value
  if (!action || !cancelAcknowledged.value || cancelling.value) return
  cancelling.value = true
  cancelError.value = null
  const requestId = cancelRequestId.value || newRemoteMutationKey('web-cancel')
  cancelRequestId.value = requestId
  try {
    const response = await $fetch<TrackingResponse>(
      mutationUrl(action, `/api/v1/orders/${encodeURIComponent(orderRef.value)}/cancel/`),
      {
        method: action.method || 'POST',
        headers: { ...(await csrfHeaders()), 'Idempotency-Key': requestId },
        credentials: 'include',
        body: { idempotency_key: requestId }
      }
    )
    data.value = response
    cancelOpen.value = false
    cancelAcknowledged.value = false
    cancelRequestId.value = null
    toast.add({
      icon: 'i-lucide-circle-check',
      color: 'success',
      title: data.value?.copy.cancel_success_title || '',
      description: data.value?.copy.cancel_success_message || ''
    })
  } catch (err: any) {
    if (captureRateLimitRecovery(err)) return
    cancelError.value = err?.data?.detail || trackingCopy.value?.cancel_failed_message || ''
  } finally {
    cancelling.value = false
  }
}

async function mockConfirmPayment () {
  const action = mockConfirmPaymentAction.value
  if (!action || mockPaymentPending.value) return
  mockPaymentPending.value = true
  const requestId = newRemoteMutationKey('web-mock-payment')
  try {
    await $fetch<{ redirect_url: string }>(
      mutationUrl(action, `/api/v1/payment/${encodeURIComponent(orderRef.value)}/mock-confirm/`),
      {
        method: action.method || 'POST',
        headers: { ...(await csrfHeaders()), 'Idempotency-Key': requestId },
        credentials: 'include',
        body: { idempotency_key: requestId }
      }
    )
    await refresh()
    toast.add({
      icon: 'i-lucide-circle-check',
      color: 'success',
      title: trackingCopy.value?.mock_payment_success_title || '',
      description: trackingCopy.value?.mock_payment_success_message || ''
    })
  } catch (err: any) {
    if (captureRateLimitRecovery(err)) return
    toast.add({
      icon: 'i-lucide-circle-alert',
      color: 'error',
      title: trackingCopy.value?.mock_payment_failed_title || '',
      description: err?.data?.detail || trackingCopy.value?.mock_payment_failed_message || ''
    })
  } finally {
    mockPaymentPending.value = false
  }
}

async function submitRating () {
  const action = rateOrderAction.value
  if (!action || !rating.value || ratingPending.value) return
  ratingPending.value = true
  ratingError.value = ''
  const requestId = ratingRequestId.value || newRemoteMutationKey('web-rating')
  ratingRequestId.value = requestId
  try {
    const response = await $fetch<TrackingResponse>(mutationUrl(action, `/api/v1/orders/${encodeURIComponent(orderRef.value)}/rate/`), {
      method: action.method || 'POST',
      headers: { ...(await csrfHeaders()), 'Idempotency-Key': requestId },
      credentials: 'include',
      body: {
        rating: rating.value,
        comment: ratingComment.value,
        idempotency_key: requestId
      }
    })
    data.value = response
    ratingRequestId.value = null
    toast.add({ color: 'success', title: trackingCopy.value?.rating_success_title || '' })
  } catch (err: any) {
    if (captureRateLimitRecovery(err)) return
    ratingError.value = err?.data?.detail || trackingCopy.value?.rating_failed_message || ''
  } finally {
    ratingPending.value = false
  }
}

async function reorderFromTracking () {
  const action = reorderAction.value
  const ref = data.value?.ref || orderRef.value
  if (!action || !ref || reorderPending.value) return
  await performReorderAction(action, ref)
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
    cancelRequestId.value = null
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
      eventSource.onopen = () => {
        liveConnected.value = true
        stopPolling()
      }
      eventSource.addEventListener('message', () => { refresh() })
      eventSource.addEventListener('order-update', () => { refresh() })
      eventSource.addEventListener('error', () => {
        liveConnected.value = false
        if (!isTerminal.value) startPolling()
      })
    } catch {
      liveConnected.value = false
      if (!isTerminal.value) startPolling()
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
      startSse()
      startPolling()
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
  title: data.value ? `${data.value.copy.order_ref_label} ${data.value.ref}` : ''
}))
</script>

<template>
  <UContainer class="py-8 sm:py-12" data-pull-refresh @shopman-pull-refresh="refreshAfterGesture">
    <USkeleton v-if="showInitialSkeleton" class="h-80 w-full" />

    <div v-else-if="activeRateLimitRecovery && !data" class="grid gap-3">
      <UAlert
        color="info"
        variant="soft"
        icon="i-lucide-clock"
        :title="activeRateLimitRecovery.title"
        :description="retryAfterDescription(activeRateLimitRecovery.detail, activeRateLimitRecovery.retryAfterSeconds, operationalCopy.recovery.rateLimit)"
      />
      <div class="flex flex-wrap gap-2">
        <UButton :label="activeRateLimitRecovery.retryLabel" icon="i-lucide-refresh-cw" @click="refreshAfterRateLimit" />
        <UButton
          v-if="whatsappHelpUrl && trackingCopy?.support_label"
          :to="whatsappHelpUrl"
          target="_blank"
          rel="noopener"
          :label="trackingCopy?.support_label"
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
      :title="notFoundTitle"
      :description="notFoundDescription"
    />

    <section v-else>
      <div class="shop-soft-panel rounded-lg p-4 sm:p-6">
        <div class="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p class="shop-section-kicker">
              <UIcon :name="statusIcon" class="size-3.5" />
              {{ data.copy.page_kicker }}
            </p>
            <h1 class="mt-2 text-3xl font-bold leading-tight text-highlighted sm:text-4xl">{{ data.copy.order_ref_label }} {{ data.ref }}</h1>
            <p class="mt-2 text-sm leading-relaxed text-muted sm:text-base">
              {{ data.status_label }} · {{ data.total_display }}
            </p>
          </div>
          <div class="flex flex-wrap gap-2">
            <UButton
              v-if="promiseActionLink"
              :label="promiseActionLink.label"
              :to="promiseActionLink.url"
              :icon="promiseActionLink.icon"
              :target="promiseActionLink.external ? '_blank' : undefined"
              :rel="promiseActionLink.external ? 'noopener' : undefined"
              color="warning"
              variant="solid"
            />
            <UButton
              v-if="mockConfirmPaymentAction"
              :label="mockConfirmPaymentAction.label || 'Capturar pagamento teste'"
              icon="i-lucide-credit-card"
              color="warning"
              variant="soft"
              :loading="mockPaymentPending"
              @click="mockConfirmPayment"
            />
            <UButton :label="data.copy.menu_label" to="/menu" icon="i-lucide-store" color="neutral" variant="outline" />
            <UButton
              v-if="whatsappHelpUrl"
              :to="whatsappHelpUrl"
              target="_blank"
              rel="noopener"
              :label="data.copy.support_label"
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
        :description="data.promise?.message || data.copy.promise_fallback_message"
        class="mt-6"
      />

      <UAlert
        v-if="activeRateLimitRecovery"
        color="info"
        variant="soft"
        icon="i-lucide-clock"
        :title="activeRateLimitRecovery.title"
        :description="retryAfterDescription(activeRateLimitRecovery.detail, activeRateLimitRecovery.retryAfterSeconds, operationalCopy.recovery.rateLimit)"
        class="mt-4"
      >
        <template #actions>
          <UButton
            size="xs"
            color="info"
            variant="solid"
            :label="activeRateLimitRecovery.retryLabel"
            icon="i-lucide-refresh-cw"
            @click="refreshAfterRateLimit"
          />
          <UButton
            v-if="whatsappHelpUrl"
            size="xs"
            color="success"
            variant="outline"
            :label="data.copy.support_label"
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
        {{ data.copy.payment_confirmed_notice }}
      </div>

      <div class="mt-6 grid lg:grid-cols-[1fr_360px] gap-6 items-start">
        <UCard class="shop-soft-panel">
          <template #header>
            <div class="flex flex-wrap items-center justify-between gap-3">
              <strong>{{ data.copy.progress_heading }}</strong>
              <UBadge v-if="!isTerminal && liveConnected" color="info" variant="subtle" class="gap-1.5">
                <span class="size-1.5 rounded-full bg-info animate-pulse" />
                {{ data.copy.live_badge }}
              </UBadge>
              <UBadge v-else-if="!isTerminal" color="neutral" variant="subtle">
                {{ data.copy.polling_badge }}
              </UBadge>
              <UBadge v-else color="neutral" variant="subtle">{{ data.copy.finished_badge }}</UBadge>
            </div>
          </template>

          <UTimeline :items="progressItems" />

          <div v-if="data.pickup_info" class="mt-6 rounded-lg border border-default p-4">
            <p class="text-sm font-semibold text-highlighted">{{ data.pickup_info.heading }}</p>
            <p class="mt-1 text-sm text-muted">{{ data.pickup_info.address }}</p>
            <p class="mt-1 text-sm text-muted">{{ data.pickup_info.opening_hours }}</p>
            <UButton
              v-if="data.pickup_info.directions_url"
              :href="data.pickup_info.directions_url"
              external
              :label="data.pickup_info.directions_label"
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
              :label="fulfillment.tracking_label"
              icon="i-lucide-truck"
              color="neutral"
              variant="outline"
              trailing-icon="i-lucide-external-link"
            />
          </div>

        </UCard>

        <UCard variant="subtle" class="shop-soft-panel lg:sticky lg:top-[calc(var(--ui-header-height)+24px)]">
          <template #header>
            <strong>{{ data.copy.items_heading }}</strong>
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
            <span class="font-medium">{{ data.copy.total_label }}</span>
            <strong class="text-xl tabular-nums">{{ data.total_display }}</strong>
          </div>

          <p v-if="data.delivery_fee_display" class="mt-1 text-xs text-muted">
            {{ data.copy.delivery_fee_label }}: {{ data.delivery_fee_display }}
          </p>

          <div class="mt-4 grid gap-2">
            <UBadge v-if="data.payment_status" color="neutral" variant="subtle">
              {{ data.payment_status }}
            </UBadge>
            <UButton
              v-if="promiseActionLink"
              :to="promiseActionLink.url"
              :label="promiseActionLink.label"
              :icon="promiseActionLink.icon"
              color="warning"
              variant="solid"
              block
            />
            <UButton
              v-if="mockConfirmPaymentAction"
              :label="mockConfirmPaymentAction.label || 'Capturar pagamento teste'"
              icon="i-lucide-credit-card"
              color="warning"
              variant="soft"
              block
              :loading="mockPaymentPending"
              @click="mockConfirmPayment"
            />
            <UButton
              v-if="cancelOrderAction"
              :label="cancelOrderAction.label"
              icon="i-lucide-circle-x"
              color="error"
              variant="outline"
              block
              @click="cancelOpen = true"
            />
            <UButton
              v-if="reorderAction"
              :label="reorderAction.label"
              icon="i-lucide-rotate-ccw"
              color="neutral"
              variant="outline"
              block
              :loading="reorderPending"
              @click="reorderFromTracking"
            />
          </div>

          <div v-if="rateOrderAction" class="mt-5 border-t border-default pt-5">
            <p class="text-sm font-semibold text-highlighted">{{ rateOrderAction.label }}</p>
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
              class="mt-3 w-full"
              :rows="3"
              :placeholder="data.copy.rating_comment_placeholder"
              :aria-label="data.copy.rating_comment_aria_label"
            />
            <UAlert v-if="ratingError" color="error" variant="soft" :title="ratingError" class="mt-3" />
            <UButton
              :label="data.copy.rating_submit_label"
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
      :title="String(cancelConfirmation.title || '')"
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
            :title="String(cancelConfirmation.warning_title || '')"
            :description="String(cancelConfirmation.warning_message || cancelConfirmation.message || '')"
          />

          <UCheckbox
            v-model="cancelAcknowledged"
            :label="String(cancelConfirmation.ack_label || '')"
          />

          <UAlert v-if="cancelError" color="error" variant="soft" :title="cancelError" />

          <div class="grid sm:grid-cols-2 gap-3">
            <UButton
              color="neutral"
              variant="outline"
              :label="String(cancelConfirmation.cancel_label || '')"
              block
              @click="cancelOpen = false"
            />
            <UButton
              color="error"
              variant="solid"
              :label="String(cancelConfirmation.confirm_label || cancelOrderAction?.label || '')"
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
