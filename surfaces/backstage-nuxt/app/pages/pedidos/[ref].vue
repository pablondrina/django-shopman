<script setup lang="ts">
import type { OrderDetailResponse, OperatorOrderProjection, OrderCardProjection } from '~/types/backstage'

const route = useRoute()
const ref_ = computed(() => String(route.params.ref || ''))
const apiPath = useBackstageApiPath()
const action = useBackstageAction()
const router = useRouter()

const order = ref<OperatorOrderProjection | null>(null)
const loading = ref(false)
const errorMsg = ref<string | null>(null)
const acting = ref(false)
const cancelOpen = ref(false)

async function load () {
  loading.value = true
  errorMsg.value = null
  try {
    const res = await $fetch<OrderDetailResponse>(
      apiPath(`/api/v1/backstage/orders/${encodeURIComponent(ref_.value)}/`),
      { credentials: 'include' }
    )
    order.value = res?.order || null
  } catch (e: any) {
    errorMsg.value = e?.data?.detail || 'Falha ao carregar pedido.'
    order.value = null
  } finally {
    loading.value = false
  }
}

watchEffect(() => { if (ref_.value) void load() })

async function advance () {
  if (!order.value) return
  acting.value = true
  const res = await action.call(`/api/v1/backstage/orders/${encodeURIComponent(order.value.ref)}/advance/`, {
    successTitle: 'Pedido avançado'
  })
  if (res !== null) await load()
  acting.value = false
}

async function onCancelConfirm (payload: { order: OrderCardProjection, reason: string }) {
  acting.value = true
  const res = await action.call(`/api/v1/backstage/orders/${encodeURIComponent(payload.order.ref)}/cancel/`, {
    body: { reason: payload.reason },
    successTitle: 'Pedido cancelado'
  })
  if (res !== null) await load()
  cancelOpen.value = false
  acting.value = false
}

const cardProxy = computed<OrderCardProjection | null>(() => order.value
  ? { ref: order.value.ref, customer_name: order.value.customer_name } as OrderCardProjection
  : null)

const statusColor = (s: string) => {
  if (['cancelled', 'refused'].includes(s)) return 'error' as const
  if (['ready', 'completed', 'delivered'].includes(s)) return 'success' as const
  if (s === 'preparing') return 'warning' as const
  return 'neutral' as const
}

useHead(() => ({ title: order.value ? `${order.value.customer_name} · ${order.value.ref}` : 'Pedido' }))
</script>

<template>
  <UDashboardPanel id="pedido-detalhe">
    <template #header>
      <UDashboardNavbar
        :title="order?.customer_name || 'Pedido'"
        icon="i-lucide-clipboard-list"
      >
        <template #leading>
          <UDashboardSidebarCollapse />
        </template>
        <template #right>
          <UBadge v-if="order" :color="statusColor(order.status)" variant="subtle">
            {{ order.status_label }}
          </UBadge>
          <UButton
            color="neutral"
            variant="ghost"
            size="sm"
            icon="i-lucide-arrow-left"
            label="Voltar"
            @click="router.back()"
          />
        </template>
      </UDashboardNavbar>
    </template>

    <template #body>
      <USkeleton v-if="loading" class="h-40 w-full" />

      <UAlert v-else-if="errorMsg" color="error" variant="soft" :title="errorMsg" />

      <div v-else-if="order" class="grid lg:grid-cols-[2fr_1fr] gap-4 items-start">
        <div class="grid gap-4">
          <UCard>
            <template #header>
              <strong>Itens do pedido</strong>
            </template>
            <ul class="grid gap-2">
              <li
                v-for="item in order.items"
                :key="item.sku"
                class="flex items-start justify-between gap-3 py-2 border-b border-default last:border-0"
              >
                <div class="min-w-0">
                  <p class="font-semibold text-highlighted text-sm leading-tight">{{ item.name }}</p>
                  <p class="text-sm text-muted tabular-nums mt-0.5">
                    {{ item.qty }}× {{ item.unit_price_display }}
                  </p>
                </div>
                <strong class="text-sm tabular-nums whitespace-nowrap">{{ item.total_display }}</strong>
              </li>
            </ul>
            <template #footer>
              <div class="flex justify-between items-baseline">
                <span class="font-medium">Total</span>
                <strong class="text-2xl tabular-nums">{{ order.total_display }}</strong>
              </div>
            </template>
          </UCard>

          <UCard v-if="order.timeline?.length">
            <template #header>
              <strong>Linha do tempo</strong>
            </template>
            <ol class="grid gap-3">
              <li
                v-for="(event, idx) in order.timeline"
                :key="idx"
                class="flex items-start gap-3"
              >
                <UIcon name="i-lucide-circle-dot" class="size-4 text-muted mt-0.5 shrink-0" />
                <div class="min-w-0 flex-1">
                  <p class="text-sm font-semibold text-highlighted">{{ event.label }}</p>
                  <p v-if="event.detail" class="text-sm text-muted">{{ event.detail }}</p>
                  <p class="text-sm text-muted">
                    {{ event.timestamp_display }}<span v-if="event.actor"> · {{ event.actor }}</span>
                  </p>
                </div>
              </li>
            </ol>
          </UCard>
        </div>

        <div class="grid gap-4 lg:sticky lg:top-4">
          <UCard variant="subtle">
            <template #header>
              <strong>Cliente</strong>
            </template>
            <dl class="grid gap-2 text-sm">
              <div class="flex justify-between">
                <dt class="text-muted">Nome</dt>
                <dd class="font-semibold text-highlighted">{{ order.customer_name }}</dd>
              </div>
              <div class="flex justify-between">
                <dt class="text-muted">Tipo</dt>
                <dd>{{ order.fulfillment_label }}</dd>
              </div>
              <div class="flex justify-between">
                <dt class="text-muted">Pagamento</dt>
                <dd>{{ order.payment_method_label || '—' }}</dd>
              </div>
              <div v-if="order.payment_status" class="flex justify-between">
                <dt class="text-muted">Status pagamento</dt>
                <dd><UBadge color="neutral" variant="subtle" size="md">{{ order.payment_status }}</UBadge></dd>
              </div>
            </dl>
          </UCard>

          <UCard v-if="order.awaiting_work_orders?.length">
            <template #header>
              <strong class="flex items-center gap-2">
                <UIcon name="i-lucide-flame" class="size-4 text-warning" />
                Aguardando produção
              </strong>
            </template>
            <ul class="grid gap-3">
              <li v-for="wo in order.awaiting_work_orders" :key="wo.ref" class="grid gap-1">
                <div class="flex items-center justify-between text-sm">
                  <span>{{ wo.output_sku }}</span>
                  <UBadge color="neutral" variant="subtle" size="md">{{ wo.status_label }}</UBadge>
                </div>
                <p class="text-sm text-muted tabular-nums">{{ wo.finished_qty }} / {{ wo.planned_qty }}</p>
                <UProgress :model-value="wo.progress_pct" size="sm" />
              </li>
            </ul>
          </UCard>

          <UCard v-if="order.internal_notes">
            <template #header><strong>Notas internas</strong></template>
            <p class="text-sm whitespace-pre-wrap">{{ order.internal_notes }}</p>
          </UCard>

          <UCard variant="outline">
            <div class="grid gap-2">
              <UButton
                v-if="['new', 'confirmed', 'preparing', 'ready'].includes(order.status)"
                block
                color="primary"
                size="lg"
                icon="i-lucide-arrow-right"
                trailing
                label="Avançar status"
                :loading="acting"
                @click="advance"
              />
              <UButton
                v-if="!['cancelled', 'refused', 'completed'].includes(order.status)"
                block
                color="error"
                variant="ghost"
                size="md"
                icon="i-lucide-x"
                label="Cancelar pedido"
                :disabled="acting"
                @click="cancelOpen = true"
              />
            </div>
          </UCard>
        </div>
      </div>

      <OrderCancelModal
        v-model:open="cancelOpen"
        :order="cardProxy"
        @confirm="onCancelConfirm"
      />
    </template>
  </UDashboardPanel>
</template>
