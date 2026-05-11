<script setup lang="ts">
import type { KDSTicketProjection } from '~/types/backstage'

const props = defineProps<{ ticket: KDSTicketProjection }>()
const emit = defineEmits<{
  itemToggle: [{ ticketPk: number, index: number, checked: boolean }]
  done: [number]
}>()

const { formatted } = useElapsedTimer(() => props.ticket.elapsed_seconds)

const timerColor = computed(() => {
  switch (props.ticket.timer_class) {
    case 'timer-late': return 'error' as const
    case 'timer-warning': return 'warning' as const
    default: return 'success' as const
  }
})

const checkedCount = computed(() => props.ticket.items.filter(i => i.checked).length)

const itemsWithNotes = computed(() => props.ticket.items.filter(i => i.notes))
const stockWarnings = computed(() => props.ticket.items.filter(i => i.stock_warning))

function onToggle (index: number, current: boolean) {
  emit('itemToggle', { ticketPk: props.ticket.pk, index, checked: !current })
}

function onDone () {
  emit('done', props.ticket.pk)
}
</script>

<template>
  <UCard
    as="article"
    :class="[
      ticket.timer_class === 'timer-late' && 'ring-2 ring-error',
      ticket.timer_class === 'timer-warning' && 'ring-1 ring-warning'
    ]"
  >
    <template #header>
      <div class="flex items-center justify-between gap-3">
        <div class="min-w-0">
          <p class="text-sm text-muted">#{{ ticket.order_ref }}</p>
          <p class="font-semibold text-highlighted truncate">{{ ticket.customer_name }}</p>
        </div>
        <UBadge :color="timerColor" variant="solid" size="md" class="tabular-nums shrink-0">
          {{ formatted }}
        </UBadge>
      </div>
    </template>

    <UAlert
      v-if="itemsWithNotes.length"
      color="warning"
      variant="subtle"
      icon="i-lucide-message-square-warning"
      title="Atenção a observações"
      class="mb-3"
      :ui="{ title: 'text-sm' }"
    >
      <template #description>
        <ul class="text-sm grid gap-1 mt-1">
          <li v-for="(item, idx) in itemsWithNotes" :key="idx">
            <span class="font-semibold">{{ item.qty }}× {{ item.name }}:</span>
            {{ item.notes }}
          </li>
        </ul>
      </template>
    </UAlert>

    <UAlert
      v-if="stockWarnings.length"
      color="error"
      variant="subtle"
      icon="i-lucide-package-x"
      title="Estoque crítico"
      class="mb-3"
      :ui="{ title: 'text-sm' }"
    >
      <template #description>
        <ul class="text-sm grid gap-1 mt-1">
          <li v-for="(item, idx) in stockWarnings" :key="idx">
            <span class="font-semibold">{{ item.name }}:</span>
            {{ item.stock_warning }}
          </li>
        </ul>
      </template>
    </UAlert>

    <ul class="grid gap-2">
      <li
        v-for="(item, idx) in ticket.items"
        :key="idx"
        class="flex items-start gap-3"
      >
        <UCheckbox
          :model-value="item.checked"
          size="lg"
          @update:model-value="() => onToggle(idx, item.checked)"
        />
        <div class="flex-1 min-w-0" :class="item.checked && 'opacity-50 line-through'">
          <p class="font-semibold text-highlighted">
            <span class="text-primary tabular-nums">{{ item.qty }}×</span>
            {{ item.name }}
          </p>
        </div>
      </li>
    </ul>

    <template #footer>
      <div class="flex items-center justify-between gap-3">
        <span class="text-sm text-muted tabular-nums">
          {{ checkedCount }} / {{ ticket.items.length }} pronto{{ ticket.items.length === 1 ? '' : 's' }}
        </span>
        <UButton
          :disabled="!ticket.all_checked"
          color="success"
          variant="solid"
          icon="i-lucide-circle-check"
          label="Pronto"
          size="md"
          @click="onDone"
        />
      </div>
    </template>
  </UCard>
</template>
