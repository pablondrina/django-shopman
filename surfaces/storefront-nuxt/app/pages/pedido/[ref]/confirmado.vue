<script setup lang="ts">
import type { OrderItemProjection } from '~/types/shopman'
import { orderAccessErrorView } from '~/presentation/orderAccess'

interface ConfirmationResponse {
  order_ref: string
  heading: string
  customer_name: string
  eta_prefix: string
  eta_display: string
  is_preorder: boolean
  when_prefix: string
  when_display: string
  items_heading: string
  items: OrderItemProjection[]
  total_display: string
  requires_payment_gate: boolean
  payment_url: string | null
  tracking_url: string
  track_cta: string
  share_cta: string
  share_text: string
}

const route = useRoute()
const apiPath = useShopmanApiPath()
const orderRef = computed(() => String(route.params.ref || ''))
const requestHeaders = import.meta.server ? useRequestHeaders(['cookie']) : undefined

const { data, pending, error, refresh } = await useFetch<ConfirmationResponse>(
  () => apiPath(`/api/v1/orders/${encodeURIComponent(orderRef.value)}/confirmation/`),
  { credentials: 'include', headers: requestHeaders, key: () => `confirmation-${orderRef.value}` }
)

const errorView = computed(() => orderAccessErrorView((error.value as { statusCode?: number } | null)?.statusCode, 'tracking'))
const loginHref = computed(() => `/entrar?next=${encodeURIComponent(`/pedido/${orderRef.value}`)}`)
const shareHref = computed(() => data.value?.share_text ? `https://wa.me/?text=${encodeURIComponent(data.value.share_text)}` : '')
// Só há rota de pagamento quando o backend manda a URL. Sem ela, o CTA cai para o
// acompanhamento (nunca um primary que parece clicável e não vai a lugar nenhum).
const hasPaymentUrl = computed(() => Boolean(data.value?.payment_url))
const paymentRoute = computed(() => hasPaymentUrl.value ? localRouteFromBackend(data.value!.payment_url) : null)
const trackingRoute = computed(() => localRouteFromBackend(data.value?.tracking_url || `/pedido/${orderRef.value}`))

useSeoMeta({ title: 'Pedido recebido' })
</script>

<template>
  <main class="shop-section">
    <div class="shop-container">
      <!-- Momento de maior ansiedade do funil (acabou de fechar o pedido): nunca
           deixamos a tela em branco. Skeleton no carregamento, erro acolhedor com
           caminho de volta se o fetch falhar. -->
      <div v-if="pending" class="mx-auto max-w-md shop-stack-block">
        <UiSkeleton class="mx-auto size-12 rounded-full" />
        <UiSkeleton class="mx-auto h-7 w-3/4 rounded" />
        <UiSkeleton class="h-40 rounded-lg" />
        <UiSkeleton class="h-11 rounded-lg" />
      </div>

      <UiAlert v-else-if="error" variant="warning" :icon="errorView.icon" class="mx-auto max-w-md">
        <UiAlertTitle>{{ errorView.title }}</UiAlertTitle>
        <UiAlertDescription>
          <div class="shop-stack-block">
            <p>{{ errorView.message }}</p>
            <div class="flex flex-col gap-2 sm:flex-row">
              <UiButton v-if="errorView.showLogin" :to="loginHref" icon="lucide:log-in">Entrar</UiButton>
              <UiButton :to="`/pedido/${orderRef}`" variant="outline" icon="lucide:package-search">Acompanhar pedido</UiButton>
              <UiButton v-if="errorView.canRetry" variant="ghost" icon="lucide:rotate-cw" @click="refresh">Tentar de novo</UiButton>
            </div>
          </div>
        </UiAlertDescription>
      </UiAlert>

      <div v-else-if="data" class="mx-auto max-w-md shop-stack-block">
        <!-- Cabeçalho "yoin": contido, não performático. -->
        <div class="text-center">
          <div class="mx-auto flex size-12 items-center justify-center rounded-full bg-primary/10 text-primary">
            <Icon name="lucide:check" class="size-6" />
          </div>
          <h1 class="mt-4 shop-title">
            {{ data.heading }}<template v-if="data.customer_name">, {{ data.customer_name }}</template>.
          </h1>
          <!-- Encomenda: mostra o combinado ("Pedido para sábado, 19/07 · A partir
               das 09h") no lugar do ETA de preparo. -->
          <p v-if="data.is_preorder && data.when_display" class="mt-2 shop-muted" data-confirmation-when>
            {{ data.when_prefix }} {{ data.when_display }}.
          </p>
          <p v-else-if="data.eta_display" class="mt-2 shop-muted">{{ data.eta_prefix }} {{ data.eta_display }}.</p>
          <p class="mt-1 shop-meta tabular-nums">{{ data.order_ref }}</p>
        </div>

        <!-- Pagamento pendente: enxuto, sem competir — destaque no "Pagar agora". -->
        <template v-if="data.requires_payment_gate">
          <!-- Com URL de pagamento: primary leva ao pagamento. Sem ela (o backend
               ainda está preparando o pagamento): avisamos e o acompanhamento vira
               o caminho principal — nunca um primary que não navega. -->
          <template v-if="paymentRoute">
            <UiButton :to="paymentRoute" size="lg" icon="lucide:qr-code" class="w-full justify-center">
              Pagar agora
            </UiButton>
            <UiButton :to="trackingRoute" variant="ghost" class="w-full justify-center">
              {{ data.track_cta }}
            </UiButton>
          </template>
          <template v-else>
            <p class="flex items-center justify-center gap-2 shop-muted">
              <Icon name="lucide:loader-circle" class="size-4 shrink-0 animate-spin" />
              Estamos preparando seu pagamento.
            </p>
            <UiButton :to="trackingRoute" size="lg" icon="lucide:package-search" class="w-full justify-center">
              {{ data.track_cta }}
            </UiButton>
          </template>
        </template>

        <!-- Sem pagamento imediato: celebra com itens + acompanhar + compartilhar. -->
        <template v-else>
          <div class="rounded-lg border bg-card p-4 shop-stack-tight">
            <p class="shop-item-title font-semibold">{{ data.items_heading }}</p>
            <div v-for="(item, i) in data.items" :key="i" class="flex items-baseline gap-2">
              <span class="shop-body">{{ item.qty }}× {{ item.name }}</span>
              <span class="ml-auto shop-price tabular-nums">{{ item.total_display }}</span>
            </div>
            <div class="flex items-baseline gap-2 border-t pt-2">
              <span class="shop-body font-semibold">Total</span>
              <span class="ml-auto shop-price-strong tabular-nums">{{ data.total_display }}</span>
            </div>
          </div>
          <UiButton :to="trackingRoute || undefined" size="lg" icon="lucide:package-search" class="w-full justify-center">
            {{ data.track_cta }}
          </UiButton>
          <UiButton
            v-if="shareHref"
            :href="shareHref"
            target="_blank"
            rel="noopener"
            variant="outline"
            icon="lucide:share-2"
            class="w-full justify-center"
          >
            {{ data.share_cta }}
          </UiButton>
        </template>
      </div>
    </div>
  </main>
</template>
