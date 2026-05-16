<script setup lang="ts">
import type { NavigationMenuItem, TableColumn } from '@nuxt/ui'
import type { POSProductProjection, POSResponse, POSTabProjection } from '~/types/backstage'

const apiPath = useBackstageApiPath()
const action = useBackstageAction()
const cart = usePosCart()
const toast = useToast()

const search = ref('')
const activeCollection = ref<string | null>(null)
const activeView = ref<'comandas' | 'atual' | 'caixa' | 'turno'>('comandas')

const tabsView = useViewMode('pos-comandas', 'grid')
const tabsSearch = ref('')
const tabsStateFilter = ref<'all' | 'open' | 'paid'>('all')
const { sortable: sortableTab } = useSortableHeader()
const tabsSorting = ref([{ id: 'last_touched_display', desc: true }])
const tabsExpanded = ref<Record<string, boolean>>({})

const { data, pending, error, refresh } = await useFetch<POSResponse>(
  () => apiPath('/api/v1/backstage/pos/'),
  { credentials: 'include' }
)

const pos = computed(() => data.value?.pos)
const shift = computed(() => data.value?.shift)
const tabs = computed(() => data.value?.tabs || [])

const filteredProducts = computed<POSProductProjection[]>(() => {
  const products = pos.value?.products || []
  let filtered = products
  if (activeCollection.value) {
    filtered = filtered.filter(p => p.collection_ref === activeCollection.value)
  }
  if (search.value) {
    const q = search.value.toLowerCase()
    filtered = filtered.filter(p => p.name.toLowerCase().includes(q) || p.sku.toLowerCase().includes(q))
  }
  return filtered
})

const subnav = computed<NavigationMenuItem[]>(() => [
  {
    label: 'Comandas',
    icon: 'i-lucide-receipt',
    badge: tabs.value.filter(t => t.state === 'open').length || undefined,
    onSelect: () => { activeView.value = 'comandas' },
    active: activeView.value === 'comandas'
  },
  {
    label: cart.isOpen.value ? `Atendimento · #${cart.state.value.tabDisplay}` : 'Atendimento',
    icon: 'i-lucide-shopping-cart',
    badge: cart.itemCount.value || undefined,
    onSelect: () => { activeView.value = 'atual' },
    active: activeView.value === 'atual',
    disabled: !cart.isOpen.value
  },
  {
    label: 'Caixa',
    icon: 'i-lucide-wallet',
    onSelect: () => { activeView.value = 'caixa' },
    active: activeView.value === 'caixa'
  },
  {
    label: 'Turno',
    icon: 'i-lucide-clock',
    onSelect: () => { activeView.value = 'turno' },
    active: activeView.value === 'turno'
  }
])

const filteredTabs = computed(() => {
  let filtered = tabs.value
  if (tabsStateFilter.value !== 'all') {
    filtered = filtered.filter(t => t.state === tabsStateFilter.value)
  }
  if (tabsSearch.value.trim()) {
    const q = tabsSearch.value.toLowerCase().trim()
    filtered = filtered.filter(t =>
      t.display_code.toLowerCase().includes(q)
      || (t.customer_name || '').toLowerCase().includes(q)
      || (t.customer_phone || '').toLowerCase().includes(q)
    )
  }
  return filtered
})

const tabsStateOptions = [
  { label: 'Todas', value: 'all', icon: 'i-lucide-layers' },
  { label: 'Abertas', value: 'open', icon: 'i-lucide-receipt' },
  { label: 'Pagas', value: 'paid', icon: 'i-lucide-check' }
] as const

const tabsColumns: TableColumn<POSTabProjection>[] = [
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
    accessorKey: 'display_code',
    header: sortableTab('Comanda'),
    cell: ({ row }) => h('span', { class: 'font-semibold text-highlighted tabular-nums' }, `#${row.original.display_code}`)
  },
  {
    accessorKey: 'customer_name',
    header: sortableTab('Cliente'),
    cell: ({ row }) => h('div', { class: 'min-w-0' }, [
      h('p', { class: 'text-sm text-highlighted truncate' }, row.original.customer_name || '—'),
      row.original.customer_phone
        ? h('p', { class: 'text-sm text-muted tabular-nums' }, row.original.customer_phone)
        : null
    ])
  },
  {
    accessorKey: 'status_label',
    header: sortableTab('Status'),
    cell: ({ row }) => h(resolveComponent('UBadge'), {
      color: row.original.state === 'open' ? 'warning' : 'neutral',
      variant: 'subtle',
      size: 'md'
    }, () => row.original.status_label)
  },
  {
    accessorKey: 'item_count',
    header: sortableTab('Itens'),
    meta: { class: { td: 'text-right tabular-nums' } },
    cell: ({ row }) => h('span', { class: 'tabular-nums text-sm text-muted' }, String(row.original.item_count))
  },
  {
    accessorFn: (row) => {
      const raw = (row.total_display || '').replace(/[^\d,.-]/g, '').replace(/\./g, '').replace(',', '.')
      return Number.parseFloat(raw) || 0
    },
    id: 'total',
    header: sortableTab('Total'),
    meta: { class: { td: 'text-right' } },
    cell: ({ row }) => h('strong', { class: 'tabular-nums text-highlighted' }, row.original.total_display)
  },
  {
    accessorKey: 'last_touched_display',
    header: sortableTab('Atualizado'),
    cell: ({ row }) => h('span', { class: 'text-sm text-muted' }, row.original.last_touched_display)
  }
]

async function openTab (tab: POSTabProjection) {
  const ok = await cart.openTab(tab)
  if (ok) {
    activeView.value = 'atual'
    await refresh()
  }
}

async function saveAndExit () {
  const ok = await cart.save()
  if (ok) {
    cart.reset()
    activeView.value = 'comandas'
    await refresh()
  }
}

async function clearCurrent () {
  if (!confirm(`Liberar comanda #${cart.state.value.tabDisplay}? Itens serão descartados.`)) return
  const ok = await cart.clearTab()
  if (ok) {
    activeView.value = 'comandas'
    await refresh()
  }
}

const paymentMethod = ref<'cash' | 'pix' | 'card'>('pix')

async function finalize () {
  const result = await cart.closeSale(paymentMethod.value)
  if (result?.orderRef) {
    toast.add({
      icon: 'i-lucide-receipt',
      color: 'success',
      title: `Pedido #${result.orderRef} criado`,
      description: 'Comanda liberada.'
    })
    activeView.value = 'comandas'
    await refresh()
  }
}

const newTabOpen = ref(false)
async function onTabCreated () {
  await refresh()
}

// Cash session forms (existing, unchanged)
const openingAmount = ref('0,00')
const closingAmount = ref('0,00')
const closingNotes = ref('')
const movementKind = ref<'sangria' | 'suprimento'>('sangria')
const movementAmount = ref('0,00')
const movementReason = ref('')
const submitting = ref(false)

async function openCash () {
  submitting.value = true
  const res = await action.call('/api/v1/backstage/pos/cash/open/', {
    body: { opening_amount: openingAmount.value },
    successTitle: 'Caixa aberto'
  })
  if (res !== null) await refresh()
  submitting.value = false
}

async function closeCash () {
  submitting.value = true
  const res = await action.call('/api/v1/backstage/pos/cash/close/', {
    body: { closing_amount: closingAmount.value, notes: closingNotes.value },
    successTitle: 'Caixa fechado'
  })
  if (res !== null) await refresh()
  submitting.value = false
}

async function registerMovement () {
  if (!movementAmount.value) return
  submitting.value = true
  const res = await action.call('/api/v1/backstage/pos/cash/movement/', {
    body: { kind: movementKind.value, amount: movementAmount.value, reason: movementReason.value },
    successTitle: movementKind.value === 'sangria' ? 'Sangria registrada' : 'Suprimento registrado'
  })
  if (res !== null) {
    movementAmount.value = '0,00'
    movementReason.value = ''
    await refresh()
  }
  submitting.value = false
}

// Keyboard shortcuts (Atendimento view only)
defineShortcuts({
  '/': () => {
    if (activeView.value === 'atual') {
      const input = document.querySelector<HTMLInputElement>('input[placeholder="Buscar produto"]')
      input?.focus()
    }
  },
  meta_enter: () => {
    if (activeView.value === 'atual' && cart.isOpen.value && cart.state.value.items.length) {
      void finalize()
    }
  },
  escape: () => {
    if (activeView.value === 'atual') {
      activeView.value = 'comandas'
    }
  }
})

useHead({ title: 'POS' })
</script>

<template>
  <UDashboardPanel id="pos">
    <template #header>
      <UDashboardNavbar title="POS · Balcão" icon="i-lucide-shopping-bag">
        <template #leading>
          <UDashboardSidebarCollapse />
        </template>

        <template #right>
          <UBadge :color="pos?.has_open_cash_session ? 'success' : 'warning'" variant="subtle">
            <UIcon :name="pos?.has_open_cash_session ? 'i-lucide-unlock' : 'i-lucide-lock'" class="size-3.5" />
            {{ pos?.has_open_cash_session ? 'Caixa aberto' : 'Caixa fechado' }}
          </UBadge>
          <UBadge color="neutral" variant="subtle" class="tabular-nums hidden sm:flex">
            {{ shift?.count ?? 0 }} hoje · {{ shift?.total_display || 'R$ 0,00' }}
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
          <UButton
            v-if="pos?.has_open_cash_session"
            color="primary"
            icon="i-lucide-plus"
            label="Nova comanda"
            size="sm"
            @click="newTabOpen = true"
          />
        </template>
      </UDashboardNavbar>

      <UDashboardToolbar>
        <template #left>
          <UNavigationMenu :items="subnav" variant="link" highlight class="-mx-1 flex-1" />
        </template>
        <template v-if="activeView === 'comandas'" #right>
          <UInput
            v-model="tabsSearch"
            icon="i-lucide-search"
            placeholder="Buscar comanda ou cliente"
            size="sm"
            class="w-56 max-w-full"
          />
          <ViewModeToggle v-model="tabsView.mode.value" />
        </template>
      </UDashboardToolbar>
    </template>

    <template #body>
      <USkeleton v-if="pending" class="h-40 w-full" />

      <UAlert v-else-if="error" color="error" variant="soft" title="Não foi possível carregar o POS" />

      <div v-else-if="pos">
        <UAlert
          v-if="!pos.has_open_cash_session && activeView !== 'caixa'"
          icon="i-lucide-lock"
          color="warning"
          variant="subtle"
          title="Caixa fechado"
          description="Vá para a aba Caixa e abra a sessão antes de iniciar atendimentos."
          class="mb-4"
        >
          <template #actions>
            <UButton size="sm" label="Ir para Caixa" @click="activeView = 'caixa'" />
          </template>
        </UAlert>

        <!-- COMANDAS -->
        <div v-if="activeView === 'comandas'">
          <div class="flex flex-wrap items-center gap-1.5 mb-3">
            <UButton
              v-for="opt in tabsStateOptions"
              :key="opt.value"
              size="sm"
              :color="tabsStateFilter === opt.value ? 'primary' : 'neutral'"
              :variant="tabsStateFilter === opt.value ? 'solid' : 'ghost'"
              :icon="opt.icon"
              :label="opt.label"
              @click="tabsStateFilter = opt.value"
            />
          </div>

          <UEmpty
            v-if="!tabs.length"
            icon="i-lucide-receipt"
            title="Nenhuma comanda"
            description="Cadastre uma nova comanda para começar."
            :actions="pos.has_open_cash_session ? [{ label: 'Nova comanda', icon: 'i-lucide-plus', onClick: () => { newTabOpen = true } }] : undefined"
          />

          <UEmpty
            v-else-if="!filteredTabs.length"
            icon="i-lucide-search-x"
            title="Nenhuma comanda com esse filtro"
          />

          <!-- GRID -->
          <div v-else-if="tabsView.mode.value === 'grid'" class="grid gap-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 xl:grid-cols-8">
            <UCard
              v-for="tab in filteredTabs"
              :key="tab.code"
              as="button"
              type="button"
              :ui="{ body: 'p-2' }"
              class="text-left transition-colors"
              :class="[
                cart.state.value.tabCode === tab.code && 'ring-2 ring-primary',
                tab.item_count > 0
                  ? 'bg-warning/5 hover:bg-warning/10 ring-1 ring-warning/30'
                  : 'hover:bg-elevated'
              ]"
              @click="openTab(tab)"
            >
              <div class="flex items-center justify-between gap-2">
                <p class="font-semibold text-base tabular-nums">#{{ tab.display_code }}</p>
                <span
                  v-if="tab.item_count > 0"
                  class="text-xs tabular-nums px-1.5 py-0.5 rounded-full bg-warning/15 text-warning font-semibold"
                >
                  {{ tab.item_count }}
                </span>
              </div>
              <p v-if="tab.customer_name" class="text-sm text-highlighted truncate mt-0.5">{{ tab.customer_name }}</p>
              <p v-if="tab.item_count > 0" class="text-sm font-bold tabular-nums text-highlighted mt-1">
                {{ tab.total_display }}
              </p>
            </UCard>
          </div>

          <!-- LIST -->
          <UCard v-else :ui="{ body: 'p-0' }">
            <UTable
              v-bind="{ onSelect: (_e: Event, row: any) => openTab(row.original) }"
              v-model:sorting="tabsSorting"
              v-model:expanded="tabsExpanded"
              :data="filteredTabs"
              :columns="tabsColumns"
              sticky
              class="cursor-pointer"
              :ui="{ tr: 'hover:bg-elevated/50 transition-colors' }"
            >
              <template #expanded="{ row }">
                <div class="grid sm:grid-cols-[1fr_auto] gap-4 p-3 bg-elevated/30">
                  <div class="min-w-0">
                    <p class="text-xs uppercase tracking-wide text-muted mb-1">Itens</p>
                    <p v-if="row.original.items_preview" class="text-sm">{{ row.original.items_preview }}</p>
                    <p v-else class="text-sm text-muted">Comanda vazia.</p>
                  </div>
                  <div class="flex flex-wrap items-center gap-2 sm:justify-end">
                    <UButton
                      color="primary"
                      variant="soft"
                      size="sm"
                      icon="i-lucide-shopping-cart"
                      label="Atender"
                      @click.stop="openTab(row.original)"
                    />
                  </div>
                </div>
              </template>
            </UTable>
          </UCard>
        </div>

        <!-- ATENDIMENTO ATUAL -->
        <div v-else-if="activeView === 'atual'">
          <UEmpty
            v-if="!cart.isOpen.value"
            icon="i-lucide-shopping-cart"
            title="Nenhum atendimento aberto"
            description="Volte para Comandas e selecione uma para atender."
            :actions="[{ label: 'Ver comandas', icon: 'i-lucide-arrow-left', onClick: () => { activeView = 'comandas' } }]"
          />
          <div v-else class="grid lg:grid-cols-[1fr_380px] gap-4 items-start">
            <div class="grid gap-3">
              <div class="flex flex-wrap gap-2">
                <UInput v-model="search" icon="i-lucide-search" placeholder="Buscar produto" class="flex-1 min-w-[200px]" />
                <UButton size="sm" :color="activeCollection === null ? 'primary' : 'neutral'" :variant="activeCollection === null ? 'solid' : 'outline'" label="Tudo" @click="activeCollection = null" />
                <UButton
                  v-for="col in pos.collections"
                  :key="col.ref"
                  size="sm"
                  :color="activeCollection === col.ref ? 'primary' : 'neutral'"
                  :variant="activeCollection === col.ref ? 'solid' : 'outline'"
                  :label="col.name"
                  @click="activeCollection = col.ref"
                />
              </div>
              <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
                <POSProductTile
                  v-for="product in filteredProducts"
                  :key="product.sku"
                  :product="product"
                  @add="cart.addProduct"
                />
              </div>
            </div>

            <UCard variant="subtle" class="lg:sticky lg:top-4">
              <template #header>
                <div class="flex items-center justify-between gap-2">
                  <div class="min-w-0">
                    <p class="text-sm text-muted">Comanda</p>
                    <strong class="text-lg">#{{ cart.state.value.tabDisplay }}</strong>
                  </div>
                  <UTooltip text="Liberar comanda (descartar)">
                    <UButton size="sm" color="neutral" variant="ghost" icon="i-lucide-x" aria-label="Liberar" @click="clearCurrent" />
                  </UTooltip>
                </div>
              </template>

              <POSCustomerLookup class="mb-4" />

              <UEmpty
                v-if="!cart.state.value.items.length"
                icon="i-lucide-package-open"
                title="Carrinho vazio"
                description="Toque em produtos para adicionar."
              />

              <ul v-else class="grid gap-2 max-h-[50vh] overflow-auto pr-1">
                <li
                  v-for="item in cart.state.value.items"
                  :key="item.sku"
                  class="grid grid-cols-[1fr_auto] gap-2 items-start py-2 border-b border-default last:border-0"
                >
                  <div class="min-w-0">
                    <p class="font-semibold text-highlighted text-sm leading-tight">{{ item.name }}</p>
                    <p class="text-sm text-muted tabular-nums mt-0.5">
                      {{ item.qty }}× {{ new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(item.price_q / 100) }}
                    </p>
                  </div>
                  <div class="flex items-center gap-1 shrink-0">
                    <UButton
                      size="sm"
                      color="neutral"
                      variant="ghost"
                      icon="i-lucide-minus"
                      aria-label="Diminuir"
                      @click="cart.setQty(item.sku, item.qty - 1)"
                    />
                    <span class="text-sm tabular-nums w-6 text-center font-semibold">{{ item.qty }}</span>
                    <UButton
                      size="sm"
                      color="neutral"
                      variant="ghost"
                      icon="i-lucide-plus"
                      aria-label="Aumentar"
                      @click="cart.setQty(item.sku, item.qty + 1)"
                    />
                    <UButton
                      size="sm"
                      color="error"
                      variant="ghost"
                      icon="i-lucide-trash-2"
                      aria-label="Remover"
                      @click="cart.removeItem(item.sku)"
                    />
                  </div>
                </li>
              </ul>

              <template #footer>
                <div class="grid gap-3">
                  <div class="flex items-baseline justify-between">
                    <span class="font-medium">Total</span>
                    <strong class="text-2xl tabular-nums text-highlighted">{{ cart.totalDisplay.value }}</strong>
                  </div>

                  <URadioGroup
                    v-model="paymentMethod"
                    :items="[
                      { label: 'PIX', value: 'pix' },
                      { label: 'Cartão', value: 'card' },
                      { label: 'Dinheiro', value: 'cash' }
                    ]"
                    orientation="horizontal"
                    :ui="{ fieldset: 'gap-2' }"
                  />

                  <div class="grid grid-cols-2 gap-2">
                    <UButton
                      color="neutral"
                      variant="outline"
                      icon="i-lucide-bookmark"
                      label="Salvar"
                      :loading="cart.saving.value"
                      :disabled="!cart.state.value.items.length"
                      @click="saveAndExit"
                    />
                    <UButton
                      color="primary"
                      icon="i-lucide-credit-card"
                      label="Finalizar"
                      :loading="cart.closing.value"
                      :disabled="!cart.state.value.items.length"
                      @click="finalize"
                    />
                  </div>
                </div>
              </template>
            </UCard>
          </div>
        </div>

        <!-- CAIXA -->
        <div v-else-if="activeView === 'caixa'" class="grid lg:grid-cols-2 gap-4">
          <UCard>
            <template #header>
              <strong>{{ pos.has_open_cash_session ? 'Fechar caixa' : 'Abrir caixa' }}</strong>
            </template>
            <div v-if="pos.has_open_cash_session" class="grid gap-4">
              <UFormField label="Valor contado em caixa">
                <UInput v-model="closingAmount" placeholder="0,00" />
              </UFormField>
              <UFormField label="Observações (opcional)">
                <UTextarea v-model="closingNotes" :rows="2" placeholder="Anotações de fechamento" />
              </UFormField>
              <UButton block color="error" icon="i-lucide-lock" label="Fechar caixa" :loading="submitting" @click="closeCash" />
            </div>
            <div v-else class="grid gap-4">
              <UFormField label="Valor inicial em caixa">
                <UInput v-model="openingAmount" placeholder="0,00" />
              </UFormField>
              <UButton block color="primary" icon="i-lucide-unlock" label="Abrir caixa" :loading="submitting" @click="openCash" />
            </div>
          </UCard>

          <UCard v-if="pos.has_open_cash_session">
            <template #header><strong>Movimento de caixa</strong></template>
            <div class="grid gap-4">
              <URadioGroup
                v-model="movementKind"
                :items="[{ label: 'Sangria (saída)', value: 'sangria' }, { label: 'Suprimento (entrada)', value: 'suprimento' }]"
                orientation="horizontal"
              />
              <UFormField label="Valor">
                <UInput v-model="movementAmount" placeholder="0,00" />
              </UFormField>
              <UFormField label="Motivo">
                <UInput v-model="movementReason" placeholder="Ex: troco, pagamento de fornecedor" />
              </UFormField>
              <UButton block color="neutral" icon="i-lucide-arrow-right-left" label="Registrar movimento" :loading="submitting" :disabled="!movementAmount" @click="registerMovement" />
            </div>
          </UCard>
        </div>

        <!-- TURNO -->
        <div v-else-if="activeView === 'turno'" class="grid lg:grid-cols-2 gap-4">
          <UCard>
            <template #header><strong>Resumo do turno</strong></template>
            <dl class="grid gap-3">
              <div class="flex justify-between">
                <dt class="text-muted">Pedidos hoje</dt>
                <dd class="font-bold text-2xl tabular-nums text-highlighted">{{ shift?.count ?? 0 }}</dd>
              </div>
              <div class="flex justify-between">
                <dt class="text-muted">Total faturado</dt>
                <dd class="font-bold text-2xl tabular-nums text-highlighted">{{ shift?.total_display || 'R$ 0,00' }}</dd>
              </div>
            </dl>
          </UCard>
          <UCard v-if="shift?.last_ref">
            <template #header><strong>Último pedido</strong></template>
            <p class="text-base text-highlighted">#{{ shift.last_ref }}</p>
            <p class="text-2xl font-bold tabular-nums text-primary mt-2">{{ shift.last_total_display }}</p>
          </UCard>
        </div>
      </div>

      <POSNewTabModal v-model:open="newTabOpen" @created="onTabCreated" />
    </template>
  </UDashboardPanel>
</template>
