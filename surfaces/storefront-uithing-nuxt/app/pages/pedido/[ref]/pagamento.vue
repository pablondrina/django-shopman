<script setup lang="ts">
import type { PaymentResponse, PaymentStatusResponse, Action } from '~/types/shopman'

const route = useRoute()
const apiPath = useShopmanApiPath()
const csrfHeaders = useShopmanCsrfHeaders()
const orderRef = computed(() => String(route.params.ref || ''))
const actionPending = ref<Record<string, boolean>>({})

const { data, pending, error, refresh } = await useFetch<PaymentResponse>(
  () => apiPath(`/api/v1/payment/${encodeURIComponent(orderRef.value)}/`),
  { credentials: 'include' }
)

const payment = computed(() => data.value?.payment || null)

watchEffect(() => {
  if (data.value?.redirect_url && !payment.value && import.meta.client) {
    void navigateTo(localRouteFromBackend(data.value.redirect_url))
  }
})

let poll: ReturnType<typeof setInterval> | null = null
onMounted(() => {
  poll = setInterval(async () => {
    if (!payment.value || ['paid', 'cancelled', 'expired'].includes(String(payment.value.payment_status))) return
    const status = await $fetch<PaymentStatusResponse>(apiPath(`/api/v1/payment/${encodeURIComponent(orderRef.value)}/status/`), {
      credentials: 'include'
    }).catch(() => null)
    if (status?.should_redirect) {
      await navigateTo(localRouteFromBackend(status.redirect_url))
    } else if (status) {
      await refresh()
    }
  }, 8000)
})
onBeforeUnmount(() => {
  if (poll) clearInterval(poll)
})

async function copyPix () {
  if (!payment.value?.pix_copy_paste || !import.meta.client) return
  await navigator.clipboard.writeText(payment.value.pix_copy_paste)
  useSonner.success('Código PIX copiado.')
}

async function postAction (action: Action) {
  actionPending.value = { ...actionPending.value, [action.ref]: true }
  try {
    const headers = await csrfHeaders()
    if (action.idempotency === 'required' || action.idempotency === 'recommended') {
      headers['x-idempotency-key'] = newRemoteMutationKey(action.ref)
    }
    const result = await $fetch<{ redirect_url?: string }>(apiPath(action.href), {
      method: action.method || 'POST',
      headers,
      credentials: 'include'
    })
    if (result.redirect_url) await navigateTo(localRouteFromBackend(result.redirect_url))
    else await refresh()
  } catch (e: any) {
    if (import.meta.client) useSonner.error(e?.data?.detail || 'Não foi possível atualizar o pagamento.')
  } finally {
    const next = { ...actionPending.value }
    delete next[action.ref]
    actionPending.value = next
  }
}

useSeoMeta({
  title: () => `Pagamento ${orderRef.value}`
})
</script>

<template>
  <main class="shop-section">
    <div class="shop-container max-w-4xl space-y-5">
      <UiBreadcrumbs
        :items="[
          { label: 'Início', link: '/' },
          { label: 'Pedido', link: orderTrackingRoute(orderRef) },
          { label: 'Pagamento' }
        ]"
      />

      <div>
        <p class="shop-kicker">Pagamento</p>
        <h1 class="mt-1 text-3xl font-semibold">Pedido {{ orderRef }}</h1>
      </div>

      <UiSkeleton v-if="pending" class="h-96 rounded-lg" />

      <UiAlert v-else-if="error" variant="destructive">
        <UiAlertTitle>Pagamento indisponível</UiAlertTitle>
        <UiAlertDescription>
          <UiButton size="sm" variant="outline" @click="refresh">Atualizar</UiButton>
        </UiAlertDescription>
      </UiAlert>

      <template v-else-if="payment">
        <UiAlert
          :variant="payment.promise.tone === 'danger' ? 'destructive' : payment.promise.tone === 'warning' ? 'warning' : 'info'"
          :filled="payment.promise.tone !== 'danger'"
          :icon="payment.promise.tone === 'danger' ? 'lucide:triangle-alert' : payment.promise.tone === 'warning' ? 'lucide:circle-alert' : 'lucide:info'"
        >
          <UiAlertTitle>{{ payment.promise.title }}</UiAlertTitle>
          <UiAlertDescription>{{ payment.promise.message }}</UiAlertDescription>
        </UiAlert>

        <div class="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_320px]">
          <UiCard>
            <UiCardHeader>
              <UiCardTitle>{{ payment.total_display }}</UiCardTitle>
              <UiCardDescription>{{ payment.method }} · {{ payment.payment_status || payment.order_status }}</UiCardDescription>
            </UiCardHeader>
            <UiCardContent class="space-y-4">
              <div v-if="payment.checkout_url" class="rounded-lg border p-4">
                <p class="text-sm text-muted-foreground">Checkout hospedado</p>
                <UiButton :href="payment.checkout_url" target="_blank" class="mt-3" icon="lucide:external-link">
                  Abrir pagamento
                </UiButton>
              </div>

              <div v-if="payment.pix_qr_code || payment.pix_copy_paste" class="grid grid-cols-1 gap-4 sm:grid-cols-[220px_minmax(0,1fr)]">
                <div class="rounded-lg border bg-white p-4">
                  <img v-if="payment.pix_qr_code" :src="payment.pix_qr_code" alt="QR Code PIX" class="w-full" />
                  <div v-else class="flex aspect-square items-center justify-center text-muted-foreground">
                    <Icon name="lucide:qr-code" class="size-12" />
                  </div>
                </div>
                <div class="space-y-3">
                  <p class="text-sm text-muted-foreground">Copia e cola PIX</p>
                  <pre class="max-h-40 overflow-auto rounded-lg border bg-muted p-3 text-xs whitespace-pre-wrap">{{ payment.pix_copy_paste }}</pre>
                  <UiButton variant="outline" icon="lucide:copy" @click="copyPix">Copiar código</UiButton>
                  <p v-if="payment.pix_expires_at" class="text-sm text-muted-foreground">Expira em {{ payment.pix_expires_at }}</p>
                </div>
              </div>

              <UiAlert v-if="payment.error_message" variant="destructive">
                <UiAlertTitle>Gateway</UiAlertTitle>
                <UiAlertDescription>{{ payment.error_message }}</UiAlertDescription>
              </UiAlert>

              <UiAlert v-if="payment.promise.recovery" variant="warning">
                <UiAlertTitle>Recuperacao</UiAlertTitle>
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
