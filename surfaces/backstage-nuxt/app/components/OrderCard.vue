<script setup lang="ts">
import type { OrderCardProjection } from '~/types/backstage'

const props = defineProps<{
  order: OrderCardProjection
  acting: boolean
  statusColor: (s: string) => 'error' | 'success' | 'warning' | 'neutral'
}>()

defineEmits<{
  advance: [OrderCardProjection]
  cancel: [OrderCardProjection]
  detail: [OrderCardProjection]
}>()

// Map Material Symbol ligatures (from Penguin projection) to Lucide icons.
const CHANNEL_LUCIDE: Record<string, string> = {
  language: 'i-lucide-globe',
  chat: 'i-lucide-message-circle',
  fastfood: 'i-lucide-utensils',
  storefront: 'i-lucide-store',
  shopping_bag: 'i-lucide-shopping-bag'
}
const FULFILLMENT_LUCIDE: Record<string, string> = {
  local_shipping: 'i-lucide-truck',
  storefront: 'i-lucide-store'
}

const channelIcon = computed(() => CHANNEL_LUCIDE[props.order.channel_icon] || 'i-lucide-circle')
const fulfillmentIcon = computed(() => FULFILLMENT_LUCIDE[props.order.fulfillment_icon] || 'i-lucide-circle')

const showTimer = computed(() => ['new', 'confirmed', 'preparing'].includes(props.order.status))
const { formatted } = useElapsedTimer(() => props.order.elapsed_seconds)

const timerColor = computed(() => {
  switch (props.order.timer_class) {
    case 'timer-urgent': return 'error' as const
    case 'timer-warning': return 'warning' as const
    case 'timer-muted': return 'neutral' as const
    default: return 'success' as const
  }
})

const ringClass = computed(() => {
  if (props.order.timer_class === 'timer-urgent') return 'ring-2 ring-error'
  if (props.order.timer_class === 'timer-warning') return 'ring-1 ring-warning'
  return ''
})

const awaitingPct = computed(() => {
  const wos = props.order.awaiting_work_orders
  if (!wos?.length) return null
  return Math.round(wos.reduce((s, w) => s + w.progress_pct, 0) / wos.length)
})

const hasIssues = computed(() =>
  props.order.payment_pending || props.order.has_notes || awaitingPct.value !== null
)
</script>

<template>
  <UCard
    :class="ringClass"
    :ui="{ body: 'p-3', header: 'p-0', footer: 'p-3' }"
  >
    <template #header>
      <button
        type="button"
        class="w-full text-left p-3 hover:bg-elevated/40 transition-colors grid gap-1.5"
        @click="$emit('detail', order)"
      >
        <div class="flex items-center justify-between gap-2">
          <div class="flex items-center gap-1.5 text-muted text-sm">
            <UIcon :name="channelIcon" class="size-4" :title="order.channel_ref" />
            <UIcon :name="fulfillmentIcon" class="size-4" />
            <span>{{ order.fulfillment_label }}</span>
          </div>
          <UBadge
            v-if="showTimer"
            :color="timerColor"
            variant="solid"
            size="md"
            class="tabular-nums"
          >
            {{ formatted }}
          </UBadge>
          <UBadge
            v-else
            :color="statusColor(order.status)"
            variant="subtle"
            size="md"
          >
            {{ order.status_label }}
          </UBadge>
        </div>

        <div class="flex items-baseline justify-between gap-3">
          <p class="font-semibold text-highlighted text-base leading-tight truncate flex-1">
            {{ order.customer_name }}
          </p>
          <strong class="text-lg font-bold text-highlighted tabular-nums whitespace-nowrap">
            {{ order.total_display }}
          </strong>
        </div>

        <div v-if="hasIssues" class="flex items-center gap-2 mt-0.5">
          <UTooltip v-if="order.payment_pending" text="Pagamento pendente">
            <UIcon name="i-lucide-credit-card" class="size-4 text-warning" />
          </UTooltip>
          <UTooltip v-if="order.has_notes" text="Notas internas">
            <UIcon name="i-lucide-message-square" class="size-4 text-info" />
          </UTooltip>
          <UTooltip v-if="awaitingPct !== null" :text="`Aguardando produção · ${awaitingPct}%`">
            <UIcon name="i-lucide-flame" class="size-4 text-warning" />
          </UTooltip>
        </div>
      </button>
    </template>

    <template #footer>
      <div class="flex gap-2">
        <UButton
          v-if="order.can_advance && order.next_action_label"
          color="primary"
          icon="i-lucide-arrow-right"
          trailing
          :label="order.next_action_label"
          size="md"
          :loading="acting"
          :disabled="order.payment_pending"
          class="flex-1"
          @click="$emit('advance', order)"
        />
        <UButton
          v-else-if="order.can_confirm"
          color="primary"
          icon="i-lucide-check"
          label="Confirmar"
          size="md"
          :loading="acting"
          class="flex-1"
          @click="$emit('advance', order)"
        />
        <UTooltip text="Cancelar pedido">
          <UButton
            color="neutral"
            variant="ghost"
            icon="i-lucide-x"
            size="md"
            aria-label="Cancelar pedido"
            :disabled="acting"
            @click="$emit('cancel', order)"
          />
        </UTooltip>
      </div>
    </template>
  </UCard>
</template>
