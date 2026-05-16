<script setup lang="ts">
import type { TableColumn } from '@nuxt/ui'
import type { KDSIndexResponse, KDSInstanceSummaryProjection } from '~/types/backstage'

const apiPath = useBackstageApiPath()
const router = useRouter()
const view = useViewMode('kds-index', 'grid')
const { sortable } = useSortableHeader()
const sorting = ref([{ id: 'pending_count', desc: true }])
const expanded = ref<Record<string, boolean>>({})
const searchQuery = ref('')
const typeFilter = ref<'all' | 'prep' | 'expedition' | 'picking'>('all')

const { data, pending, error } = await useFetch<KDSIndexResponse>(
  apiPath('/api/v1/backstage/kds/'),
  { credentials: 'include' }
)

const instances = computed(() => data.value?.instances || [])

const typeOptions = [
  { label: 'Todas', value: 'all', icon: 'i-lucide-layers' },
  { label: 'Preparo', value: 'prep', icon: 'i-lucide-chef-hat' },
  { label: 'Expedição', value: 'expedition', icon: 'i-lucide-package' },
  { label: 'Picking', value: 'picking', icon: 'i-lucide-package-search' }
] as const

const typeIcons: Record<string, string> = {
  prep: 'i-lucide-chef-hat',
  expedition: 'i-lucide-package',
  picking: 'i-lucide-package-search'
}

const filteredInstances = computed(() => {
  let filtered = instances.value
  if (typeFilter.value !== 'all') {
    filtered = filtered.filter(i => i.type === typeFilter.value)
  }
  if (searchQuery.value.trim()) {
    const q = searchQuery.value.toLowerCase().trim()
    filtered = filtered.filter(i => i.name.toLowerCase().includes(q))
  }
  return filtered
})

const totalPending = computed(() => instances.value.reduce((sum, i) => sum + i.pending_count, 0))

const columns: TableColumn<KDSInstanceSummaryProjection>[] = [
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
    accessorKey: 'name',
    header: sortable('Estação'),
    cell: ({ row }) => h('div', { class: 'flex items-center gap-2 min-w-0' }, [
      h(resolveComponent('UIcon'), {
        name: typeIcons[row.original.type] || 'i-lucide-monitor',
        class: 'size-4 text-muted shrink-0'
      }),
      h('span', { class: 'font-semibold text-highlighted truncate' }, row.original.name)
    ])
  },
  {
    accessorKey: 'type_display',
    header: sortable('Tipo'),
    cell: ({ row }) => h(resolveComponent('UBadge'), {
      color: 'neutral',
      variant: 'subtle',
      size: 'md'
    }, () => row.original.type_display)
  },
  {
    accessorKey: 'pending_count',
    header: sortable('Pendentes'),
    meta: { class: { td: 'text-right' } },
    cell: ({ row }) => h(resolveComponent('UBadge'), {
      color: row.original.pending_count > 0 ? 'warning' : 'neutral',
      variant: row.original.pending_count > 0 ? 'solid' : 'subtle',
      size: 'md',
      class: 'tabular-nums'
    }, () => `${row.original.pending_count} pendente${row.original.pending_count === 1 ? '' : 's'}`)
  },
  {
    id: 'actions',
    header: '',
    meta: { class: { td: 'w-12 text-right' } },
    cell: ({ row }) => h(resolveComponent('UButton'), {
      to: `/kds/${row.original.ref}`,
      color: 'primary',
      variant: 'soft',
      size: 'sm',
      icon: 'i-lucide-arrow-right',
      'aria-label': 'Abrir estação',
      onClick: (e: Event) => e.stopPropagation()
    })
  }
]

useHead({ title: 'Estações KDS' })
</script>

<template>
  <UDashboardPanel id="kds-index">
    <template #header>
      <UDashboardNavbar title="Estações KDS" icon="i-lucide-chef-hat">
        <template #leading>
          <UDashboardSidebarCollapse />
        </template>
        <template #right>
          <UBadge color="neutral" variant="subtle">{{ instances.length }} estações</UBadge>
          <UBadge :color="totalPending > 0 ? 'warning' : 'neutral'" variant="subtle" class="tabular-nums">
            {{ totalPending }} pendente{{ totalPending === 1 ? '' : 's' }}
          </UBadge>
        </template>
      </UDashboardNavbar>

      <UDashboardToolbar v-if="instances.length">
        <template #left>
          <UButton
            v-for="opt in typeOptions"
            :key="opt.value"
            size="sm"
            :color="typeFilter === opt.value ? 'primary' : 'neutral'"
            :variant="typeFilter === opt.value ? 'solid' : 'ghost'"
            :icon="opt.icon"
            :label="opt.label"
            @click="typeFilter = opt.value"
          />
        </template>
        <template #right>
          <UInput
            v-model="searchQuery"
            icon="i-lucide-search"
            placeholder="Buscar estação"
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
        title="Não foi possível carregar as estações"
        description="Verifique se você está autenticado como operador."
      >
        <template #actions>
          <UButton to="/admin/login/?next=/kds" label="Entrar no admin" target="_blank" />
        </template>
      </UAlert>

      <UEmpty
        v-else-if="!instances.length"
        icon="i-lucide-monitor-off"
        title="Nenhuma estação cadastrada"
        description="Configure uma instância KDS no Admin para começar."
      />

      <UEmpty
        v-else-if="!filteredInstances.length"
        icon="i-lucide-search-x"
        title="Nenhuma estação com esse filtro"
      />

      <!-- GRID -->
      <UPageGrid v-else-if="view.mode.value === 'grid'">
        <UPageCard
          v-for="instance in filteredInstances"
          :key="instance.ref"
          :to="`/kds/${instance.ref}`"
          :title="instance.name"
          :description="instance.type_display"
          :icon="typeIcons[instance.type] || 'i-lucide-monitor'"
          variant="outline"
          spotlight
        >
          <template #footer>
            <div class="flex items-center justify-between">
              <UBadge color="neutral" variant="subtle">{{ instance.type_display }}</UBadge>
              <UBadge :color="instance.pending_count > 0 ? 'warning' : 'neutral'" variant="solid">
                {{ instance.pending_count }} pendente{{ instance.pending_count === 1 ? '' : 's' }}
              </UBadge>
            </div>
          </template>
        </UPageCard>
      </UPageGrid>

      <!-- LIST -->
      <UCard v-else :ui="{ body: 'p-0' }">
        <UTable
          v-bind="{ onSelect: (_e: Event, row: any) => router.push(`/kds/${row.original.ref}`) }"
          v-model:sorting="sorting"
          v-model:expanded="expanded"
          :data="filteredInstances"
          :columns="columns"
          sticky
          class="cursor-pointer"
          :ui="{ tr: 'hover:bg-elevated/50 transition-colors' }"
        >
          <template #expanded="{ row }">
            <div class="grid sm:grid-cols-[1fr_auto] gap-4 p-3 bg-elevated/30">
              <div>
                <p class="text-xs uppercase tracking-wide text-muted mb-1">Estação</p>
                <p class="text-sm">
                  <strong class="text-highlighted">{{ row.original.name }}</strong> — {{ row.original.type_display }}
                </p>
                <p class="text-sm text-muted mt-1 font-mono">{{ row.original.ref }}</p>
              </div>
              <div class="flex items-center gap-2 sm:justify-end">
                <UButton
                  :to="`/kds/${row.original.ref}`"
                  color="primary"
                  variant="soft"
                  size="sm"
                  icon="i-lucide-arrow-right"
                  trailing
                  label="Abrir estação"
                  @click.stop
                />
              </div>
            </div>
          </template>
        </UTable>
      </UCard>
    </template>
  </UDashboardPanel>
</template>
