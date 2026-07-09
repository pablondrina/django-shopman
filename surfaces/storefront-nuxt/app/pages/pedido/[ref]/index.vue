<script setup lang="ts">
import type { Action, TrackingResponse } from '~/types/shopman'
import {
  hasLiveDeadline,
  pollIntervalMs,
  timelineActiveStep,
  trackingFreshness,
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
// Ref esmaecido no prefixo (canal/data) + cauda em destaque (o que o cliente usa).
const refParts = computed(() => orderRefParts(orderRef.value))
// "Conversar com a loja" já abre com o contexto do pedido — o cliente não precisa
// explicar do zero qual pedido é.
const supportUrl = computed(() => withWhatsAppText(tracking.value?.whatsapp_url || '', `Preciso de ajuda com o pedido ${orderRef.value}`))
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
// Pedido em andamento: o próprio ícone do card pulsa (sinal "ao vivo") — sem
// bolinha extra ao lado do título, que competia com o ícone.
const statusPanelIconClassLive = computed(() =>
  tracking.value?.is_active ? `${statusPanelIconClass.value} animate-pulse` : statusPanelIconClass.value
)
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
const showReorderAction = computed(() => Boolean(
  reorderAction.value && !statusPanelActions.value.some(action => action.ref === 'reorder')
))
const showSupportAction = computed(() => Boolean(
  tracking.value?.whatsapp_url && !showSupportInStatusPanel.value
))
// Um (e só um) botão primary no card de Ações: o topo da pilha não-destrutiva.
// Prioridade: Avaliar > Pedir de novo > Falar conosco. Cancelar fica destructive
// à parte. Assim nunca sobra um card só com botões secundários (faubourg).
const sideActionsPrimary = computed(() => {
  if (rateAction.value) return 'rate'
  if (showReorderAction.value) return 'reorder'
  if (showSupportAction.value) return 'support'
  return null
})
const showSideActions = computed(() => Boolean(
  tracking.value &&
  (cancelAction.value || showReorderAction.value || showSupportAction.value)
))
const showDeliveryTab = computed(() => Boolean(tracking.value?.pickup_info || tracking.value?.fulfillments.length))
const deliveryTabLabel = computed(() => tracking.value?.is_delivery
  ? (tracking.value.copy.delivery_heading || 'Entrega')
  : (tracking.value?.pickup_info?.heading || 'Retirada'))
const trackingTabsListClass = 'no-scrollbar relative flex h-auto w-full justify-start gap-6 overflow-x-auto border-b bg-transparent p-0'
const trackingTabsTriggerClass = 'rounded-none border-b-2 border-transparent bg-transparent px-1 py-2 text-muted-foreground shadow-none data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:text-foreground data-[state=active]:shadow-none'
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

// Frescor do dado: idade viva "Atualizado há X", que vira aviso se um poll falhar
// (idade > 2× a janela de frescor do servidor). Só em pedidos ativos — um pedido
// finalizado não precisa de contagem, o carimbo estático basta.
const freshness = computed(() => trackingFreshness(
  tracking.value?.last_updated_iso,
  nowMs.value,
  (tracking.value?.stale_after_seconds ?? 30) * 2
))

// Reconexão / volta de foco → reconcilia NA HORA (não espera o próximo poll):
// grande alívio do "esperei e nada" quando o operador muda o status.
const { watchConnectivity } = useConnectivity()
watchConnectivity(() => { if (tracking.value?.is_active) void refresh() })

// Push instantâneo por SSE (G1): o backend emite no canal order-<ref> a cada
// mudança de status/pagamento; aqui refazemos o fetch canônico na hora, sem
// esperar o poll. Convidado sem login cai no poll (o Django recusa o canal dele).
useOrderTrackingStream(orderRef, () => { if (tracking.value?.is_active) void refresh() })

// Linhas do resumo (ícone + valor) — mesma diagramação do overlay de revisão do
// checkout (componente OrderSummaryRows), a partir da projeção do pedido.
const summaryRows = computed(() => {
  const t = tracking.value
  if (!t) return []
  const rows: { icon: string, lines: string[], muted?: string }[] = [
    { icon: t.is_delivery ? 'lucide:bike' : 'lucide:store', lines: [t.is_delivery ? (t.copy.delivery_heading || 'Entrega') : (t.pickup_info?.heading || 'Retirada')] }
  ]
  if (t.delivery_fee_display) {
    rows.push({ icon: 'lucide:coins', lines: [`Taxa ${t.delivery_fee_display}${t.delivery_distance_display ? ` · ${t.delivery_distance_display}` : ''}`] })
  }
  const paymentLabel = t.payment_status_label || t.payment_status
  if (paymentLabel) rows.push({ icon: 'lucide:credit-card', lines: [paymentLabel] })
  return rows
})

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
      method: action.method || 'POST',
      headers,
      credentials: 'include',
      body
    })
    await refresh()
    if (import.meta.client) useSonner.success('Atualizado.')
  } catch (e) {
    if (import.meta.client) useSonner.error(errorDetail(e, 'Não foi possível executar a ação.'))
  } finally {
    actionPending.value = omitKey(actionPending.value, action.ref)
  }
}

// Envia a avaliação e fecha o sheet (o rate_order some após avaliar, no refresh).
async function rateAndClose () {
  const action = rateAction.value
  if (!action) return
  supportOpen.value = false
  await postAction(action, { rating: rating.value, comment: comment.value })
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
  title: () => tracking.value ? `Pedido ${tracking.value.ref}` : 'Acompanhamento',
  description: () => tracking.value?.copy.page_meta_description || 'Acompanhe seu pedido'
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
          <p class="shop-kicker">{{ tracking?.copy.page_kicker || 'Acompanhamento' }}</p>
          <h1 class="mt-1 shop-title">
            {{ tracking?.copy.order_ref_label || 'Pedido' }}<br>
            <span class="text-xl font-normal text-muted-foreground">{{ refParts.prefix }}</span>{{ refParts.tail }}
          </h1>
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
            :icon-class="statusPanelIconClassLive"
          >
            <UiAlertTitle class="text-foreground">
              {{ tracking.promise.title || tracking.status_label }}
            </UiAlertTitle>
            <UiAlertDescription class="w-full text-muted-foreground">
              <div class="w-full shop-stack-block">
                <p>{{ tracking.promise.message || tracking.copy.promise_fallback_message }}</p>

                <!-- Aviso ativo: "também avisamos você por um canal ativo" (só quando o
                     sistema realmente notifica). Reduz a ansiedade de olhar a tela. -->
                <p v-if="tracking.promise.active_notification" class="flex items-center gap-2 shop-meta">
                  <Icon name="lucide:bell-ring" class="size-3.5 shrink-0" />
                  <span v-if="tracking.copy.active_notification_label" class="font-medium">{{ tracking.copy.active_notification_label }}</span>
                  {{ tracking.promise.active_notification }}
                </p>

                <div v-if="deadlineCount && !deadlineCount.isExpired" class="space-y-2" role="timer" aria-live="polite">
                  <div class="flex items-center gap-2 text-sm font-semibold">
                    <Icon name="lucide:timer" :size="18" :class="deadlineUrgent ? 'text-destructive' : statusPanelIconClass" />
                    <span class="text-muted-foreground">{{ tracking.promise_deadline_label || 'Tempo restante' }}</span>
                    <span class="ml-auto tabular-nums" :class="deadlineUrgent ? 'text-destructive' : 'text-foreground'">{{ deadlineCount.mmss }}</span>
                  </div>
                  <UiProgress :model-value="deadlinePct" :class="deadlineUrgent ? '[&>div]:bg-destructive' : ''" />
                </div>

                <p
                  v-if="tracking.is_active"
                  class="flex items-center gap-2 shop-muted"
                  :class="freshness.isStale ? 'text-destructive' : ''"
                  aria-live="polite"
                >
                  <Icon
                    v-if="freshness.isStale"
                    name="lucide:rotate-cw"
                    class="size-3.5 shrink-0 animate-spin"
                  />
                  <span>{{ freshness.text }}</span>
                  <span v-if="freshness.isStale">· reconectando…</span>
                </p>

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
                    <UiButton v-if="showSupportInStatusPanel" :href="supportUrl" target="_blank" variant="secondary" icon="lucide:message-circle">
                      {{ tracking.copy.support_label }}
                    </UiButton>
                  </div>
                </div>
              </div>
            </UiAlertDescription>
          </UiAlert>

          <UiCard class="py-3">
            <UiCardContent class="px-4 py-0">
              <UiTabs default-value="history" class="space-y-2">
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
                  <!-- Mesma diagramação do overlay de revisão: itens (qty + nome),
                       linhas ícone+valor e Total. Fonte = projeção do pedido. -->
                  <div class="px-1">
                    <ul v-if="tracking.items.length" class="space-y-1">
                      <li v-for="item in tracking.items" :key="item.sku" class="shop-body">
                        <span class="font-semibold tabular-nums">{{ item.qty }}×</span>
                        {{ item.name }}
                      </li>
                    </ul>

                    <UiSeparator class="my-3" />

                    <OrderSummaryRows :rows="summaryRows" />

                    <div class="mt-3 flex items-baseline justify-between border-t pt-3">
                      <span class="shop-body font-semibold">{{ tracking.copy.total_label }}</span>
                      <span class="font-semibold tabular-nums">{{ tracking.total_display }}</span>
                    </div>
                  </div>
                </UiTabsContent>

                <UiTabsContent v-if="showDeliveryTab" value="delivery">
                  <div class="shop-stack-block">
                    <UiAlert v-if="tracking.pickup_info">
                      <UiAlertTitle>Endereço</UiAlertTitle>
                      <UiAlertDescription>
                        {{ tracking.pickup_info.address }}
                        <UiButton v-if="tracking.pickup_info.directions_url" :href="tracking.pickup_info.directions_url" target="_blank" size="sm" class="mt-2 w-full border-transparent bg-brass text-brass-foreground hover:bg-brass/90 sm:w-auto">
                          {{ tracking.pickup_info.directions_label }}
                        </UiButton>
                      </UiAlertDescription>
                    </UiAlert>
                    <UiItem v-for="fulfillment in tracking.fulfillments" :key="`${fulfillment.status}-${fulfillment.tracking_code}`" class="rounded-lg border p-3">
                      <UiItemContent>
                        <UiItemTitle>{{ fulfillment.status_label }}</UiItemTitle>
                        <UiItemDescription v-if="fulfillment.tracking_label">{{ fulfillment.tracking_label }}</UiItemDescription>
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
        <UiCard class="gap-3 py-4">
          <UiCardHeader class="pb-0">
            <UiCardTitle>Ações</UiCardTitle>
          </UiCardHeader>
          <UiCardContent class="space-y-2">
            <!-- Avaliar em destaque (primary); as demais ficam secundárias. -->
            <UiButton v-if="rateAction" class="w-full" icon="lucide:star" @click="supportOpen = true">
              Avaliar pedido
            </UiButton>
            <UiButton
              v-if="showReorderAction"
              :variant="sideActionsPrimary === 'reorder' ? 'default' : 'secondary'"
              :loading="!!reorderPending[orderRef]"
              icon="lucide:rotate-ccw"
              class="w-full"
              @click="performReorderSafely(reorderAction!)"
            >
              {{ reorderAction!.label }}
            </UiButton>
            <UiButton v-if="showSupportAction" :href="supportUrl" target="_blank" :variant="sideActionsPrimary === 'support' ? 'default' : 'secondary'" icon="lucide:message-circle" class="w-full">
              {{ tracking.copy.support_label }}
            </UiButton>
            <UiAlertDialog v-if="cancelAction">
              <UiAlertDialogTrigger as-child>
                <UiButton variant="destructive" class="w-full">{{ tracking.copy.cancel_cta }}</UiButton>
              </UiAlertDialogTrigger>
              <UiAlertDialogContent>
                <UiAlertDialogHeader>
                  <UiAlertDialogTitle>{{ tracking.copy.cancel_dialog_title }}</UiAlertDialogTitle>
                  <UiAlertDialogDescription>{{ tracking.copy.cancel_dialog_message }}</UiAlertDialogDescription>
                </UiAlertDialogHeader>
                <UiAlertDialogFooter>
                  <UiAlertDialogCancel>{{ tracking.copy.cancel_dialog_back }}</UiAlertDialogCancel>
                  <UiAlertDialogAction @click="postAction(cancelAction)">{{ tracking.copy.cancel_dialog_confirm }}</UiAlertDialogAction>
                </UiAlertDialogFooter>
              </UiAlertDialogContent>
            </UiAlertDialog>
          </UiCardContent>
        </UiCard>

        <BottomSheet
          v-if="rateAction"
          v-model:open="supportOpen"
          max-width="md"
          title="Avaliar pedido"
          :description="tracking.copy.rating_thanks || 'Sua nota ajuda a loja a melhorar.'"
        >
          <div class="shop-stack-block px-4 py-4">
            <UiStarRating v-model="rating" :max="5" size="lg" class="justify-center" />
            <UiTextarea v-model="comment" :rows="3" :placeholder="tracking.copy.rating_comment_placeholder" />
          </div>
          <template #footer>
            <UiButton class="w-full" size="lg" @click="rateAndClose">{{ tracking.copy.rating_submit_label }}</UiButton>
          </template>
        </BottomSheet>
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
