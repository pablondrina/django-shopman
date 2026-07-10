<script setup lang="ts">
import type { Action, TrackingResponse } from '~/types/shopman'
import {
  hasLiveDeadline,
  pollIntervalMs,
  timelineActiveStep,
  trackingPanelClass,
  trackingPanelIcon,
  trackingPanelIconClass,
  trackingStatusPanelActions,
  visibleTrackingPromiseRows
} from '~/presentation/orderTracking'
import { countdownPct, deadlineCountdown, isCountdownUrgent, serverClockOffsetMs } from '~/presentation/deadline'
import { orderAccessErrorView } from '~/presentation/orderAccess'

const route = useRoute()
const apiPath = useShopmanApiPath()
const csrfHeaders = useShopmanCsrfHeaders()
const orderRef = computed(() => String(route.params.ref || ''))
const rating = ref(5)
const comment = ref('')
const actionPending = ref<Record<string, boolean>>({})
const supportOpen = ref(false)
const { performAction: performReorderAction, conflict, pending: reorderPending } = useReorder()
// Forward the session cookie on SSR so order access resolves on first paint
// (same pattern as the account pages) — otherwise the server fetch lands
// unauthenticated and the page renders the "not found" fallback for a customer
// who can actually see this order.
const requestHeaders = import.meta.server ? useRequestHeaders(['cookie']) : undefined

const { data, pending, error, refresh } = await useFetch<TrackingResponse>(
  () => apiPath(`/api/v1/tracking/${encodeURIComponent(orderRef.value)}/`),
  { credentials: 'include', headers: requestHeaders }
)

const tracking = computed(() => data.value || null)
const errorView = computed(() => orderAccessErrorView((error.value as { statusCode?: number } | null)?.statusCode, 'tracking'))
const loginHref = computed(() => `/entrar?next=${encodeURIComponent(`/pedido/${orderRef.value}`)}`)
const paymentHref = computed(() => localRouteFromBackend(tracking.value?.payment_gate_url || tracking.value?.promise.actions.find(action => action.ref.includes('payment'))?.href || null))
const cancelAction = computed(() => tracking.value?.actions.find(action => action.ref === 'cancel_order' && action.enabled) || null)
const rateAction = computed(() => tracking.value?.actions.find(action => action.ref === 'rate_order' && action.enabled) || null)
const reorderAction = computed(() => tracking.value?.actions.find(action => action.ref === 'reorder' && action.enabled) || null)
const promiseActions = computed(() => tracking.value?.promise.actions.filter(action => action.enabled) || [])
const promiseTone = computed(() => tracking.value?.promise.tone || 'info')
const statusPanelActions = computed(() => trackingStatusPanelActions(promiseActions.value, reorderAction.value, promiseTone.value))
const statusPanelClass = computed(() => trackingPanelClass(promiseTone.value))
const statusPanelIconClass = computed(() => trackingPanelIconClass(promiseTone.value))
const statusPanelIcon = computed(() => trackingPanelIcon(promiseTone.value))
const showPaymentStatusFallback = computed(() => Boolean(
  tracking.value?.requires_payment_gate &&
  !statusPanelActions.value.some(action => action.ref === 'pay_now' || action.ref.includes('payment'))
))
// "Fale conosco" em destaque quando há risco (danger) e quando o pedido saiu para
// entrega — o trecho mais sensível, com courier terceirizado e sem rastreio.
const showSupportInStatusPanel = computed(() => Boolean(
  tracking.value?.whatsapp_url &&
  (promiseTone.value === 'danger' || tracking.value?.promise.state === 'dispatched')
))
const hasStatusPanelActions = computed(() => Boolean(
  statusPanelActions.value.length ||
  showPaymentStatusFallback.value ||
  showSupportInStatusPanel.value
))
const visiblePromiseRows = computed(() => visibleTrackingPromiseRows(tracking.value?.promise_rows || []))
const showSideActions = computed(() => Boolean(
  tracking.value &&
  (
    cancelAction.value ||
    (reorderAction.value && !statusPanelActions.value.some(action => action.ref === 'reorder')) ||
    (tracking.value.whatsapp_url && !showSupportInStatusPanel.value)
  )
))
const showDeliveryTab = computed(() => Boolean(tracking.value?.pickup_info || tracking.value?.fulfillments.length))
const deliveryTabLabel = computed(() => tracking.value?.is_delivery ? 'Entrega' : 'Retirada')
const trackingTabsListClass = 'no-scrollbar before:bg-border relative h-auto w-full justify-start gap-1 overflow-x-auto bg-transparent p-0 before:absolute before:inset-x-0 before:bottom-0 before:h-px'
const trackingTabsTriggerClass = 'border-border bg-muted overflow-hidden rounded-b-none border-x border-t py-2 data-[state=active]:z-10 data-[state=active]:shadow-none'
const progressTimelineStep = computed(() => timelineActiveStep(tracking.value?.progress_steps || []))

// Deadline vivo (timeouts transparentes): countdown ancorado em server_now_iso
// quando a promise pede contagem (ex.: prazo de confirmação/pagamento).
const clientNow = ref(Date.now())
const serverOffset = computed(() => serverClockOffsetMs(tracking.value?.server_now_iso, Date.now()))
const nowMs = computed(() => clientNow.value + serverOffset.value)
const deadlineLive = computed(() => tracking.value && hasLiveDeadline(tracking.value.promise))
const deadlineCount = computed(() => deadlineLive.value ? deadlineCountdown(tracking.value!.promise.deadline_at, nowMs.value) : null)
// Barra de tempo restante: a janela é ancorada no que sobra no primeiro render
// (a projeção não expõe o início real) e a barra drena honestamente de cheia a
// vazia. Re-ancora se o deadline mudar (ex.: novo prazo num novo estado).
const deadlineWindowSeconds = ref(0)
watch(() => tracking.value?.promise.deadline_at, () => { deadlineWindowSeconds.value = 0 })
watch(deadlineCount, count => {
  if (count && count.totalSeconds > 0 && deadlineWindowSeconds.value === 0) {
    deadlineWindowSeconds.value = count.totalSeconds
  }
}, { immediate: true })
const deadlinePct = computed(() => deadlineCount.value ? countdownPct(deadlineCount.value.totalSeconds, deadlineWindowSeconds.value) : 0)
const deadlineUrgent = computed(() => isCountdownUrgent(deadlinePct.value))

let tick: ReturnType<typeof setInterval> | null = null
let poll: ReturnType<typeof setInterval> | null = null
let deadlineHandled = false
onMounted(() => {
  tick = setInterval(() => { clientNow.value = Date.now() }, 1000)
  poll = setInterval(() => {
    if (tracking.value?.is_active) void refresh()
  }, pollIntervalMs(tracking.value?.stale_after_seconds))
})
onBeforeUnmount(() => {
  if (tick) clearInterval(tick)
  if (poll) clearInterval(poll)
})

// Ao zerar o prazo, o backend decide (deadline_action): a UI sincroniza uma vez.
watch(() => deadlineCount.value?.isExpired, async expired => {
  if (expired && !deadlineHandled && tracking.value?.is_active) {
    deadlineHandled = true
    await refresh()
  }
})

async function postAction (action: Action, body: Record<string, unknown> = {}) {
  actionPending.value = { ...actionPending.value, [action.ref]: true }
  try {
    const headers = await csrfHeaders()
    if (action.idempotency === 'required' || action.idempotency === 'recommended') {
      headers['x-idempotency-key'] = newRemoteMutationKey(action.ref)
    }
    await $fetch(apiPath(action.href), {
      method: remoteMethod(action.method),
      headers,
      credentials: 'include',
      body
    })
    await refresh()
    if (import.meta.client) useSonner.success('Atualizado.')
  } catch (e: any) {
    if (import.meta.client) useSonner.error(e?.data?.detail || 'Não foi possível executar a ação.')
  } finally {
    const next = { ...actionPending.value }
    delete next[action.ref]
    actionPending.value = next
  }
}

function actionRoute (action: Action) {
  return localRouteFromBackend(action.href || null)
}

function actionIcon (action: Action) {
  if (action.ref === 'reorder') return 'lucide:rotate-ccw'
  if (action.ref === 'pay_now' || action.ref.includes('payment')) return 'lucide:credit-card'
  if (action.ref === 'confirm_received') return 'lucide:package-check'
  return 'lucide:arrow-right'
}

function canRunInlineAction (action: Action) {
  return action.kind === 'mutation'
}

async function handleStatusPanelAction (action: Action) {
  if (action.ref === 'reorder') {
    await performReorderSafely(action)
    return
  }
  if (action.kind === 'mutation') {
    await postAction(action)
  }
}

async function performReorderSafely (action: Action | null | undefined) {
  if (!action) return
  await performReorderAction(action).catch(() => null)
}

function dismissReorderConflict () {
  conflict.value = null
}

useSeoMeta({
  title: () => tracking.value ? `Pedido ${tracking.value.ref}` : 'Acompanhamento'
})
</script>

<template>
  <main class="shop-section pt-0">
    <div class="shop-breadcrumb-bar mb-4">
      <div class="shop-container py-2">
        <UiBreadcrumbs
          :items="[
            { label: 'Início', link: '/' },
            { label: 'Pedidos', link: '/conta' },
            { label: `Pedido ${orderRef}` }
          ]"
        />
      </div>
    </div>
    <div class="shop-container grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
      <section class="shop-stack-block">
        <div>
          <p class="shop-kicker">Acompanhamento</p>
          <h1 class="mt-1 shop-title">Pedido {{ orderRef }}</h1>
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

        <template v-else-if="tracking">
          <UiAlert
            variant="default"
            :class="statusPanelClass"
            :icon="statusPanelIcon"
            :icon-class="statusPanelIconClass"
          >
            <UiAlertTitle class="text-foreground">{{ tracking.promise.title || tracking.status_label }}</UiAlertTitle>
            <UiAlertDescription class="w-full text-muted-foreground">
              <div class="w-full shop-stack-block">
                <p>{{ tracking.promise.message || tracking.copy.promise_fallback_message }}</p>

                <div v-if="deadlineCount && !deadlineCount.isExpired" class="space-y-2" role="timer" aria-live="polite">
                  <div class="flex items-center gap-2 text-sm font-semibold">
                    <Icon name="lucide:timer" :size="18" :class="deadlineUrgent ? 'text-destructive' : statusPanelIconClass" />
                    <span class="text-muted-foreground">{{ tracking.promise_deadline_label || 'Tempo restante' }}</span>
                    <span class="ml-auto tabular-nums" :class="deadlineUrgent ? 'text-destructive' : 'text-foreground'">{{ deadlineCount.mmss }}</span>
                  </div>
                  <UiProgress :model-value="deadlinePct" :class="deadlineUrgent ? '[&>div]:bg-destructive' : ''" />
                </div>

                <p class="shop-muted">{{ tracking.last_updated_display }}</p>

                <div v-if="visiblePromiseRows.length" class="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <div v-for="row in visiblePromiseRows" :key="row.label" class="rounded-lg border bg-card p-3 shop-body">
                    <p class="text-muted-foreground">{{ row.label }}</p>
                    <a v-if="row.url" :href="row.url" target="_blank" class="font-semibold text-primary">{{ row.value }}</a>
                    <p v-else class="font-semibold text-foreground">{{ row.value }}</p>
                  </div>
                </div>

                <div v-if="hasStatusPanelActions" class="w-full pt-1">
                  <span class="sr-only">Ações disponíveis</span>
                  <div class="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
                    <template v-for="action in statusPanelActions" :key="action.ref">
                      <UiButton
                        v-if="action.ref === 'reorder'"
                        :icon="actionIcon(action)"
                        :loading="!!reorderPending[orderRef]"
                        @click="handleStatusPanelAction(action)"
                      >
                        {{ action.label }}
                      </UiButton>
                      <UiButton
                        v-else-if="action.kind === 'link' && action.href"
                        :to="actionRoute(action)"
                        :icon="actionIcon(action)"
                      >
                        {{ action.label }}
                      </UiButton>
                      <UiButton
                        v-else-if="canRunInlineAction(action)"
                        :icon="actionIcon(action)"
                        :loading="!!actionPending[action.ref]"
                        @click="handleStatusPanelAction(action)"
                      >
                        {{ action.label }}
                      </UiButton>
                    </template>
                    <UiButton v-if="showPaymentStatusFallback" :to="paymentHref" icon="lucide:credit-card">
                      Regularizar pagamento
                    </UiButton>
                    <UiButton v-if="showSupportInStatusPanel" :href="tracking.whatsapp_url" target="_blank" variant="outline" icon="lucide:message-circle">
                      {{ tracking.copy.support_label }}
                    </UiButton>
                  </div>
                </div>
              </div>
            </UiAlertDescription>
          </UiAlert>

          <UiCard>
            <UiCardContent class="p-4">
              <UiTabs default-value="history" class="space-y-4">
                <UiTabsList :pill="false" :class="trackingTabsListClass">
                  <UiTabsTrigger :pill="false" value="history" :class="trackingTabsTriggerClass">Histórico</UiTabsTrigger>
                  <UiTabsTrigger :pill="false" value="summary" :class="trackingTabsTriggerClass">Resumo</UiTabsTrigger>
                  <UiTabsTrigger v-if="showDeliveryTab" :pill="false" value="delivery" :class="trackingTabsTriggerClass">{{ deliveryTabLabel }}</UiTabsTrigger>
                </UiTabsList>

                <UiTabsContent value="history">
                  <UiTimeline :model-value="progressTimelineStep">
                    <UiTimelineItem
                      v-for="(step, index) in tracking.progress_steps"
                      :key="step.key"
                      :step="index + 1"
                      class="group-data-[orientation=vertical]/timeline:ms-10"
                    >
                      <UiTimelineHeader>
                        <UiTimelineSeparator
                          class="group-data-[orientation=vertical]/timeline:-left-7 group-data-[orientation=vertical]/timeline:h-[calc(100%-1.5rem-0.25rem)] group-data-[orientation=vertical]/timeline:translate-y-6.5"
                        />
                        <UiTimelineDate v-if="step.timestamp_display">{{ step.timestamp_display }}</UiTimelineDate>
                        <UiTimelineTitle>{{ step.label }}</UiTimelineTitle>
                        <UiTimelineIndicator
                          class="group-data-completed/timeline-item:bg-primary group-data-completed/timeline-item:text-primary-foreground flex size-6 items-center justify-center group-data-completed/timeline-item:border-none group-data-[orientation=vertical]/timeline:-left-7"
                        >
                          <Icon
                            name="lucide:check"
                            :size="16"
                            class="group-not-data-completed/timeline-item:hidden"
                          />
                        </UiTimelineIndicator>
                      </UiTimelineHeader>
                    </UiTimelineItem>
                  </UiTimeline>
                </UiTabsContent>

                <UiTabsContent value="summary">
                  <div class="shop-stack-block">
                    <section class="space-y-2">
                      <p class="shop-kicker">Resumo do pedido</p>
                      <UiDescriptionList class="rounded-lg border px-3">
                        <UiDescriptionListTerm>{{ tracking.copy.total_label }}</UiDescriptionListTerm>
                        <UiDescriptionListDetails class="font-semibold">{{ tracking.total_display }}</UiDescriptionListDetails>

                        <UiDescriptionListTerm>Recebimento</UiDescriptionListTerm>
                        <UiDescriptionListDetails>{{ tracking.is_delivery ? 'Entrega' : 'Retirada' }}</UiDescriptionListDetails>

                        <UiDescriptionListTerm v-if="tracking.payment_status_label || tracking.payment_status">Pagamento</UiDescriptionListTerm>
                        <UiDescriptionListDetails v-if="tracking.payment_status_label || tracking.payment_status">{{ tracking.payment_status_label || tracking.payment_status }}</UiDescriptionListDetails>

                        <UiDescriptionListTerm v-if="tracking.delivery_fee_display">
                          {{ tracking.copy.delivery_fee_label }}<span v-if="tracking.delivery_distance_display" class="shop-muted"> · {{ tracking.delivery_distance_display }}</span>
                        </UiDescriptionListTerm>
                        <UiDescriptionListDetails v-if="tracking.delivery_fee_display">{{ tracking.delivery_fee_display }}</UiDescriptionListDetails>
                      </UiDescriptionList>
                    </section>

                    <section v-if="tracking.items.length" class="space-y-2">
                      <p class="shop-kicker">{{ tracking.copy.items_heading }}</p>
                      <UiItemGroup class="rounded-lg border">
                        <UiItem v-for="item in tracking.items" :key="item.sku" class="border-b px-3 py-3 last:border-b-0">
                          <UiItemContent>
                            <UiItemTitle>{{ item.name }}</UiItemTitle>
                            <UiItemDescription>{{ item.qty }} x {{ item.unit_price_display }}</UiItemDescription>
                          </UiItemContent>
                          <UiItemActions>{{ item.total_display }}</UiItemActions>
                        </UiItem>
                      </UiItemGroup>
                    </section>
                  </div>
                </UiTabsContent>

                <UiTabsContent v-if="showDeliveryTab" value="delivery">
                  <div class="shop-stack-block">
                    <UiAlert v-if="tracking.pickup_info">
                      <UiAlertTitle>Endereço</UiAlertTitle>
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
                  </div>
                </UiTabsContent>
              </UiTabs>
            </UiCardContent>
          </UiCard>
        </template>
      </section>

      <aside v-if="tracking && (showSideActions || rateAction)" class="space-y-4 lg:sticky lg:top-24 lg:self-start">
        <UiCard v-if="showSideActions">
          <UiCardHeader>
            <UiCardTitle>Ações</UiCardTitle>
          </UiCardHeader>
          <UiCardContent class="space-y-2">
            <UiButton
              v-if="reorderAction && !statusPanelActions.some(action => action.ref === 'reorder')"
              :loading="!!reorderPending[orderRef]"
              icon="lucide:rotate-ccw"
              class="w-full"
              @click="performReorderSafely(reorderAction)"
            >
              {{ reorderAction.label }}
            </UiButton>
            <UiButton v-if="tracking.whatsapp_url && !showSupportInStatusPanel" :href="tracking.whatsapp_url" target="_blank" variant="outline" icon="lucide:message-circle" class="w-full">
              {{ tracking.copy.support_label }}
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
              <UiTextarea v-model="comment" :rows="3" />
            </div>
            <UiDialogFooter>
              <UiButton @click="postAction(rateAction, { rating, comment })">{{ tracking.copy.rating_submit_label }}</UiButton>
            </UiDialogFooter>
          </UiDialogContent>
        </UiDialog>
      </aside>

      <UiAlertDialog :open="!!conflict" @update:open="open => { if (!open) dismissReorderConflict() }">
        <UiAlertDialogContent>
          <UiAlertDialogHeader>
            <UiAlertDialogTitle>{{ conflict?.copy.title.title || 'Sacola já tem itens' }}</UiAlertDialogTitle>
            <UiAlertDialogDescription>{{ conflict?.copy.message.message || conflict?.detail }}</UiAlertDialogDescription>
          </UiAlertDialogHeader>
          <UiAlertDialogFooter>
            <UiAlertDialogCancel>Cancelar</UiAlertDialogCancel>
            <UiAlertDialogAction v-if="conflict" @click="performReorderSafely(conflict.actions.find(action => action.ref.includes('replace')) || conflict.actions[0])">
              Substituir
            </UiAlertDialogAction>
          </UiAlertDialogFooter>
        </UiAlertDialogContent>
      </UiAlertDialog>
    </div>
  </main>
</template>
