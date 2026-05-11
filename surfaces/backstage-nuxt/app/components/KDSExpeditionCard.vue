<script setup lang="ts">
import type { KDSExpeditionCardProjection } from '~/types/backstage'

const props = defineProps<{ card: KDSExpeditionCardProjection }>()
const emit = defineEmits<{
  action: [{ orderPk: number, action: 'dispatch' | 'complete' }]
}>()

const actionLabel = computed(() => props.card.is_delivery ? 'Despachar' : 'Concluir')
const actionValue = computed(() => props.card.is_delivery ? 'dispatch' : 'complete' as const)
const actionIcon = computed(() => props.card.is_delivery ? 'i-lucide-truck' : 'i-lucide-circle-check')
</script>

<template>
  <UCard as="article">
    <template #header>
      <div class="flex items-center justify-between gap-3">
        <div class="min-w-0">
          <p class="font-mono text-sm text-muted">#{{ card.ref }}</p>
          <p class="font-semibold text-highlighted truncate">{{ card.customer_name }}</p>
        </div>
        <UBadge color="neutral" variant="subtle" size="md" class="shrink-0">
          {{ card.fulfillment_label }}
        </UBadge>
      </div>
    </template>

    <dl class="grid grid-cols-2 gap-3 text-sm">
      <div>
        <dt class="text-muted">Itens</dt>
        <dd class="font-semibold text-highlighted tabular-nums">{{ card.units_count }}</dd>
      </div>
      <div>
        <dt class="text-muted">Total</dt>
        <dd class="font-semibold text-highlighted tabular-nums">{{ card.total_display }}</dd>
      </div>
    </dl>

    <template #footer>
      <UButton
        block
        color="primary"
        :icon="actionIcon"
        :label="actionLabel"
        size="lg"
        @click="emit('action', { orderPk: card.pk, action: actionValue })"
      />
    </template>
  </UCard>
</template>
