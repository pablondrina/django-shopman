<script setup lang="ts">
import type { TableColumn } from '@nuxt/ui'
import type { ProductionBoardResponse, WorkOrderCardProjection } from '~/types/backstage'

const apiPath = useBackstageApiPath()
const router = useRouter()
const view = useViewMode('producao', 'grid')
const { sortable } = useSortableHeader()
const sorting = ref([{ id: 'recipe_name', desc: false }])
const expanded = ref<Record<string, boolean>>({})
const searchQuery = ref('')
const statusFilter = ref<'all' | 'planned' | 'started' | 'finished'>('all')

const { data, pending, error, refresh } = await useFetch<ProductionBoardResponse>(
  () => apiPath('/api/v1/backstage/production/'),
  { credentials: 'include' }
)

const board = computed(() => data.value?.board)

function applyFilters (cards: WorkOrderCardProjection[] | undefined) {
  if (!cards) return []
  let filtered = cards
  if (statusFilter.value !== 'all') {
    filtered = filtered.filter(c => c.status === statusFilter.value)
  }
  if (searchQuery.value.trim()) {
    const q = searchQuery.value.toLowerCase().trim()
    filtered = filtered.filter(c =>
      c.recipe_name.toLowerCase().includes(q)
      || c.output_sku.toLowerCase().includes(q)
      || c.ref.toLowerCase().includes(q)
    )
  }
  return filtered
}

const filteredCards = computed(() => applyFilters(board.value?.cards))

const groupedCards = computed(() => ({
  planned: filteredCards.value.filter(c => c.status === 'planned'),
  started: filteredCards.value.filter(c => c.status === 'started'),
  finished: filteredCards.value.filter(c => c.status === 'finished')
}))

const statusOptions = [
  { label: 'Todos', value: 'all', icon: 'i-lucide-layers' },
  { label: 'Planejados', value: 'planned', icon: 'i-lucide-calendar' },
  { label: 'Em andamento', value: 'started', icon: 'i-lucide-flame' },
  { label: 'Concluídos', value: 'finished', icon: 'i-lucide-check' }
] as const

const statusColor = (status: string) => {
  if (status === 'started') return 'warning' as const
  if (status === 'finished') return 'success' as const
  return 'neutral' as const
}

const columns: TableColumn<WorkOrderCardProjection>[] = [
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
    header: sortable('Ref'),
    cell: ({ row }) => h('span', { class: 'text-sm text-muted tabular-nums' }, row.original.ref)
  },
  {
    accessorKey: 'recipe_name',
    header: sortable('Receita'),
    cell: ({ row }) => h('div', { class: 'min-w-0' }, [
      h('p', { class: 'font-semibold text-highlighted truncate' }, row.original.recipe_name),
      h('p', { class: 'text-sm text-muted truncate' }, row.original.output_sku)
    ])
  },
  {
    accessorKey: 'status_display',
    header: sortable('Status'),
    cell: ({ row }) => h(resolveComponent('UBadge'), {
      color: row.original.is_late ? 'warning' : statusColor(row.original.status),
      variant: 'subtle',
      size: 'md'
    }, () => row.original.status_display)
  },
  {
    accessorKey: 'quantity_display',
    header: sortable('Quantidade'),
    meta: { class: { td: 'tabular-nums' } },
    cell: ({ row }) => h('span', { class: 'tabular-nums font-semibold' }, row.original.quantity_display)
  },
  {
    accessorKey: 'position_display',
    header: sortable('Posição'),
    cell: ({ row }) => h('span', { class: 'text-sm text-muted' }, row.original.position_display || '—')
  }
]

if (import.meta.client) {
  let pollTimer: ReturnType<typeof setInterval> | null = null
  onMounted(() => { pollTimer = setInterval(() => refresh(), 30_000) })
  onBeforeUnmount(() => { if (pollTimer) clearInterval(pollTimer) })
}

useHead({ title: 'Produção' })
</script>

<template>
  <UDashboardPanel id="producao">
    <template #header>
      <UDashboardNavbar title="Produção" icon="i-lucide-flame">
        <template #leading>
          <UDashboardSidebarCollapse />
        </template>
        <template #right>
          <UBadge color="neutral" variant="subtle">
            {{ board?.selected_date_display }}
          </UBadge>
          <UBadge color="neutral" variant="subtle" class="tabular-nums hidden sm:flex">
            {{ board?.counts.total ?? 0 }} total
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
          <UButton to="/producao/kds" icon="i-lucide-flame" color="primary" size="sm" label="KDS produção" />
        </template>
      </UDashboardNavbar>

      <UDashboardToolbar>
        <template #left>
          <UButton
            v-for="opt in statusOptions"
            :key="opt.value"
            size="sm"
            :color="statusFilter === opt.value ? 'primary' : 'neutral'"
            :variant="statusFilter === opt.value ? 'solid' : 'ghost'"
            :icon="opt.icon"
            :label="opt.label"
            @click="statusFilter = opt.value"
          />
        </template>
        <template #right>
          <UInput
            v-model="searchQuery"
            icon="i-lucide-search"
            placeholder="Buscar receita, SKU ou ref"
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
        title="Não foi possível carregar a produção"
      />

      <div v-else-if="board">
        <UEmpty
          v-if="!filteredCards.length"
          icon="i-lucide-flame-off"
          :title="searchQuery || statusFilter !== 'all' ? 'Nenhuma work order com esse filtro' : 'Sem produção hoje'"
          description="Nenhuma work order para esta data."
        />

        <!-- GRID (kanban) -->
        <div v-else-if="view.mode.value === 'grid'" class="grid lg:grid-cols-3 gap-4 items-start">
          <section>
            <h2 class="text-sm font-semibold text-highlighted uppercase tracking-wide mb-3 flex items-center gap-2">
              <UIcon name="i-lucide-calendar" class="size-4 text-muted" />
              Planejados
              <UBadge color="neutral" variant="subtle" size="md">{{ groupedCards.planned.length }}</UBadge>
            </h2>
            <UEmpty v-if="!groupedCards.planned.length" icon="i-lucide-circle-dashed" title="Vazio" />
            <div v-else class="grid gap-3">
              <UCard v-for="card in groupedCards.planned" :key="card.pk">
                <p class="font-semibold text-highlighted">{{ card.recipe_name }}</p>
                <p class="text-sm text-muted mt-1">{{ card.output_sku }}</p>
                <div class="flex items-baseline justify-between mt-3">
                  <span class="text-sm text-muted">{{ card.position_display || '—' }}</span>
                  <strong class="text-base tabular-nums">{{ card.quantity_display }}</strong>
                </div>
              </UCard>
            </div>
          </section>

          <section>
            <h2 class="text-sm font-semibold text-highlighted uppercase tracking-wide mb-3 flex items-center gap-2">
              <UIcon name="i-lucide-flame" class="size-4 text-warning" />
              Em andamento
              <UBadge color="warning" variant="subtle" size="md">{{ groupedCards.started.length }}</UBadge>
            </h2>
            <UEmpty v-if="!groupedCards.started.length" icon="i-lucide-circle-dashed" title="Vazio" />
            <div v-else class="grid gap-3">
              <UCard v-for="card in groupedCards.started" :key="card.pk" :class="card.is_late && 'ring-1 ring-warning'">
                <p class="font-semibold text-highlighted">{{ card.recipe_name }}</p>
                <p class="text-sm text-muted mt-1">{{ card.output_sku }}</p>
                <div class="flex items-baseline justify-between mt-3">
                  <span class="text-sm text-muted">{{ card.position_display || '—' }}</span>
                  <strong class="text-base tabular-nums">{{ card.quantity_display }}</strong>
                </div>
              </UCard>
            </div>
          </section>

          <section>
            <h2 class="text-sm font-semibold text-highlighted uppercase tracking-wide mb-3 flex items-center gap-2">
              <UIcon name="i-lucide-check" class="size-4 text-success" />
              Concluídos
              <UBadge color="success" variant="subtle" size="md">{{ groupedCards.finished.length }}</UBadge>
            </h2>
            <UEmpty v-if="!groupedCards.finished.length" icon="i-lucide-circle-dashed" title="Vazio" />
            <div v-else class="grid gap-3">
              <UCard v-for="card in groupedCards.finished" :key="card.pk">
                <p class="font-semibold text-highlighted">{{ card.recipe_name }}</p>
                <p class="text-sm text-muted mt-1">{{ card.output_sku }}</p>
                <div class="flex items-baseline justify-between mt-3">
                  <span class="text-sm text-muted">{{ card.yield_pct_display || '—' }}</span>
                  <strong class="text-base tabular-nums">{{ card.quantity_display }}</strong>
                </div>
              </UCard>
            </div>
          </section>
        </div>

        <!-- LIST -->
        <UCard v-else :ui="{ body: 'p-0' }">
          <UTable
            v-bind="{ onSelect: () => router.push('/producao/kds') }"
            v-model:sorting="sorting"
            v-model:expanded="expanded"
            :data="filteredCards"
            :columns="columns"
            sticky
            class="cursor-pointer"
            :ui="{ tr: 'hover:bg-elevated/50 transition-colors' }"
          >
            <template #expanded="{ row }">
              <div class="grid sm:grid-cols-3 gap-4 p-3 bg-elevated/30 text-sm">
                <div>
                  <p class="text-xs uppercase tracking-wide text-muted mb-1">Iniciada</p>
                  <p class="tabular-nums">{{ row.original.started_at_display || '—' }}</p>
                </div>
                <div>
                  <p class="text-xs uppercase tracking-wide text-muted mb-1">Concluída</p>
                  <p class="tabular-nums">{{ row.original.finished_at_display || '—' }}</p>
                </div>
                <div>
                  <p class="text-xs uppercase tracking-wide text-muted mb-1">Rendimento</p>
                  <p class="tabular-nums">
                    {{ row.original.yield_pct_display || '—' }}
                    <span v-if="row.original.loss_qty_display" class="text-muted">· perda {{ row.original.loss_qty_display }}</span>
                  </p>
                </div>
              </div>
            </template>
          </UTable>
        </UCard>
      </div>
    </template>
  </UDashboardPanel>
</template>
