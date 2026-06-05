<script setup lang="ts">
import type { Action, TrackingResponse } from '~/types/shopman'

const route = useRoute()
const apiPath = useShopmanApiPath()
const csrfHeaders = useShopmanCsrfHeaders()
const orderRef = computed(() => String(route.params.ref || ''))
const rating = ref(5)
const comment = ref('')
const actionPending = ref<Record<string, boolean>>({})
const supportOpen = ref(false)
const { performAction: performReorderAction, conflict, pending: reorderPending } = useReorder()

const { data, pending, error, refresh } = await useFetch<TrackingResponse>(
  () => apiPath(`/api/v1/tracking/${encodeURIComponent(orderRef.value)}/`),
  { credentials: 'include' }
)

const tracking = computed(() => data.value || null)
const paymentHref = computed(() => localRouteFromBackend(tracking.value?.payment_gate_url || tracking.value?.promise.actions.find(action => action.ref.includes('payment'))?.href || null))
const cancelAction = computed(() => tracking.value?.actions.find(action => action.ref === 'cancel_order' && action.enabled) || null)
const rateAction = computed(() => tracking.value?.actions.find(action => action.ref === 'rate_order' && action.enabled) || null)
const reorderAction = computed(() => tracking.value?.actions.find(action => action.ref === 'reorder' && action.enabled) || null)
const promiseActions = computed(() => tracking.value?.promise.actions.filter(action => action.enabled) || [])
const promiseTone = computed(() => tracking.value?.promise.tone || 'info')
const statusPanelActions = computed(() => {
  const actions = [...promiseActions.value]
  if (promiseTone.value === 'danger' && reorderAction.value && !actions.some(action => action.ref === 'reorder')) {
    actions.unshift(reorderAction.value)
  }
  return actions
})
const statusPanelClass = computed(() => {
  if (promiseTone.value === 'danger') return 'border-l-4 border-border border-l-destructive bg-card text-foreground shadow-sm'
  if (promiseTone.value === 'warning') return 'border-l-4 border-border border-l-amber-500 bg-card text-foreground shadow-sm'
  if (promiseTone.value === 'success') return 'border-l-4 border-border border-l-emerald-500 bg-card text-foreground shadow-sm'
  return 'border-l-4 border-border border-l-blue-500 bg-card text-foreground shadow-sm'
})
const statusPanelIconClass = computed(() => {
  if (promiseTone.value === 'danger') return 'text-destructive'
  if (promiseTone.value === 'warning') return 'text-amber-600'
  if (promiseTone.value === 'success') return 'text-emerald-600'
  return 'text-blue-600'
})
const statusPanelIcon = computed(() => {
  if (promiseTone.value === 'danger') return 'lucide:triangle-alert'
  if (promiseTone.value === 'warning') return 'lucide:circle-alert'
  if (promiseTone.value === 'success') return 'lucide:circle-check'
  return 'lucide:info'
})
const showPaymentStatusFallback = computed(() => Boolean(
  tracking.value?.requires_payment_gate &&
  !statusPanelActions.value.some(action => action.ref === 'pay_now' || action.ref.includes('payment'))
))
const showSupportInStatusPanel = computed(() => Boolean(tracking.value?.whatsapp_url && promiseTone.value === 'danger'))
const hasStatusPanelActions = computed(() => Boolean(
  statusPanelActions.value.length ||
  showPaymentStatusFallback.value ||
  showSupportInStatusPanel.value
))
const visiblePromiseRows = computed(() => {
  const hiddenLabels = ['última atualização', 'sua ação']
  return (tracking.value?.promise_rows || []).filter(row => {
    const label = row.label.toLocaleLowerCase('pt-BR')
    return !hiddenLabels.some(hidden => label.includes(hidden))
  })
})
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
const trackingTabsListClass = 'no-scrollbar before:bg-border relative h-auto w-full justify-start gap-0.5 overflow-x-auto bg-transparent p-0 before:absolute before:inset-x-0 before:bottom-0 before:h-px'
const trackingTabsTriggerClass = 'border-border bg-muted overflow-hidden rounded-b-none border-x border-t py-2 data-[state=active]:z-10 data-[state=active]:shadow-none'
const progressTimelineStep = computed(() => {
  const steps = tracking.value?.progress_steps || []
  if (!steps.length) return undefined
  const active = steps.findIndex(step => step.state === 'current' || step.state === 'cancelled')
  if (active >= 0) return active + 1
  return Math.max(steps.filter(step => step.state === 'completed').length, 1)
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
  <main class="shop-section">
    <div class="shop-container grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
      <section class="space-y-5">
        <UiBreadcrumbs
          :items="[
            { label: 'Início', link: '/' },
            { label: 'Pedidos', link: '/account' },
            { label: `Pedido ${orderRef}` }
          ]"
        />

        <div>
          <p class="shop-kicker">Acompanhamento</p>
          <h1 class="mt-1 text-3xl font-semibold">Pedido {{ orderRef }}</h1>
        </div>

        <UiSkeleton v-if="pending" class="h-96 rounded-lg" />

        <UiAlert v-else-if="error" variant="destructive">
          <UiAlertTitle>Pedido não encontrado</UiAlertTitle>
          <UiAlertDescription>
            <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <span>Não conseguimos carregar o acompanhamento agora.</span>
              <UiButton size="sm" variant="outline" @click="refresh">Atualizar</UiButton>
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
              <div class="w-full space-y-3">
                <p>{{ tracking.promise.message || tracking.copy.promise_fallback_message }}</p>

                <p class="text-sm text-muted-foreground">{{ tracking.last_updated_display }}</p>

                <div v-if="visiblePromiseRows.length" class="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <div v-for="row in visiblePromiseRows" :key="row.label" class="rounded-lg border bg-background/60 p-3 text-sm">
                    <p class="text-muted-foreground">{{ row.label }}</p>
                    <a v-if="row.url" :href="row.url" target="_blank" class="font-medium text-primary">{{ row.value }}</a>
                    <p v-else class="font-medium text-foreground">{{ row.value }}</p>
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
                  <div class="space-y-5">
                    <section class="space-y-2">
                      <p class="text-xs font-medium uppercase text-muted-foreground">Resumo do pedido</p>
                      <UiDescriptionList class="rounded-lg border px-3">
                        <UiDescriptionListTerm>{{ tracking.copy.total_label }}</UiDescriptionListTerm>
                        <UiDescriptionListDetails class="font-semibold">{{ tracking.total_display }}</UiDescriptionListDetails>

                        <UiDescriptionListTerm>Recebimento</UiDescriptionListTerm>
                        <UiDescriptionListDetails class="font-medium">{{ tracking.is_delivery ? 'Entrega' : 'Retirada' }}</UiDescriptionListDetails>

                        <UiDescriptionListTerm v-if="tracking.payment_status_label || tracking.payment_status">Pagamento</UiDescriptionListTerm>
                        <UiDescriptionListDetails v-if="tracking.payment_status_label || tracking.payment_status" class="font-medium">{{ tracking.payment_status_label || tracking.payment_status }}</UiDescriptionListDetails>

                        <UiDescriptionListTerm v-if="tracking.delivery_fee_display">{{ tracking.copy.delivery_fee_label }}</UiDescriptionListTerm>
                        <UiDescriptionListDetails v-if="tracking.delivery_fee_display" class="font-medium">{{ tracking.delivery_fee_display }}</UiDescriptionListDetails>
                      </UiDescriptionList>
                    </section>

                    <section v-if="tracking.items.length" class="space-y-2">
                      <p class="text-xs font-medium uppercase text-muted-foreground">{{ tracking.copy.items_heading }}</p>
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
                  <div class="space-y-3">
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
              <UiTextarea v-model="comment" rows="3" />
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
            <UiAlertDialogTitle>{{ conflict?.copy.title.title || 'Carrinho já tem itens' }}</UiAlertDialogTitle>
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
