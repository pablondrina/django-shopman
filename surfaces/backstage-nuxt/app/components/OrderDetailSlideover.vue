<script setup lang="ts">
import { breakpointsTailwind, useBreakpoints } from '@vueuse/core'
import type { OrderDetailResponse, OperatorOrderProjection } from '~/types/backstage'

const props = defineProps<{ open: boolean, orderRef: string | null }>()
const emit = defineEmits<{ 'update:open': [boolean] }>()

const breakpoints = useBreakpoints(breakpointsTailwind)
const isMobile = breakpoints.smaller('sm')
const slideoverSide = computed(() => isMobile.value ? 'bottom' : 'right')
const slideoverUi = computed(() => isMobile.value
  ? { content: 'max-h-[85vh] rounded-t-xl' }
  : { content: 'max-w-xl' })

const apiPath = useBackstageApiPath()
const order = ref<OperatorOrderProjection | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)

async function load () {
  if (!props.orderRef) return
  loading.value = true
  error.value = null
  try {
    const res = await $fetch<OrderDetailResponse>(
      apiPath(`/api/v1/backstage/orders/${encodeURIComponent(props.orderRef)}/`),
      { credentials: 'include' }
    )
    order.value = res?.order || null
  } catch (e: any) {
    error.value = e?.data?.detail || 'Falha ao carregar pedido.'
    order.value = null
  } finally {
    loading.value = false
  }
}

watchEffect(() => {
  if (props.open && props.orderRef) void load()
  if (!props.open) order.value = null
})

const statusColor = (s: string) => {
  if (['cancelled', 'refused'].includes(s)) return 'error' as const
  if (['ready', 'completed', 'delivered'].includes(s)) return 'success' as const
  if (s === 'preparing') return 'warning' as const
  return 'neutral' as const
}
</script>

<template>
  <USlideover
    :open="open"
    :side="slideoverSide"
    :ui="slideoverUi"
    @update:open="emit('update:open', $event)"
  >
    <template #title>
      <span v-if="order" class="text-highlighted">{{ order.customer_name }}</span>
      <span v-else>Pedido</span>
    </template>

    <template #actions>
      <UTooltip text="Abrir em tela cheia">
        <UButton
          v-if="order"
          :to="`/pedidos/${order.ref}`"
          color="neutral"
          variant="ghost"
          size="sm"
          icon="i-lucide-external-link"
          aria-label="Abrir em tela cheia"
          @click="emit('update:open', false)"
        />
      </UTooltip>
    </template>

    <template #description>
      <span v-if="order" class="flex items-center gap-2 flex-wrap">
        <UBadge :color="statusColor(order.status)" variant="subtle" size="md">
          {{ order.status_label }}
        </UBadge>
        <span class="text-muted">{{ order.fulfillment_label }} · {{ order.total_display }}</span>
        <span class="text-dimmed">·</span>
        <span class="text-dimmed text-xs">{{ order.ref }}</span>
      </span>
    </template>

    <template #body>
      <USkeleton v-if="loading" class="h-40" />

      <UAlert v-else-if="error" color="error" variant="soft" :title="error" />

      <div v-else-if="order" class="grid gap-5">
        <UCard variant="subtle" :ui="{ body: 'p-4' }">
          <div class="grid gap-1.5 text-sm">
            <div class="flex justify-between">
              <span class="text-muted">Cliente</span>
              <span class="font-semibold text-highlighted">{{ order.customer_name }}</span>
            </div>
            <div class="flex justify-between">
              <span class="text-muted">Pagamento</span>
              <span>{{ order.payment_method_label || '—' }}</span>
            </div>
            <div v-if="order.payment_status" class="flex justify-between">
              <span class="text-muted">Status do pagamento</span>
              <UBadge color="neutral" variant="subtle" size="md">{{ order.payment_status }}</UBadge>
            </div>
          </div>
        </UCard>

        <section>
          <h3 class="text-sm font-semibold text-highlighted uppercase tracking-wide mb-2">Itens</h3>
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
          <div class="flex justify-between items-baseline pt-3 mt-3 border-t border-default">
            <span class="font-medium">Total</span>
            <strong class="text-xl tabular-nums">{{ order.total_display }}</strong>
          </div>
        </section>

        <section v-if="order.awaiting_work_orders?.length">
          <h3 class="text-sm font-semibold text-highlighted uppercase tracking-wide mb-2 flex items-center gap-2">
            <UIcon name="i-lucide-flame" class="size-4 text-warning" />
            Aguardando produção
          </h3>
          <ul class="grid gap-2">
            <li
              v-for="wo in order.awaiting_work_orders"
              :key="wo.ref"
              class="rounded-md border border-default px-3 py-2 grid gap-1"
            >
              <div class="flex items-center justify-between">
                <span class="font-mono text-sm">{{ wo.ref }}</span>
                <UBadge color="neutral" variant="subtle" size="md">{{ wo.status_label }}</UBadge>
              </div>
              <p class="text-sm text-muted">{{ wo.output_sku }} · {{ wo.finished_qty }}/{{ wo.planned_qty }}</p>
              <UProgress :model-value="wo.progress_pct" size="sm" />
            </li>
          </ul>
        </section>

        <section v-if="order.internal_notes">
          <h3 class="text-sm font-semibold text-highlighted uppercase tracking-wide mb-2">Notas internas</h3>
          <UCard variant="subtle" :ui="{ body: 'p-3' }">
            <p class="text-sm whitespace-pre-wrap">{{ order.internal_notes }}</p>
          </UCard>
        </section>

        <section v-if="order.timeline?.length">
          <h3 class="text-sm font-semibold text-highlighted uppercase tracking-wide mb-2">Linha do tempo</h3>
          <ol class="grid gap-2">
            <li
              v-for="(event, idx) in order.timeline"
              :key="idx"
              class="flex items-start gap-3 py-2 border-b border-default last:border-0"
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
        </section>
      </div>
    </template>
  </USlideover>
</template>
