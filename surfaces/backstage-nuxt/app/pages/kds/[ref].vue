<script setup lang="ts">
import type { TableColumn } from '@nuxt/ui'
import type { KDSBoardResponse, KDSExpeditionCardProjection, KDSTicketProjection } from '~/types/backstage'

const route = useRoute()
const ref_ = computed(() => String(route.params.ref || ''))
const apiPath = useBackstageApiPath()
const action = useBackstageAction()

const view = useViewMode(`kds-board-${ref_.value}`, 'grid')
const { sortable } = useSortableHeader()
const sortingPrep = ref([{ id: 'elapsed_seconds', desc: true }])
const sortingExp = ref([{ id: 'customer_name', desc: false }])
const searchQuery = ref('')
const expandedPrep = ref<Record<string, boolean>>({})
const expandedExp = ref<Record<string, boolean>>({})

const { data, pending, error, refresh } = await useFetch<KDSBoardResponse>(
  () => apiPath(`/api/v1/backstage/kds/${encodeURIComponent(ref_.value)}/`),
  { credentials: 'include' }
)

const board = computed(() => data.value?.board)
const isExpedition = computed(() => !!board.value?.is_expedition)

const tickets = computed(() => {
  const all = (board.value?.tickets || []) as KDSTicketProjection[]
  if (!searchQuery.value.trim()) return all
  const q = searchQuery.value.toLowerCase().trim()
  return all.filter(t =>
    t.order_ref.toLowerCase().includes(q)
    || t.customer_name.toLowerCase().includes(q)
    || t.items.some(i => i.name.toLowerCase().includes(q))
  )
})

const expeditionCards = computed(() => {
  const all = (board.value?.tickets || []) as KDSExpeditionCardProjection[]
  if (!searchQuery.value.trim()) return all
  const q = searchQuery.value.toLowerCase().trim()
  return all.filter(c =>
    c.ref.toLowerCase().includes(q)
    || c.customer_name.toLowerCase().includes(q)
  )
})

const { isFullscreen, toggle: toggleFullscreen } = useFullscreen()

const soundEnabled = useState<boolean>('kds-sound', () => {
  if (import.meta.client) return localStorage.getItem('kds-sound') !== '0'
  return true
})
watch(soundEnabled, (v) => { if (import.meta.client) localStorage.setItem('kds-sound', v ? '1' : '0') })

const lastTicketIds = ref<Set<number>>(new Set())
let audioCtx: AudioContext | null = null

function beep () {
  if (!soundEnabled.value || typeof window === 'undefined') return
  try {
    if (!audioCtx) audioCtx = new (window.AudioContext || (window as any).webkitAudioContext)()
    const osc = audioCtx.createOscillator()
    const gain = audioCtx.createGain()
    osc.connect(gain)
    gain.connect(audioCtx.destination)
    osc.frequency.value = 880
    gain.gain.setValueAtTime(0.15, audioCtx.currentTime)
    gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.3)
    osc.start()
    osc.stop(audioCtx.currentTime + 0.3)
  } catch {}
}

watch(tickets, (next) => {
  if (!next?.length) return
  const ids = new Set(next.map(t => t.pk))
  if (lastTicketIds.value.size > 0) {
    for (const id of ids) {
      if (!lastTicketIds.value.has(id)) { beep(); break }
    }
  }
  lastTicketIds.value = ids
}, { deep: true })

async function toggleItem (p: { ticketPk: number, index: number, checked: boolean }) {
  const r = await action.call(`/api/v1/backstage/kds/tickets/${p.ticketPk}/items/`, {
    body: { index: p.index, checked: p.checked }
  })
  if (r !== null) refresh()
}

async function markDone (ticketPk: number) {
  const r = await action.call(`/api/v1/backstage/kds/tickets/${ticketPk}/done/`, {
    successTitle: 'Pedido pronto'
  })
  if (r !== null) refresh()
}

async function expeditionAction (p: { orderPk: number, action: 'dispatch' | 'complete' }) {
  const r = await action.call(`/api/v1/backstage/kds/expedition/${p.orderPk}/action/`, {
    body: { action: p.action },
    successTitle: p.action === 'dispatch' ? 'Despachado' : 'Concluído'
  })
  if (r !== null) refresh()
}

const fmtElapsed = (s: number) => {
  const mins = Math.floor(s / 60)
  const secs = s % 60
  return mins >= 60 ? `${Math.floor(mins / 60)}h${String(mins % 60).padStart(2, '0')}` : `${mins}:${String(secs).padStart(2, '0')}`
}

const timerColor = (cls: string) => cls === 'timer-late' ? 'error' : cls === 'timer-warning' ? 'warning' : 'success'

const prepColumns: TableColumn<KDSTicketProjection>[] = [
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
    accessorKey: 'order_ref',
    header: sortable('Pedido'),
    cell: ({ row }) => h('span', { class: 'text-sm text-muted tabular-nums' }, row.original.order_ref)
  },
  {
    accessorKey: 'customer_name',
    header: sortable('Cliente'),
    cell: ({ row }) => h('span', { class: 'font-semibold text-highlighted' }, row.original.customer_name)
  },
  {
    accessorFn: (row) => row.items.map(i => `${i.qty}× ${i.name}`).join(', '),
    id: 'items',
    header: 'Itens',
    cell: ({ row }) => h('div', { class: 'min-w-0' }, [
      h('p', { class: 'text-sm text-muted line-clamp-2' },
        row.original.items.map(i => `${i.qty}× ${i.name}`).join(', '))
    ])
  },
  {
    accessorKey: 'elapsed_seconds',
    header: sortable('Tempo'),
    meta: { class: { td: 'text-right' } },
    cell: ({ row }) => h(resolveComponent('UBadge'), {
      color: timerColor(row.original.timer_class),
      variant: 'subtle',
      size: 'md',
      class: 'tabular-nums'
    }, () => fmtElapsed(row.original.elapsed_seconds))
  },
  {
    id: 'actions',
    header: '',
    meta: { class: { td: 'w-32 text-right' } },
    cell: ({ row }) => h(resolveComponent('UButton'), {
      color: 'success',
      variant: row.original.all_checked ? 'solid' : 'soft',
      size: 'sm',
      icon: 'i-lucide-check',
      label: 'Pronto',
      onClick: (e: Event) => { e.stopPropagation(); markDone(row.original.pk) }
    })
  }
]

const expColumns: TableColumn<KDSExpeditionCardProjection>[] = [
  {
    id: 'expand',
    header: '',
    meta: { class: { td: 'w-10' } },
    cell: ({ row }) => h(resolveComponent('UButton'), {
      color: 'neutral',
      variant: 'ghost',
      size: 'sm',
      icon: row.getIsExpanded() ? 'i-lucide-chevron-down' : 'i-lucide-chevron-right',
      'aria-label': row.getIsExpanded() ? 'Recolher detalhe' : 'Expandir detalhe',
      onClick: (e: Event) => { e.stopPropagation(); row.toggleExpanded() }
    })
  },
  {
    accessorKey: 'ref',
    header: sortable('Pedido'),
    cell: ({ row }) => h('span', { class: 'text-sm text-muted tabular-nums' }, row.original.ref)
  },
  {
    accessorKey: 'customer_name',
    header: sortable('Cliente'),
    cell: ({ row }) => h('span', { class: 'font-semibold text-highlighted' }, row.original.customer_name)
  },
  {
    accessorKey: 'fulfillment_label',
    header: sortable('Tipo'),
    cell: ({ row }) => h(resolveComponent('UBadge'), {
      color: row.original.is_delivery ? 'warning' : 'neutral',
      variant: 'subtle',
      size: 'md'
    }, () => row.original.fulfillment_label)
  },
  {
    accessorKey: 'units_count',
    header: sortable('Itens'),
    meta: { class: { td: 'tabular-nums' } },
    cell: ({ row }) => h('span', { class: 'tabular-nums text-sm text-muted' },
      `${row.original.units_count} (${row.original.line_count} linhas)`)
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
    meta: { class: { td: 'w-44 text-right' } },
    cell: ({ row }) => h('div', { class: 'flex items-center gap-1 justify-end' }, [
      row.original.is_delivery
        ? h(resolveComponent('UButton'), {
            color: 'primary', size: 'sm', icon: 'i-lucide-truck', label: 'Despachar',
            onClick: (e: Event) => { e.stopPropagation(); expeditionAction({ orderPk: row.original.pk, action: 'dispatch' }) }
          })
        : h(resolveComponent('UButton'), {
            color: 'success', size: 'sm', icon: 'i-lucide-check', label: 'Concluir',
            onClick: (e: Event) => { e.stopPropagation(); expeditionAction({ orderPk: row.original.pk, action: 'complete' }) }
          })
    ])
  }
]

if (import.meta.client) {
  let pollTimer: ReturnType<typeof setInterval> | null = null
  let eventSource: EventSource | null = null

  function startPolling () {
    stopPolling()
    pollTimer = setInterval(() => { refresh() }, 15_000)
  }
  function stopPolling () {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
  }
  function startSse () {
    stopSse()
    try {
      const url = apiPath('/gestor/events/kds/')
      eventSource = new EventSource(url, { withCredentials: true })
      eventSource.addEventListener('message', () => { refresh() })
      eventSource.addEventListener('backstage-kds-main', () => { refresh() })
      eventSource.addEventListener('error', () => {})
    } catch {}
  }
  function stopSse () {
    if (eventSource) { eventSource.close(); eventSource = null }
  }

  onMounted(() => { startPolling(); startSse() })
  onBeforeUnmount(() => { stopPolling(); stopSse() })
}

useHead(() => ({ title: board.value ? `KDS · ${board.value.instance_name}` : 'KDS' }))
</script>

<template>
  <UDashboardPanel id="kds-station">
    <template #header>
      <UDashboardNavbar
        v-if="board"
        :title="board.instance_name"
        icon="i-lucide-chef-hat"
      >
        <template #leading>
          <UDashboardSidebarCollapse />
        </template>

        <template #right>
          <UBadge color="neutral" variant="subtle" class="tabular-nums hidden sm:flex">
            Pendentes · {{ board.counts.pending }}
          </UBadge>
          <UBadge color="warning" variant="subtle" class="tabular-nums hidden sm:flex">
            Em prep · {{ board.counts.in_progress }}
          </UBadge>
          <UBadge color="success" variant="subtle" class="gap-1.5">
            <span class="size-1.5 rounded-full bg-success animate-pulse" />
            Ao vivo
          </UBadge>
          <UTooltip text="Atualizar agora">
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
          <UTooltip :text="soundEnabled ? 'Desligar som' : 'Ligar som'">
            <UButton
              :icon="soundEnabled ? 'i-lucide-volume-2' : 'i-lucide-volume-x'"
              color="neutral"
              variant="ghost"
              size="sm"
              :aria-label="soundEnabled ? 'Desligar som' : 'Ligar som'"
              @click="soundEnabled = !soundEnabled"
            />
          </UTooltip>
          <UTooltip :text="isFullscreen ? 'Sair de tela cheia' : 'Tela cheia'">
            <UButton
              :icon="isFullscreen ? 'i-lucide-minimize' : 'i-lucide-maximize'"
              color="neutral"
              variant="ghost"
              size="sm"
              :aria-label="isFullscreen ? 'Sair de tela cheia' : 'Tela cheia'"
              @click="toggleFullscreen"
            />
          </UTooltip>
        </template>
      </UDashboardNavbar>

      <UDashboardToolbar v-if="board">
        <template #right>
          <UInput
            v-model="searchQuery"
            icon="i-lucide-search"
            placeholder="Buscar pedido, cliente ou item"
            size="sm"
            class="w-72 max-w-full"
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
        title="Não foi possível carregar a estação"
        description="Verifique o ref da estação e se você está autenticado como operador."
      />

      <div v-else-if="board">
        <UEmpty
          v-if="!board.tickets.length"
          icon="i-lucide-coffee"
          title="Tudo em dia"
          description="Nenhum pedido na fila no momento. Aguarde a próxima entrada."
        />

        <UEmpty
          v-else-if="(isExpedition ? expeditionCards.length : tickets.length) === 0"
          icon="i-lucide-search-x"
          title="Nenhum item com esse filtro"
        />

        <!-- GRID -->
        <div v-else-if="view.mode.value === 'grid'" class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          <template v-if="isExpedition">
            <KDSExpeditionCard
              v-for="card in expeditionCards"
              :key="card.pk"
              :card="card"
              @action="expeditionAction"
            />
          </template>
          <template v-else>
            <KDSTicketCard
              v-for="ticket in tickets"
              :key="ticket.pk"
              :ticket="ticket"
              @item-toggle="toggleItem"
              @done="markDone"
            />
          </template>
        </div>

        <!-- LIST -->
        <UCard v-else :ui="{ body: 'p-0' }">
          <UTable
            v-if="isExpedition"
            v-bind="{ onSelect: (_e: Event, row: any) => row.toggleExpanded() }"
            v-model:sorting="sortingExp"
            v-model:expanded="expandedExp"
            :data="expeditionCards"
            :columns="expColumns"
            sticky
            class="cursor-pointer"
            :ui="{ tr: 'hover:bg-elevated/50 transition-colors' }"
          >
            <template #expanded="{ row }">
              <div class="grid sm:grid-cols-2 gap-3 p-3 bg-elevated/30">
                <div>
                  <p class="text-xs uppercase tracking-wide text-muted mb-1">Cliente</p>
                  <p class="font-semibold text-highlighted">{{ row.original.customer_name }}</p>
                </div>
                <div>
                  <p class="text-xs uppercase tracking-wide text-muted mb-1">Conteúdo</p>
                  <p class="text-sm">
                    {{ row.original.units_count }} itens em {{ row.original.line_count }} linhas · <strong>{{ row.original.total_display }}</strong>
                  </p>
                </div>
              </div>
            </template>
          </UTable>
          <UTable
            v-else
            v-bind="{ onSelect: (_e: Event, row: any) => row.toggleExpanded() }"
            v-model:sorting="sortingPrep"
            v-model:expanded="expandedPrep"
            :data="tickets"
            :columns="prepColumns"
            sticky
            class="cursor-pointer"
            :ui="{ tr: 'hover:bg-elevated/50 transition-colors' }"
          >
            <template #expanded="{ row }">
              <div class="p-3 bg-elevated/30 grid gap-2">
                <ul class="grid gap-1.5">
                  <li
                    v-for="(item, idx) in row.original.items"
                    :key="`${row.original.pk}-${idx}`"
                    class="flex items-start gap-3"
                  >
                    <UCheckbox
                      :model-value="item.checked"
                      @update:model-value="(v: boolean) => toggleItem({ ticketPk: row.original.pk, index: idx, checked: v })"
                    />
                    <div class="min-w-0 flex-1">
                      <p
                        class="text-sm font-semibold leading-tight"
                        :class="item.checked ? 'text-muted line-through' : 'text-highlighted'"
                      >
                        {{ item.qty }}× {{ item.name }}
                      </p>
                      <p v-if="item.notes" class="text-sm text-muted">{{ item.notes }}</p>
                      <p v-if="item.stock_warning" class="text-sm text-warning">⚠ {{ item.stock_warning }}</p>
                    </div>
                  </li>
                </ul>
              </div>
            </template>
          </UTable>
        </UCard>
      </div>
    </template>
  </UDashboardPanel>
</template>
