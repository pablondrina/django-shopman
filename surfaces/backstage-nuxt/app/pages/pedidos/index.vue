<script setup lang="ts">
import type { TableColumn } from '@nuxt/ui'
import type { OrderCardProjection, OrderQueueResponse } from '~/types/backstage'

const apiPath = useBackstageApiPath()
const action = useBackstageAction()
const view = useViewMode('pedidos', 'grid')
const { sortable } = useSortableHeader()
const sorting = ref([{ id: 'elapsed_seconds', desc: true }])
const expanded = ref<Record<string, boolean>>({})

const { data, pending, error, refresh } = await useFetch<OrderQueueResponse>(
  () => apiPath('/api/v1/backstage/orders/'),
  { credentials: 'include' }
)

const queue = computed(() => data.value?.queue)
const actingRef = ref<string | null>(null)
const searchQuery = ref('')

const channelFilter = ref<'all' | 'web' | 'whatsapp' | 'ifood' | 'pdv'>('all')
const channelOptions = [
  { label: 'Todos', value: 'all', icon: 'i-lucide-layers' },
  { label: 'Web', value: 'web', icon: 'i-lucide-globe' },
  { label: 'WhatsApp', value: 'whatsapp', icon: 'i-lucide-message-circle' },
  { label: 'iFood', value: 'ifood', icon: 'i-lucide-utensils' },
  { label: 'PDV', value: 'pdv', icon: 'i-lucide-shopping-bag' }
] as const

function applyFilters (orders: OrderCardProjection[] | undefined) {
  if (!orders) return []
  let filtered = orders
  if (channelFilter.value !== 'all') {
    filtered = filtered.filter(o => (o.channel_icon || '').toLowerCase().includes(channelFilter.value))
  }
  if (searchQuery.value.trim()) {
    const q = searchQuery.value.toLowerCase().trim()
    filtered = filtered.filter(o =>
      o.ref.toLowerCase().includes(q) ||
      o.customer_name.toLowerCase().includes(q)
    )
  }
  return filtered
}

const entrada = computed(() => applyFilters(queue.value?.entrada))
const preparo = computed(() => applyFilters(queue.value?.preparo))
const saida = computed(() => applyFilters([
  ...(queue.value?.saida_retirada || []),
  ...(queue.value?.saida_delivery || []),
  ...(queue.value?.saida_delivery_transit || [])
]))

const allFiltered = computed(() => [...entrada.value, ...preparo.value, ...saida.value])

const cancelOpen = ref(false)
const cancelTarget = ref<OrderCardProjection | null>(null)

const detailOpen = ref(false)
const detailRef = ref<string | null>(null)
function openDetail (order: OrderCardProjection) {
  detailRef.value = order.ref
  detailOpen.value = true
}

function onRowSelect (_e: Event, row: { original: OrderCardProjection }) {
  openDetail(row.original)
}

async function advance (order: OrderCardProjection) {
  actingRef.value = order.ref
  const res = await action.call(`/api/v1/backstage/orders/${encodeURIComponent(order.ref)}/advance/`, {
    successTitle: `${order.customer_name} avançado`
  })
  if (res !== null) await refresh()
  actingRef.value = null
}

function openCancel (order: OrderCardProjection) {
  cancelTarget.value = order
  cancelOpen.value = true
}

async function onCancelConfirm (payload: { order: OrderCardProjection, reason: string }) {
  actingRef.value = payload.order.ref
  const res = await action.call(`/api/v1/backstage/orders/${encodeURIComponent(payload.order.ref)}/cancel/`, {
    body: { reason: payload.reason },
    successTitle: 'Pedido cancelado'
  })
  if (res !== null) await refresh()
  cancelOpen.value = false
  actingRef.value = null
}

const statusColor = (status: string) => {
  if (['cancelled', 'refused'].includes(status)) return 'error' as const
  if (['ready', 'completed', 'delivered'].includes(status)) return 'success' as const
  if (status === 'preparing') return 'warning' as const
  return 'neutral' as const
}

const channelLucide: Record<string, string> = {
  language: 'i-lucide-globe',
  chat: 'i-lucide-message-circle',
  fastfood: 'i-lucide-utensils',
  storefront: 'i-lucide-store',
  shopping_bag: 'i-lucide-shopping-bag'
}
const fulfillmentLucide: Record<string, string> = {
  local_shipping: 'i-lucide-truck',
  storefront: 'i-lucide-store'
}

const columns: TableColumn<OrderCardProjection>[] = [
  {
    id: 'expand',
    header: '',
    meta: { class: { td: 'w-10' } },
    cell: ({ row }) => h(resolveComponent('UButton'), {
      color: 'neutral',
      variant: 'ghost',
      size: 'sm',
      icon: row.getIsExpanded() ? 'i-lucide-chevron-down' : 'i-lucide-chevron-right',
      'aria-label': row.getIsExpanded() ? 'Recolher itens' : 'Expandir itens',
      onClick: (e: Event) => { e.stopPropagation(); row.toggleExpanded() }
    })
  },
  {
    accessorKey: 'channel_icon',
    header: '',
    meta: { class: { td: 'w-12' } },
    cell: ({ row }) => h('div', { class: 'flex items-center gap-1 text-muted' }, [
      h(resolveComponent('UIcon'), { name: channelLucide[row.original.channel_icon] || 'i-lucide-circle', class: 'size-4' }),
      h(resolveComponent('UIcon'), { name: fulfillmentLucide[row.original.fulfillment_icon] || 'i-lucide-circle', class: 'size-4' })
    ])
  },
  {
    accessorKey: 'customer_name',
    header: sortable('Cliente'),
    cell: ({ row }) => h('span', { class: 'font-semibold text-highlighted' }, row.original.customer_name)
  },
  {
    accessorKey: 'status_label',
    header: sortable('Status'),
    cell: ({ row }) => h(resolveComponent('UBadge'), {
      color: statusColor(row.original.status),
      variant: 'subtle',
      size: 'md'
    }, () => row.original.status_label)
  },
  {
    accessorKey: 'fulfillment_label',
    header: sortable('Tipo'),
    cell: ({ row }) => h('span', { class: 'text-sm text-muted' }, row.original.fulfillment_label)
  },
  {
    accessorKey: 'elapsed_seconds',
    header: sortable('Tempo'),
    meta: { class: { td: 'text-right tabular-nums' } },
    cell: ({ row }) => {
      const s = row.original.elapsed_seconds
      const mins = Math.floor(s / 60)
      const secs = s % 60
      const label = mins >= 60 ? `${Math.floor(mins / 60)}h${String(mins % 60).padStart(2, '0')}` : `${mins}:${String(secs).padStart(2, '0')}`
      const color = row.original.timer_class === 'timer-urgent' ? 'error' : row.original.timer_class === 'timer-warning' ? 'warning' : 'neutral'
      return h(resolveComponent('UBadge'), { color, variant: 'subtle', size: 'md', class: 'tabular-nums' }, () => label)
    }
  },
  {
    accessorFn: (row) => {
      const raw = (row.total_display || '').replace(/[^\d,.-]/g, '').replace(/\./g, '').replace(',', '.')
      return Number.parseFloat(raw) || 0
    },
    id: 'total',
    header: sortable('Total'),
    meta: { class: { td: 'text-right' } },
    cell: ({ row }) => h('strong', { class: 'tabular-nums text-highlighted' }, row.original.total_display)
  },
  {
    id: 'actions',
    header: '',
    meta: { class: { td: 'text-right' } },
    cell: ({ row }) => h('div', { class: 'flex items-center gap-1 justify-end' }, [
      row.original.can_advance && row.original.next_action_label
        ? h(resolveComponent('UButton'), {
            color: 'primary',
            size: 'sm',
            label: row.original.next_action_label,
            icon: 'i-lucide-arrow-right',
            trailing: true,
            disabled: row.original.payment_pending,
            onClick: (e: Event) => { e.stopPropagation(); advance(row.original) }
          })
        : row.original.can_confirm
          ? h(resolveComponent('UButton'), {
              color: 'primary', size: 'sm', label: 'Confirmar', icon: 'i-lucide-check',
              onClick: (e: Event) => { e.stopPropagation(); advance(row.original) }
            })
          : null,
      h(resolveComponent('UButton'), {
        color: 'neutral', variant: 'ghost', size: 'sm', icon: 'i-lucide-x',
        'aria-label': 'Cancelar',
        onClick: (e: Event) => { e.stopPropagation(); openCancel(row.original) }
      })
    ])
  }
]

if (import.meta.client) {
  let pollTimer: ReturnType<typeof setInterval> | null = null
  onMounted(() => { pollTimer = setInterval(() => refresh(), 15_000) })
  onBeforeUnmount(() => { if (pollTimer) clearInterval(pollTimer) })
}

useHead({ title: 'Pedidos' })
</script>

<template>
  <UDashboardPanel id="pedidos">
    <template #header>
      <UDashboardNavbar title="Pedidos" icon="i-lucide-clipboard-list">
        <template #leading>
          <UDashboardSidebarCollapse />
        </template>

        <template #right>
          <UBadge color="neutral" variant="subtle" class="tabular-nums">
            {{ queue?.total_count ?? 0 }} ativos
          </UBadge>
          <UBadge color="success" variant="subtle" class="gap-1.5">
            <span class="size-1.5 rounded-full bg-success animate-pulse" />
            Ao vivo
          </UBadge>
          <UTooltip text="Atualizar">
            <UButton
              icon="i-lucide-refresh-cw"
              color="neutral"
              variant="ghost"
              size="sm"
              aria-label="Atualizar"
              :loading="pending"
              @click="refresh()"
            />
          </UTooltip>
        </template>
      </UDashboardNavbar>

      <UDashboardToolbar>
        <template #left>
          <UButton
            v-for="opt in channelOptions"
            :key="opt.value"
            size="sm"
            :color="channelFilter === opt.value ? 'primary' : 'neutral'"
            :variant="channelFilter === opt.value ? 'solid' : 'ghost'"
            :icon="opt.icon"
            :label="opt.label"
            @click="channelFilter = opt.value"
          />
        </template>
        <template #right>
          <UInput
            v-model="searchQuery"
            icon="i-lucide-search"
            placeholder="Buscar por cliente ou pedido"
            size="sm"
            class="w-64 max-w-full"
          />
          <ViewModeToggle v-model="view.mode.value" />
        </template>
      </UDashboardToolbar>
    </template>

    <template #body>
      <USkeleton v-if="pending" class="h-40 w-full" />

      <UAlert
        v-else-if="error"
        color="error"
        variant="soft"
        title="Não foi possível carregar pedidos"
      />

      <div v-else-if="queue">
        <!-- GRID (kanban) -->
        <div v-if="view.mode.value === 'grid'" class="grid lg:grid-cols-3 gap-4 items-start">
          <section>
            <h2 class="text-sm font-semibold text-highlighted uppercase tracking-wide mb-3 flex items-center gap-2">
              <UIcon name="i-lucide-inbox" class="size-4 text-primary" />
              Entrada
              <UBadge color="primary" variant="subtle" size="md">{{ entrada.length }}</UBadge>
            </h2>
            <UEmpty v-if="!entrada.length" icon="i-lucide-coffee" title="Sem novos" />
            <div v-else class="grid gap-3">
              <OrderCard
                v-for="order in entrada"
                :key="order.ref"
                :order="order"
                :acting="actingRef === order.ref"
                :status-color="statusColor"
                @advance="advance"
                @cancel="openCancel"
                @detail="openDetail"
              />
            </div>
          </section>

          <section>
            <h2 class="text-sm font-semibold text-highlighted uppercase tracking-wide mb-3 flex items-center gap-2">
              <UIcon name="i-lucide-flame" class="size-4 text-warning" />
              Preparo
              <UBadge color="warning" variant="subtle" size="md">{{ preparo.length }}</UBadge>
            </h2>
            <UEmpty v-if="!preparo.length" icon="i-lucide-coffee" title="Sem prep ativo" />
            <div v-else class="grid gap-3">
              <OrderCard
                v-for="order in preparo"
                :key="order.ref"
                :order="order"
                :acting="actingRef === order.ref"
                :status-color="statusColor"
                @advance="advance"
                @cancel="openCancel"
                @detail="openDetail"
              />
            </div>
          </section>

          <section>
            <h2 class="text-sm font-semibold text-highlighted uppercase tracking-wide mb-3 flex items-center gap-2">
              <UIcon name="i-lucide-package-check" class="size-4 text-success" />
              Saída
              <UBadge color="success" variant="subtle" size="md">{{ saida.length }}</UBadge>
            </h2>
            <UEmpty v-if="!saida.length" icon="i-lucide-coffee" title="Sem saída" />
            <div v-else class="grid gap-3">
              <OrderCard
                v-for="order in saida"
                :key="order.ref"
                :order="order"
                :acting="actingRef === order.ref"
                :status-color="statusColor"
                @advance="advance"
                @cancel="openCancel"
                @detail="openDetail"
              />
            </div>
          </section>
        </div>

        <!-- LIST -->
        <UCard v-else :ui="{ body: 'p-0' }">
          <UTable
            v-bind="{ onSelect: onRowSelect }"
            v-model:sorting="sorting"
            v-model:expanded="expanded"
            :data="allFiltered"
            :columns="columns"
            :empty="searchQuery || channelFilter !== 'all' ? 'Nenhum pedido com esse filtro.' : 'Sem pedidos ativos.'"
            sticky
            class="cursor-pointer"
            :ui="{ tr: 'hover:bg-elevated/50 transition-colors' }"
          >
            <template #expanded="{ row }">
              <div class="grid sm:grid-cols-[1fr_auto] gap-4 p-3 bg-elevated/30">
                <div>
                  <p class="text-xs uppercase tracking-wide text-muted mb-1">Itens</p>
                  <p class="text-sm">{{ row.original.items_summary }}</p>
                  <p v-if="row.original.has_notes" class="text-sm text-info mt-1.5 flex items-center gap-1">
                    <UIcon name="i-lucide-message-square" class="size-3.5" /> Tem notas internas
                  </p>
                </div>
                <div class="flex flex-wrap items-center gap-2 sm:justify-end">
                  <UBadge v-if="row.original.payment_pending" color="warning" variant="subtle" size="md">
                    Pagamento pendente
                  </UBadge>
                  <UBadge v-else-if="row.original.payment_method_label" color="neutral" variant="subtle" size="md">
                    {{ row.original.payment_method_label }}
                  </UBadge>
                  <UButton
                    :to="`/pedidos/${row.original.ref}`"
                    color="neutral"
                    variant="outline"
                    size="sm"
                    icon="i-lucide-external-link"
                    label="Tela cheia"
                    @click.stop
                  />
                </div>
              </div>
            </template>
          </UTable>
        </UCard>
      </div>

      <OrderCancelModal
        v-model:open="cancelOpen"
        :order="cancelTarget"
        @confirm="onCancelConfirm"
      />

      <OrderDetailSlideover
        v-model:open="detailOpen"
        :order-ref="detailRef"
      />
    </template>
  </UDashboardPanel>
</template>
