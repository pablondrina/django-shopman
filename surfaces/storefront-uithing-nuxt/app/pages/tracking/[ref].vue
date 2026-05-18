<script setup lang="ts">
import type { SurfaceActionProjection, TrackingResponse } from '~/types/shopman'

const route = useRoute()
const apiPath = useShopmanApiPath()
const csrfHeaders = useShopmanCsrfHeaders()
const orderRef = computed(() => String(route.params.ref || ''))
const rating = ref(5)
const comment = ref('')
const actionPending = ref<Record<string, boolean>>({})
const supportOpen = ref(false)

const { data, pending, error, refresh } = await useFetch<TrackingResponse>(
  () => apiPath(`/api/v1/tracking/${encodeURIComponent(orderRef.value)}/`),
  { credentials: 'include' }
)

const tracking = computed(() => data.value || null)
const paymentHref = computed(() => localRouteFromBackend(tracking.value?.payment_gate_url || tracking.value?.promise.actions.find(action => action.ref.includes('payment'))?.href || null))
const cancelAction = computed(() => tracking.value?.actions.find(action => action.ref === 'cancel_order' && action.enabled) || null)
const rateAction = computed(() => tracking.value?.actions.find(action => action.ref === 'rate_order' && action.enabled) || null)
const progressPercent = computed(() => {
  const steps = tracking.value?.progress_steps || []
  if (!steps.length) return 0
  const done = steps.filter(step => step.state === 'completed').length
  const current = steps.findIndex(step => step.state === 'current')
  return Math.round(((done + (current >= 0 ? 0.5 : 0)) / steps.length) * 100)
})

let poll: ReturnType<typeof setInterval> | null = null
onMounted(() => {
  poll = setInterval(() => {
    if (tracking.value?.is_active) void refresh()
  }, Math.max((tracking.value?.stale_after_seconds || 30) * 1000, 15000))
})
onBeforeUnmount(() => {
  if (poll) clearInterval(poll)
})

async function postAction (action: SurfaceActionProjection, body: Record<string, unknown> = {}) {
  actionPending.value = { ...actionPending.value, [action.ref]: true }
  try {
    await $fetch(apiPath(action.href), {
      method: action.method || 'POST',
      headers: await csrfHeaders(),
      credentials: 'include',
      body
    })
    await refresh()
    if (import.meta.client) useSonner.success('Atualizado.')
  } catch (e: any) {
    if (import.meta.client) useSonner.error(e?.data?.detail || 'Nao foi possivel executar a acao.')
  } finally {
    const next = { ...actionPending.value }
    delete next[action.ref]
    actionPending.value = next
  }
}

useSeoMeta({
  title: () => tracking.value ? `Pedido ${tracking.value.ref}` : 'Acompanhamento'
})
</script>

<template>
  <main class="shop-section">
    <div class="shop-container grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
      <section class="space-y-5">
        <div>
          <p class="shop-kicker">Acompanhamento</p>
          <h1 class="mt-1 text-3xl font-semibold">Pedido {{ orderRef }}</h1>
        </div>

        <UiSkeleton v-if="pending" class="h-96 rounded-lg" />

        <UiAlert v-else-if="error" variant="destructive">
          <UiAlertTitle>Pedido nao encontrado</UiAlertTitle>
          <UiAlertDescription>
            <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <span>Nao conseguimos carregar o acompanhamento agora.</span>
              <UiButton size="sm" variant="outline" @click="refresh">Atualizar</UiButton>
            </div>
          </UiAlertDescription>
        </UiAlert>

        <template v-else-if="tracking">
          <UiAlert :variant="tracking.promise.tone === 'danger' ? 'destructive' : tracking.promise.tone === 'warning' ? 'warning' : 'success'" filled>
            <UiAlertTitle>{{ tracking.promise.title || tracking.status_label }}</UiAlertTitle>
            <UiAlertDescription>
              <div class="space-y-3">
                <p>{{ tracking.promise.message || tracking.copy.promise_fallback_message }}</p>
                <UiButton v-if="tracking.requires_payment_gate" :to="paymentHref" icon="lucide:credit-card">
                  Regularizar pagamento
                </UiButton>
              </div>
            </UiAlertDescription>
          </UiAlert>

          <UiCard>
            <UiCardHeader>
              <div class="flex items-center justify-between gap-3">
                <div>
                  <UiCardTitle>{{ tracking.status_label }}</UiCardTitle>
                  <UiCardDescription>{{ tracking.promise.next_event || tracking.last_updated_display }}</UiCardDescription>
                </div>
                <UiBadge :variant="tracking.is_active ? 'success' : 'secondary'">
                  {{ tracking.is_active ? tracking.copy.live_badge : tracking.copy.finished_badge }}
                </UiBadge>
              </div>
            </UiCardHeader>
            <UiCardContent class="space-y-4">
              <UiProgress :model-value="progressPercent" />
              <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div v-for="row in tracking.promise_rows" :key="row.label" class="rounded-lg border p-3 text-sm">
                  <p class="text-muted-foreground">{{ row.label }}</p>
                  <a v-if="row.url" :href="row.url" target="_blank" class="font-medium text-primary">{{ row.value }}</a>
                  <p v-else class="font-medium">{{ row.value }}</p>
                </div>
              </div>
            </UiCardContent>
          </UiCard>

          <UiCard>
            <UiCardHeader>
              <UiCardTitle>{{ tracking.copy.progress_heading }}</UiCardTitle>
            </UiCardHeader>
            <UiCardContent>
              <UiTimeline>
                <UiTimelineItem v-for="step in tracking.progress_steps" :key="step.key" :step="step.key">
                  <UiTimelineHeader>
                    <UiTimelineIndicator :class="step.state === 'completed' ? 'bg-primary' : ''" />
                    <UiTimelineTitle>{{ step.label }}</UiTimelineTitle>
                    <UiTimelineDate v-if="step.timestamp_display">{{ step.timestamp_display }}</UiTimelineDate>
                  </UiTimelineHeader>
                </UiTimelineItem>
              </UiTimeline>
            </UiCardContent>
          </UiCard>

          <UiTabs default-value="items">
            <UiTabsList>
              <UiTabsTrigger value="items">Itens</UiTabsTrigger>
              <UiTabsTrigger value="timeline">Timeline</UiTabsTrigger>
              <UiTabsTrigger value="delivery">Entrega</UiTabsTrigger>
            </UiTabsList>
            <UiTabsContent value="items">
              <UiCard>
                <UiCardContent class="space-y-3 p-4">
                  <UiItem v-for="item in tracking.items" :key="item.sku" class="p-0">
                    <UiItemContent>
                      <UiItemTitle>{{ item.name }}</UiItemTitle>
                      <UiItemDescription>{{ item.qty }} x {{ item.unit_price_display }}</UiItemDescription>
                    </UiItemContent>
                    <UiItemActions>{{ item.total_display }}</UiItemActions>
                  </UiItem>
                </UiCardContent>
              </UiCard>
            </UiTabsContent>
            <UiTabsContent value="timeline">
              <UiCard>
                <UiCardContent class="space-y-3 p-4">
                  <UiItem v-for="event in tracking.timeline" :key="`${event.event_type}-${event.timestamp_display}`" class="p-0">
                    <UiItemContent>
                      <UiItemTitle>{{ event.label }}</UiItemTitle>
                      <UiItemDescription>{{ event.timestamp_display }}</UiItemDescription>
                    </UiItemContent>
                  </UiItem>
                </UiCardContent>
              </UiCard>
            </UiTabsContent>
            <UiTabsContent value="delivery">
              <UiCard>
                <UiCardContent class="space-y-3 p-4">
                  <UiAlert v-if="tracking.pickup_info">
                    <UiAlertTitle>{{ tracking.pickup_info.heading }}</UiAlertTitle>
                    <UiAlertDescription>
                      {{ tracking.pickup_info.address }}
                      <UiButton v-if="tracking.pickup_info.directions_url" :href="tracking.pickup_info.directions_url" target="_blank" variant="outline" size="sm" class="mt-2">
                        {{ tracking.pickup_info.directions_label }}
                      </UiButton>
                    </UiAlertDescription>
                  </UiAlert>
                  <UiItem v-for="fulfillment in tracking.fulfillments" :key="`${fulfillment.status}-${fulfillment.tracking_code}`" class="rounded-lg border p-3">
                    <UiItemContent>
                      <UiItemTitle>{{ fulfillment.status_label }}</UiItemTitle>
                      <UiItemDescription>{{ fulfillment.tracking_label }}</UiItemDescription>
                    </UiItemContent>
                    <UiItemActions>
                      <UiButton v-if="fulfillment.tracking_url" :href="fulfillment.tracking_url" target="_blank" variant="outline" size="sm">Rastrear</UiButton>
                    </UiItemActions>
                  </UiItem>
                </UiCardContent>
              </UiCard>
            </UiTabsContent>
          </UiTabs>
        </template>
      </section>

      <aside v-if="tracking" class="space-y-4 lg:sticky lg:top-24 lg:self-start">
        <UiCard>
          <UiCardHeader>
            <UiCardTitle>Proxima acao</UiCardTitle>
            <UiCardDescription>{{ tracking.promise.recovery || tracking.promise.next_event }}</UiCardDescription>
          </UiCardHeader>
          <UiCardContent class="space-y-2">
            <UiButton v-if="tracking.whatsapp_url" :href="tracking.whatsapp_url" target="_blank" variant="outline" icon="lucide:message-circle" class="w-full">
              {{ tracking.copy.support_label }}
            </UiButton>
            <UiButton v-if="tracking.requires_payment_gate" :to="paymentHref" icon="lucide:credit-card" class="w-full">
              Pagamento
            </UiButton>
            <UiAlertDialog v-if="cancelAction">
              <UiAlertDialogTrigger as-child>
                <UiButton variant="destructive" class="w-full">Cancelar pedido</UiButton>
              </UiAlertDialogTrigger>
              <UiAlertDialogContent>
                <UiAlertDialogHeader>
                  <UiAlertDialogTitle>Cancelar pedido?</UiAlertDialogTitle>
                  <UiAlertDialogDescription>Vamos avisar a loja e atualizar o acompanhamento.</UiAlertDialogDescription>
                </UiAlertDialogHeader>
                <UiAlertDialogFooter>
                  <UiAlertDialogCancel>Voltar</UiAlertDialogCancel>
                  <UiAlertDialogAction @click="postAction(cancelAction)">Cancelar</UiAlertDialogAction>
                </UiAlertDialogFooter>
              </UiAlertDialogContent>
            </UiAlertDialog>
          </UiCardContent>
        </UiCard>

        <UiDialog v-if="rateAction" v-model:open="supportOpen">
          <UiDialogTrigger as-child>
            <UiButton variant="secondary" class="w-full" icon="lucide:star">Avaliar pedido</UiButton>
          </UiDialogTrigger>
          <UiDialogContent>
            <UiDialogHeader>
              <UiDialogTitle>Avaliar pedido</UiDialogTitle>
              <UiDialogDescription>{{ tracking.copy.rating_comment_placeholder }}</UiDialogDescription>
            </UiDialogHeader>
            <div class="space-y-4">
              <UiNumberField v-model="rating" :min="1" :max="5" />
              <UiTextarea v-model="comment" rows="3" />
            </div>
            <UiDialogFooter>
              <UiButton @click="postAction(rateAction, { rating, comment })">{{ tracking.copy.rating_submit_label }}</UiButton>
            </UiDialogFooter>
          </UiDialogContent>
        </UiDialog>
      </aside>
    </div>
  </main>
</template>
