<script setup lang="ts">
import type { PaymentResponse, PaymentStatusResponse, Action } from '~/types/shopman'
import { paymentAlertFilled, paymentAlertIcon, paymentAlertVariant, paymentMethodLabel, shouldPollPayment } from '~/presentation/payment'
import { countdownPct, deadlineCountdown, isCountdownUrgent, serverClockOffsetMs } from '~/presentation/deadline'
import { orderAccessErrorView } from '~/presentation/orderAccess'

const route = useRoute()
const apiPath = useShopmanApiPath()
const csrfHeaders = useShopmanCsrfHeaders()
const orderRef = computed(() => String(route.params.ref || ''))
const actionPending = ref<Record<string, boolean>>({})
// Forward the session cookie on SSR so order access resolves on first paint
// (same pattern as the account pages) — otherwise the server fetch lands
// unauthenticated and the page renders the "not found" fallback for a customer
// who can actually see this payment.
const requestHeaders = import.meta.server ? useRequestHeaders(['cookie']) : undefined

const { data, pending, error, refresh } = await useFetch<PaymentResponse>(
  () => apiPath(`/api/v1/payment/${encodeURIComponent(orderRef.value)}/`),
  { credentials: 'include', headers: requestHeaders }
)

const payment = computed(() => data.value?.payment || null)
// Copy estática da tela vem do registro omotenashi (configurável no Admin); o
// fallback cobre só o intervalo de carregamento. O painel de status é o promise.
const copy = computed(() => data.value?.copy ?? {
  order_ref_label: 'Pedido',
  total_label: 'Total',
  meta_description: 'Pague seu pedido para seguirmos com o preparo',
  card_intro: 'Conclua o pagamento no ambiente seguro do Stripe. A confirmação é automática. Volte aqui se quiser acompanhar seu pedido.',
  card_security_note: 'Pagamento processado por provedor seguro. Nós não recebemos os dados do seu cartão.',
  pix_instruction: 'Escaneie o QR Code ou copie o código Pix abaixo.',
  pix_copy_label: 'Copia e cola PIX',
  pix_copy_btn: 'Copiar código',
  pix_copied: 'Código PIX copiado.',
  pix_expires_label: 'Tempo para pagar'
})
const errorView = computed(() => orderAccessErrorView((error.value as { statusCode?: number } | null)?.statusCode, 'payment'))
const loginHref = computed(() => `/entrar?next=${encodeURIComponent(`/pedido/${orderRef.value}/pagamento`)}`)

watchEffect(() => {
  if (data.value?.redirect_url && !payment.value && import.meta.client) {
    void navigateTo(localRouteFromBackend(data.value.redirect_url))
  }
})

// Relógio vivo alinhado ao servidor (timeouts transparentes). `nowMs` corrige o
// relógio do dispositivo pelo offset de server_now_iso.
const clientNow = ref(Date.now())
const serverOffset = computed(() => serverClockOffsetMs(payment.value?.server_now_iso, Date.now()))
const nowMs = computed(() => clientNow.value + serverOffset.value)

// Janela do PIX ancorada no primeiro tempo restante visto, para a barra drenar
// de cheia a vazia sem o início real do intent.
const pixWindowSeconds = ref(0)
const pixCountdown = computed(() => deadlineCountdown(payment.value?.pix_expires_at, nowMs.value))
watch(pixCountdown, countdown => {
  if (countdown && countdown.totalSeconds > 0 && pixWindowSeconds.value === 0) {
    pixWindowSeconds.value = countdown.totalSeconds
  }
}, { immediate: true })
const pixPct = computed(() => pixCountdown.value ? countdownPct(pixCountdown.value.totalSeconds, pixWindowSeconds.value) : 0)
const pixUrgent = computed(() => isCountdownUrgent(pixPct.value))

let tick: ReturnType<typeof setInterval> | null = null
let poll: ReturnType<typeof setInterval> | null = null
let expiryHandled = false
// Sinal de offline: 3 polls seguidos falhando (~24s) = o countdown do PIX
// está rodando às cegas — o cliente precisa saber que estamos sem conexão.
const failedPolls = ref(0)
const connectionLost = computed(() => failedPolls.value >= 3)
onMounted(() => {
  tick = setInterval(() => { clientNow.value = Date.now() }, 1000)
  poll = setInterval(async () => {
    if (!shouldPollPayment(payment.value)) return
    const status = await $fetch<PaymentStatusResponse>(apiPath(`/api/v1/payment/${encodeURIComponent(orderRef.value)}/status/`), {
      credentials: 'include',
      timeout: 7000
    }).catch(() => null)
    if (status === null) {
      failedPolls.value += 1
      return
    }
    failedPolls.value = 0
    if (status.should_redirect) {
      await navigateTo(localRouteFromBackend(status.redirect_url))
    } else {
      await refresh()
    }
  }, 8000)
})
onBeforeUnmount(() => {
  if (tick) clearInterval(tick)
  if (poll) clearInterval(poll)
})

// Quando o PIX zera, o backend decide (deadline_action): a UI só sincroniza uma
// vez para refletir o estado terminal (expirado/cancelado) que a projeção trouxer.
watch(() => pixCountdown.value?.isExpired, async expired => {
  if (expired && !expiryHandled && shouldPollPayment(payment.value)) {
    expiryHandled = true
    await refresh()
  }
})

async function copyPix () {
  if (!payment.value?.pix_copy_paste || !import.meta.client) return
  await navigator.clipboard.writeText(payment.value.pix_copy_paste)
  useSonner.success(copy.value.pix_copied)
}

async function postAction (action: Action) {
  actionPending.value = { ...actionPending.value, [action.ref]: true }
  try {
    const headers = await csrfHeaders()
    if (action.idempotency === 'required' || action.idempotency === 'recommended') {
      headers['x-idempotency-key'] = newRemoteMutationKey(action.ref)
    }
    const result = await $fetch<{ redirect_url?: string }>(apiPath(action.href), {
      method: remoteMethod(action.method),
      headers,
      credentials: 'include'
    })
    if (result.redirect_url) await navigateTo(localRouteFromBackend(result.redirect_url))
    else await refresh()
  } catch (e) {
    if (import.meta.client) useSonner.error(errorDetail(e, 'Não foi possível atualizar o pagamento.'))
  } finally {
    actionPending.value = omitKey(actionPending.value, action.ref)
  }
}

// "Simular pagamento" (staging/DEBUG): captura o pagamento por um gateway mock,
// para testar o fluxo PIX/cartão de ponta a ponta sem gateway real. Só aparece
// quando o backend marca payment.mock_enabled.
const simulating = ref(false)
async function simulatePayment () {
  if (simulating.value) return
  simulating.value = true
  try {
    const headers = await csrfHeaders()
    headers['x-idempotency-key'] = newRemoteMutationKey(`mock-confirm:${orderRef.value}`)
    const result = await $fetch<{ redirect_url?: string }>(
      apiPath(`/api/v1/payment/${encodeURIComponent(orderRef.value)}/mock-confirm/`),
      { method: 'POST', headers, credentials: 'include' }
    )
    if (result.redirect_url) await navigateTo(localRouteFromBackend(result.redirect_url))
    else await refresh()
  } catch (e) {
    if (import.meta.client) useSonner.error(errorDetail(e, 'Não foi possível simular o pagamento.'))
  } finally {
    simulating.value = false
  }
}

useSeoMeta({
  title: () => `Pagamento ${orderRef.value}`,
  description: () => copy.value.meta_description
})
</script>

<template>
  <main class="shop-section pt-0">
    <div class="shop-breadcrumb-bar mb-4">
      <div class="shop-container max-w-4xl py-2">
        <UiBreadcrumbs
          :items="[
            { label: 'Início', link: '/' },
            { label: 'Pedido', link: orderTrackingRoute(orderRef) },
            { label: 'Pagamento' }
          ]"
        />
      </div>
    </div>
    <div class="shop-container max-w-4xl shop-stack-block">
      <div>
        <p class="shop-kicker">Pagamento</p>
        <h1 class="mt-1 shop-title">{{ copy.order_ref_label }} {{ orderRef }}</h1>
      </div>

      <UiSkeleton v-if="pending" class="h-96 rounded-lg" />

      <UiAlert v-else-if="error" variant="warning" :icon="errorView.icon">
        <UiAlertTitle>{{ errorView.title }}</UiAlertTitle>
        <UiAlertDescription>
          <div class="shop-stack-block">
            <p>{{ errorView.message }}</p>
            <div class="flex flex-col gap-2 sm:flex-row">
              <UiButton v-if="errorView.showLogin" :to="loginHref" icon="lucide:log-in">Entrar</UiButton>
              <UiButton v-if="errorView.canRetry" variant="outline" icon="lucide:rotate-cw" @click="refresh">Tentar de novo</UiButton>
              <UiButton to="/menu" variant="ghost" icon="lucide:utensils">Ver cardápio</UiButton>
            </div>
          </div>
        </UiAlertDescription>
      </UiAlert>

      <template v-else-if="payment">
        <UiAlert
          :variant="paymentAlertVariant(payment.promise.tone)"
          :filled="paymentAlertFilled(payment.promise.tone)"
          :icon="paymentAlertIcon(payment.promise.tone)"
        >
          <UiAlertTitle>{{ payment.promise.title }}</UiAlertTitle>
          <UiAlertDescription>{{ payment.promise.message }}</UiAlertDescription>
        </UiAlert>

        <div class="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
          <UiCard>
            <UiCardHeader>
              <p class="shop-muted text-sm">{{ copy.total_label }}</p>
              <UiCardTitle>{{ payment.total_display }}</UiCardTitle>
              <UiCardDescription>{{ paymentMethodLabel(payment.method) }}</UiCardDescription>
            </UiCardHeader>
            <UiCardContent class="space-y-4">
              <div v-if="payment.method === 'card' && payment.checkout_url" class="shop-stack-block rounded-lg border p-4">
                <div class="flex items-start gap-3">
                  <Icon name="lucide:shield-check" :size="22" class="mt-0.5 shrink-0 text-emerald-600" />
                  <div class="space-y-1">
                    <p class="shop-item-title font-semibold text-foreground">Pagamento seguro</p>
                    <p class="shop-muted">{{ copy.card_intro }}</p>
                    <p class="shop-meta">{{ copy.card_security_note }}</p>
                  </div>
                </div>
                <UiButton :href="payment.checkout_url" target="_blank" class="w-full" :class="simulating ? 'pointer-events-none opacity-50' : ''" size="lg" icon="lucide:credit-card">
                  Pagar com cartão
                </UiButton>
              </div>

              <div v-else-if="payment.method === 'card'" class="flex items-center gap-3 rounded-lg border p-4">
                <Icon name="lucide:loader-circle" :size="20" class="shrink-0 animate-spin text-muted-foreground" />
                <p class="shop-muted">Preparando o pagamento seguro com cartão…</p>
              </div>

              <p v-if="payment.pix_qr_code || payment.pix_copy_paste" class="shop-muted">{{ copy.pix_instruction }}</p>

              <div v-if="payment.pix_qr_code || payment.pix_copy_paste" class="grid grid-cols-1 gap-4 sm:grid-cols-[220px_minmax(0,1fr)]">
                <div class="rounded-lg border bg-white p-4">
                  <img v-if="payment.pix_qr_code" :src="payment.pix_qr_code" alt="QR Code PIX" class="w-full" />
                  <div v-else class="flex aspect-square items-center justify-center text-muted-foreground">
                    <Icon name="lucide:qr-code" class="size-12" />
                  </div>
                </div>
                <div class="shop-stack-block">
                  <p class="shop-muted">{{ copy.pix_copy_label }}</p>
                  <pre class="max-h-40 overflow-auto rounded-lg border bg-muted p-3 text-xs whitespace-pre-wrap">{{ payment.pix_copy_paste }}</pre>
                  <UiButton variant="outline" icon="lucide:copy" class="w-full sm:w-auto" @click="copyPix">{{ copy.pix_copy_btn }}</UiButton>

                  <p v-if="connectionLost" class="rounded-md border border-amber-500/30 bg-amber-500/5 p-2 text-xs text-amber-700 dark:text-amber-400" role="status">
                    Sem conexão no momento — se você já pagou, a confirmação chega assim que a internet voltar.
                  </p>
                  <div v-if="pixCountdown && !pixCountdown.isExpired" class="space-y-2" role="timer" aria-live="polite">
                    <div class="flex items-center justify-between shop-body">
                      <span class="text-muted-foreground">{{ copy.pix_expires_label }}</span>
                      <span class="shop-price" :class="pixUrgent ? 'text-destructive' : 'text-foreground'">{{ pixCountdown.mmss }}</span>
                    </div>
                    <UiProgress :model-value="pixPct" :class="pixUrgent ? '[&>div]:bg-destructive' : ''" />
                    <p class="shop-meta">Assim que o pagamento cair, atualizamos esta tela sozinhos.</p>
                  </div>
                  <p v-else-if="pixCountdown?.isExpired" class="shop-body font-semibold text-destructive">O prazo do PIX expirou.</p>
                </div>
              </div>

              <div v-if="payment.mock_enabled" class="space-y-1 rounded-lg border border-dashed bg-muted/40 p-4">
                <UiButton
                  variant="default"
                  class="w-full"
                  icon="lucide:flask-conical"
                  :loading="simulating"
                  @click="simulatePayment"
                >
                  Simular pagamento
                </UiButton>
                <p class="shop-meta text-center">Ambiente de teste · captura por gateway simulado</p>
              </div>

              <UiAlert v-if="payment.error_message" variant="destructive">
                <UiAlertTitle>Gateway</UiAlertTitle>
                <UiAlertDescription>{{ payment.error_message }}</UiAlertDescription>
              </UiAlert>

              <UiAlert v-if="payment.promise.recovery" variant="warning">
                <UiAlertTitle>Como resolver</UiAlertTitle>
                <UiAlertDescription>{{ payment.promise.recovery }}</UiAlertDescription>
              </UiAlert>
            </UiCardContent>
          </UiCard>

          <aside class="space-y-4">
            <UiCard>
              <UiCardHeader>
                <UiCardTitle>Próxima ação</UiCardTitle>
                <UiCardDescription>{{ payment.promise.next_event }}</UiCardDescription>
              </UiCardHeader>
              <UiCardContent class="space-y-2">
                <UiButton :to="localRouteFromBackend(payment.tracking_url)" class="w-full" icon="lucide:route">
                  Acompanhar pedido
                </UiButton>
                <UiButton
                  v-for="action in payment.actions"
                  :key="action.ref"
                  :variant="actionVariant(action)"
                  class="w-full"
                  :disabled="!action.enabled"
                  :loading="!!actionPending[action.ref]"
                  @click="postAction(action)"
                >
                  {{ action.label }}
                </UiButton>

              </UiCardContent>
            </UiCard>

            <UiAlert v-if="payment.promise.active_notification" variant="info">
              <UiAlertTitle>Status</UiAlertTitle>
              <UiAlertDescription>{{ payment.promise.active_notification }}</UiAlertDescription>
            </UiAlert>
          </aside>
        </div>
      </template>
    </div>
  </main>
</template>
