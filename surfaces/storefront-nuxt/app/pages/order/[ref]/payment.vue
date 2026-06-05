<script setup lang="ts">
import type { PaymentPromiseProjection, PaymentResponse, PaymentStatusResponse, Action } from '~/types/shopman'

interface PaymentErrorPayload {
  detail?: string
  error_code?: string
  retry_after_seconds?: number
}

const route = useRoute()
const apiPath = useShopmanApiPath()
const csrfHeaders = useShopmanCsrfHeaders()
const orderRef = computed(() => String(route.params.ref || ''))
const requestHeaders = import.meta.server ? useRequestHeaders(['cookie']) : undefined

definePageMeta({
  path: '/pedido/:ref/pagamento'
})

const { data, pending, error, refresh } = await useFetch<PaymentResponse>(
  () => apiPath(`/api/v1/payment/${encodeURIComponent(orderRef.value)}/`),
  {
    credentials: 'include',
    headers: requestHeaders
  }
)

const paymentStatus = ref<PaymentStatusResponse | null>(null)
const copied = ref(false)
const copyError = ref('')
const actionPending = ref(false)
const pollFailures = ref(0)
const statusError = ref('')
const rateLimitRecovery = ref<{ detail: string, retryAfterSeconds: number | null } | null>(null)
const lastStatusCheckedAt = ref('')
const pixQrCodeFailed = ref(false)

const payment = computed(() => data.value?.payment || null)
const promise = computed(() => paymentStatus.value?.promise || payment.value?.promise || null)
const trackingUrl = computed(() => payment.value?.tracking_url || (orderRef.value ? `/tracking/${orderRef.value}` : null))
const pixQrCodeSource = computed(() => payment.value?.pix_qr_code || '')
const paymentActions = computed(() => payment.value?.actions || [])
const mockConfirmPaymentAction = computed(() =>
  paymentActions.value.find(action => action.ref === 'mock_confirm_payment' && action.enabled !== false) || null
)

function actionablePaymentActions (paymentPromise?: PaymentPromiseProjection | null): Action[] {
  return (paymentPromise?.actions || []).filter(action =>
    action.enabled !== false
    && action.ref !== 'track_order'
  )
}

const activePaymentActions = computed(() => actionablePaymentActions(promise.value))
const hasPendingPaymentAction = computed(() => activePaymentActions.value.length > 0)
const redirectAction = computed(() =>
  activePaymentActions.value.find(action =>
    action.kind === 'external'
    || action.ref === 'authorize_card'
    || action.ref === 'pay_card'
  ) || null
)
const redirectUrl = computed(() => data.value?.redirect_url || (!hasPendingPaymentAction.value ? trackingUrl.value : null) || null)
const canRedirectToCardCheckout = computed(() => {
  const currentPayment = payment.value
  const action = redirectAction.value
  return Boolean(
    currentPayment?.method === 'card'
    && action
    && (action.href || currentPayment.checkout_url)
  )
})
const hasRenderablePixQrCode = computed(() => isRenderablePixQrCode(pixQrCodeSource.value))
const shouldShowPixQrCode = computed(() => Boolean(hasRenderablePixQrCode.value && !pixQrCodeFailed.value))
const initialRateLimitRecovery = computed(() => {
  const payload = (error.value?.data || {}) as PaymentErrorPayload
  const statusCode = (error.value as any)?.statusCode || (error.value as any)?.status
  if (statusCode !== 429 && payload.error_code !== 'rate_limited') return null
  return {
    detail: payload.detail || operationalCopy.recovery.rateLimit,
    retryAfterSeconds: typeof payload.retry_after_seconds === 'number' ? payload.retry_after_seconds : null
  }
})
const activeRateLimitRecovery = computed(() => rateLimitRecovery.value || initialRateLimitRecovery.value)
const toneColor = computed(() => {
  const tone = promise.value?.tone
  if (tone === 'danger') return 'error'
  if (tone === 'warning') return 'warning'
  if (tone === 'success') return 'success'
  return 'info'
})

function formatDeadline (deadline: string | null | undefined) {
  if (!deadline) return ''
  const date = new Date(deadline)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

function statusCodeFromError (err: any): number | null {
  return err?.response?.status || err?.statusCode || err?.status || null
}

function mutationUrl (action: Action, fallback: string): string {
  return apiPath(action.href || fallback)
}

function rateLimitFromError (err: any) {
  const payload = (err?.data || {}) as PaymentErrorPayload
  const statusCode = statusCodeFromError(err)
  if (statusCode !== 429 && payload.error_code !== 'rate_limited') return false
  rateLimitRecovery.value = {
    detail: payload.detail || operationalCopy.recovery.rateLimit,
    retryAfterSeconds: typeof payload.retry_after_seconds === 'number' ? payload.retry_after_seconds : null
  }
  statusError.value = ''
  return true
}

function markStatusChecked () {
  lastStatusCheckedAt.value = new Date().toLocaleTimeString('pt-BR', {
    hour: '2-digit',
    minute: '2-digit'
  })
}

const paymentDetails = computed(() => {
  const p = promise.value
  if (!p) return []
  return [
    p.deadline_at ? { label: 'Prazo', value: formatDeadline(p.deadline_at) } : null,
    p.next_event ? { label: 'Próximo passo', value: p.next_event } : null,
    p.recovery ? { label: 'Recuperação', value: p.recovery } : null,
    p.active_notification ? { label: 'Aviso ativo', value: p.active_notification } : null,
    p.stale_after_seconds ? { label: 'Atualização', value: `${operationalCopy.payment.statusStalePrefix} ${p.stale_after_seconds} segundos.` } : null
  ].filter(Boolean)
})

watch(redirectUrl, (next) => {
  if (next) void navigateTo(next)
}, { immediate: true })

watch(pixQrCodeSource, () => {
  pixQrCodeFailed.value = false
})

function markPixQrCodeFailed () {
  pixQrCodeFailed.value = true
}

function isRenderablePixQrCode (source: string) {
  if (!source) return false
  if (!source.startsWith('data:')) return true
  const commaIndex = source.indexOf(',')
  if (commaIndex === -1) return false
  const metadata = source.slice(0, commaIndex)
  const payload = source.slice(commaIndex + 1).trim()
  if (!payload) return false
  if (metadata.includes(';base64')) return payload.length >= 128
  return payload.length >= 32
}

async function copyPix () {
  const code = payment.value?.pix_copy_paste
  if (!code) return
  copyError.value = ''
  try {
    await navigator.clipboard.writeText(code)
  } catch {
    try {
      const textarea = document.createElement('textarea')
      textarea.value = code
      textarea.setAttribute('readonly', 'true')
      textarea.style.position = 'fixed'
      textarea.style.opacity = '0'
      document.body.appendChild(textarea)
      textarea.select()
      const didCopy = document.execCommand('copy')
      document.body.removeChild(textarea)
      if (!didCopy) throw new Error('copy failed')
    } catch {
      copyError.value = operationalCopy.payment.manualPix
      return
    }
  }
  copied.value = true
  window.setTimeout(() => { copied.value = false }, 1800)
}

async function pollStatus () {
  if (!payment.value) return
  statusError.value = ''
  rateLimitRecovery.value = null
  try {
    const statusUrl = payment.value.status_url || `/api/v1/payment/${encodeURIComponent(orderRef.value)}/status/`
    const status = await $fetch<PaymentStatusResponse>(apiPath(statusUrl), {
      credentials: 'include'
    })
    paymentStatus.value = status
    pollFailures.value = 0
    markStatusChecked()
    if ((status.should_redirect || status.is_terminal || actionablePaymentActions(status.promise).length === 0) && status.redirect_url) {
      await navigateTo(status.redirect_url)
    }
  } catch (err: any) {
    if (rateLimitFromError(err)) return
    pollFailures.value += 1
    if (pollFailures.value >= 2) {
      statusError.value = operationalCopy.payment.automaticStatusFailed
    }
  }
}

async function refreshPayment () {
  statusError.value = ''
  rateLimitRecovery.value = null
  await refresh()
}

async function mockConfirm () {
  const action = mockConfirmPaymentAction.value
  if (!action || actionPending.value) return
  actionPending.value = true
  const requestId = newRemoteMutationKey('web-payment-mock-confirm')
  try {
    const response = await $fetch<{ redirect_url: string }>(
      mutationUrl(action, `/api/v1/payment/${encodeURIComponent(orderRef.value)}/mock-confirm/`),
      {
        method: action.method || 'POST',
        headers: { ...(await csrfHeaders()), 'Idempotency-Key': requestId },
        credentials: 'include',
        body: { idempotency_key: requestId }
      }
    )
    await navigateTo(response.redirect_url || trackingUrl.value || `/tracking/${orderRef.value}`)
  } catch (err: any) {
    if (!rateLimitFromError(err)) {
      statusError.value = operationalCopy.payment.mockConfirmFailed
    }
  } finally {
    actionPending.value = false
  }
}

let pollTimer: ReturnType<typeof setInterval> | null = null
if (import.meta.client) {
  onMounted(() => {
    pollTimer = setInterval(() => { void pollStatus() }, 5000)
  })
  onBeforeUnmount(() => {
    if (pollTimer) clearInterval(pollTimer)
  })
}

useHead(() => ({
  title: orderRef.value ? `Pagamento ${orderRef.value}` : 'Pagamento'
}))
</script>

<template>
  <UContainer class="py-8 sm:py-12 max-w-3xl">
    <USkeleton v-if="pending" class="h-96 w-full" />

    <UAlert
      v-else-if="initialRateLimitRecovery"
      color="warning"
      variant="soft"
      title="Aguarde antes de atualizar o pagamento"
      :description="initialRateLimitRecovery.detail"
      :actions="[{ label: 'Tentar novamente', icon: 'i-lucide-refresh-cw', onClick: refreshPayment }]"
    />

    <UAlert
      v-else-if="error || (!payment && !redirectUrl)"
      color="error"
      variant="soft"
      title="Pagamento não encontrado"
      description="Confira o link do pedido ou acompanhe pela página do pedido."
      :actions="[{ label: 'Acompanhar pedido', to: trackingUrl || `/tracking/${orderRef}` }]"
    />

    <section v-else-if="payment && promise" class="grid gap-6">
      <div class="shop-soft-panel rounded-lg p-4 sm:p-6">
        <div class="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p class="shop-section-kicker">
              Pagamento
            </p>
            <h1 class="mt-2 text-3xl font-bold leading-tight text-highlighted sm:text-4xl">Pedido {{ payment.order_ref }}</h1>
            <p class="mt-2 text-sm leading-relaxed text-muted sm:text-base">{{ payment.total_display }}</p>
          </div>
          <UButton label="Acompanhar" :to="payment.tracking_url" color="neutral" variant="outline" />
        </div>
      </div>

      <UAlert
        :color="toneColor"
        variant="subtle"
        :title="promise.title"
        :description="promise.message"
      />

      <UAlert
        v-if="payment.error_message"
        color="warning"
        variant="soft"
        title="Gateway indisponível"
        :description="payment.error_message"
        :actions="[{ label: 'Tentar novamente', icon: 'i-lucide-refresh-cw', onClick: refreshPayment }]"
      />

      <UAlert
        v-if="activeRateLimitRecovery"
      color="warning"
      variant="soft"
      title="Aguarde antes de tentar novamente"
      :description="retryAfterDescription(activeRateLimitRecovery.detail, activeRateLimitRecovery.retryAfterSeconds)"
      :actions="[{ label: 'Atualizar status', icon: 'i-lucide-refresh-cw', onClick: pollStatus }]"
      />

      <UCard v-if="paymentDetails.length" :ui="{ body: 'p-4 sm:p-5' }">
        <div class="grid gap-3 sm:grid-cols-2">
          <div v-for="detail in paymentDetails" :key="detail.label">
            <p class="text-xs font-semibold uppercase text-muted">{{ detail.label }}</p>
            <p class="mt-1 text-sm leading-relaxed text-highlighted">{{ detail.value }}</p>
          </div>
        </div>
      </UCard>

      <UAlert
        v-if="pollFailures >= 2"
        color="warning"
        variant="soft"
        :title="statusError || operationalCopy.payment.automaticStatusFailed"
        :description="operationalCopy.payment.preserveOrder"
      />

      <UCard v-if="payment.method === 'pix'" variant="outline" class="shop-soft-panel">
        <template #header>
          <div class="flex items-center justify-between gap-3">
            <strong>PIX</strong>
            <UBadge v-if="payment.pix_expires_at" color="warning" variant="subtle">Prazo ativo</UBadge>
          </div>
        </template>

        <div class="grid gap-5 justify-items-center">
          <img
            v-if="shouldShowPixQrCode"
            :src="pixQrCodeSource"
            alt="QR Code PIX"
            class="size-64 max-w-full rounded-lg border border-default bg-white p-3"
            @error="markPixQrCodeFailed"
          >
          <UAlert
            v-else-if="pixQrCodeSource || pixQrCodeFailed"
            color="warning"
            variant="soft"
            title="QR Code indisponível"
            description="Use o código Pix copia e cola abaixo para concluir o pagamento."
          />
          <UAlert
            v-else
            color="warning"
            variant="soft"
            title="PIX ainda não está pronto"
            description="Estamos aguardando a confirmação operacional ou do gateway."
          />

          <div v-if="payment.pix_copy_paste" class="w-full grid gap-2">
            <UTextarea :model-value="payment.pix_copy_paste" readonly :rows="3" aria-label="Código PIX copia e cola" class="w-full" />
            <UButton
              block
              :label="copied ? 'Código copiado' : 'Copiar código PIX'"
              :color="copyError ? 'warning' : 'primary'"
              @click="copyPix"
            />
            <UAlert
              v-if="copyError"
              color="warning"
              variant="soft"
              :title="copyError"
            />
            <p class="text-xs text-muted">
              Se preferir, toque no campo do código PIX, selecione o texto e copie manualmente no app do banco.
            </p>
          </div>
        </div>
      </UCard>

      <UCard v-else-if="payment.method === 'card'" variant="outline" class="shop-soft-panel">
        <template #header>
          <strong>Cartão</strong>
        </template>
        <div class="grid gap-4">
          <p class="text-sm text-muted">{{ promise.next_event || promise.recovery }}</p>
          <UButton
            v-if="canRedirectToCardCheckout"
            :to="redirectAction?.href || payment.checkout_url"
            target="_blank"
            rel="noopener"
            :label="redirectAction?.label || 'Pagar com cartão'"
          />
        </div>
      </UCard>

      <UCard variant="subtle">
        <div class="grid gap-3">
          <p v-if="promise.recovery" class="text-sm text-muted">{{ promise.recovery }}</p>
          <div class="flex flex-wrap gap-2">
            <UButton label="Atualizar status" color="neutral" variant="outline" @click="pollStatus" />
            <UButton v-if="mockConfirmPaymentAction && hasPendingPaymentAction" :label="mockConfirmPaymentAction.label || 'Confirmar pagamento teste'" color="success" variant="soft" :loading="actionPending" @click="mockConfirm" />
            <UButton label="Voltar ao pedido" color="neutral" variant="ghost" :to="payment.tracking_url" />
          </div>
          <p v-if="lastStatusCheckedAt" class="text-xs text-muted">Status atualizado às {{ lastStatusCheckedAt }}.</p>
        </div>
      </UCard>
    </section>
  </UContainer>
</template>
