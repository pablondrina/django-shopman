<script setup lang="ts">
import type { CatalogItemProjection, CatalogSectionProjection, MenuResponse } from '~/types/shopman'

const apiPath = useShopmanApiPath()
const { setFromServer } = useCartState()
const { data, pending, error, refresh } = await useFetch<MenuResponse>(apiPath('/api/v1/storefront/menu/'), {
  credentials: 'include'
})

watchEffect(() => setFromServer(data.value?.cart))

const query = ref('')
const activeSection = ref('all')
const selectedSku = ref<string | null>(null)
const detailOpen = ref(false)

const catalog = computed(() => data.value?.catalog || null)
const sections = computed(() => catalog.value?.sections || [])
const allItems = computed(() => catalog.value?.items || [])
const favoriteRef = computed(() => catalog.value?.favorite_category_ref || '')
const normalizedQuery = computed(() => normalizeSearchText(query.value))
const activeSections = computed(() => {
  const raw = activeSection.value === 'all'
    ? sections.value
    : sections.value.filter(section => section.ref === activeSection.value)
  const q = normalizedQuery.value
  if (!q) return raw
  return raw
    .map(section => ({
      ...section,
      items: section.items.filter(item => matches(item, section, q))
    }))
    .filter(section => section.items.length)
})

const filteredCount = computed(() => activeSections.value.reduce((sum, section) => sum + section.items.length, 0))

function matches (item: CatalogItemProjection, section: CatalogSectionProjection, search: string) {
  return normalizeSearchText([
    item.name,
    item.short_description,
    item.category,
    section.label,
    (item.tags || []).join(' '),
    (item.search_terms || []).join(' '),
    (item.allergens || []).join(' '),
    (item.dietary_info || []).join(' ')
  ].join(' ')).includes(search)
}

function openProduct (sku: string) {
  selectedSku.value = sku
  detailOpen.value = true
}

function selectCommand (sku: string) {
  openProduct(sku)
}

useSeoMeta({
  title: 'Cardapio',
  description: () => catalog.value?.has_items ? `${allItems.value.length} itens publicados.` : 'Cardapio publicado.'
})
</script>

<template>
  <main class="shop-section">
    <div class="shop-container space-y-5">
      <div class="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <p class="shop-kicker">Cardapio</p>
          <h1 class="mt-1 text-3xl font-semibold leading-tight">Escolha com calma, ajuste em um toque</h1>
          <p class="mt-2 shop-muted">
            {{ pending ? 'Carregando o cardapio.' : `${formatCount(filteredCount, 'item disponivel', 'itens disponiveis')} para escolher.` }}
          </p>
        </div>
        <div v-if="catalog?.happy_hour?.active" class="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          Happy hour ativo: {{ catalog.happy_hour.discount_percent }}%
        </div>
      </div>

      <div v-if="pending" class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <UiSkeleton v-for="n in 6" :key="n" class="h-72 rounded-lg" />
      </div>

      <UiAlert v-else-if="error" variant="destructive">
        <UiAlertTitle>Cardapio indisponivel</UiAlertTitle>
        <UiAlertDescription>
          <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <span>Nao conseguimos carregar o cardapio agora.</span>
            <UiButton size="sm" variant="outline" @click="refresh">Atualizar</UiButton>
          </div>
        </UiAlertDescription>
      </UiAlert>

      <template v-else-if="catalog">
        <div class="grid grid-cols-1 gap-4 lg:grid-cols-[360px_minmax(0,1fr)]">
          <aside class="min-w-0 space-y-4 lg:sticky lg:top-24 lg:self-start">
            <UiCard>
              <UiCardHeader>
                <UiCardTitle>Encontrar item</UiCardTitle>
                <UiCardDescription>Busque por nome, ingrediente, categoria ou restricao.</UiCardDescription>
              </UiCardHeader>
              <UiCardContent class="space-y-3">
                <UiInput v-model="query" placeholder="Buscar por nome, ingrediente ou restricao..." />
                <UiCommand class="hidden h-72 border lg:block">
                  <UiCommandInput placeholder="Encontrar rapido..." />
                  <UiCommandList>
                    <UiCommandEmpty>Nenhum item encontrado.</UiCommandEmpty>
                    <UiCommandGroup heading="Produtos">
                      <UiCommandItem
                        v-for="item in allItems.slice(0, 40)"
                        :key="item.sku"
                        :value="`${item.name} ${item.sku}`"
                        @select="selectCommand(item.sku)"
                      >
                        <div class="flex min-w-0 items-center justify-between gap-3">
                          <span class="truncate">{{ item.name }}</span>
                          <UiBadge :variant="availabilityVariant(item.availability)">{{ item.price_display }}</UiBadge>
                        </div>
                      </UiCommandItem>
                    </UiCommandGroup>
                  </UiCommandList>
                </UiCommand>
              </UiCardContent>
            </UiCard>
          </aside>

          <section class="min-w-0 space-y-4">
            <UiTabs v-model="activeSection" class="min-w-0">
              <div class="no-scrollbar overflow-x-auto pb-1">
                <UiTabsList>
                  <UiTabsTrigger value="all">Tudo</UiTabsTrigger>
                  <UiTabsTrigger v-for="section in sections" :key="section.ref" :value="section.ref">
                    <span class="inline-flex items-center gap-1">
                      {{ section.label }}
                      <UiBadge v-if="favoriteRef && [section.ref, section.category?.ref, section.dynamic_ref].includes(favoriteRef)" variant="success">
                        habitual
                      </UiBadge>
                    </span>
                  </UiTabsTrigger>
                </UiTabsList>
              </div>
              <UiTabsContent value="all" class="space-y-6">
                <div v-for="section in activeSections" :key="section.ref" class="space-y-3">
                  <div>
                    <h2 class="text-xl font-semibold">{{ section.label }}</h2>
                    <p class="shop-muted">{{ section.description }}</p>
                  </div>
                  <div class="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
                    <ProductTile v-for="item in section.items" :key="`${section.ref}-${item.sku}`" :item="item" :section-label="section.label" @select="openProduct" />
                  </div>
                </div>
              </UiTabsContent>
              <UiTabsContent v-for="section in sections" :key="section.ref" :value="section.ref" class="space-y-6">
                <div v-for="visible in activeSections" :key="visible.ref" class="space-y-3">
                  <div>
                    <h2 class="text-xl font-semibold">{{ visible.label }}</h2>
                    <p class="shop-muted">{{ visible.description }}</p>
                  </div>
                  <div class="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
                    <ProductTile v-for="item in visible.items" :key="`${visible.ref}-${item.sku}`" :item="item" :section-label="visible.label" @select="openProduct" />
                  </div>
                </div>
              </UiTabsContent>
            </UiTabs>

            <UiAlert v-if="!activeSections.length">
              <UiAlertTitle>Nada por esse filtro</UiAlertTitle>
              <UiAlertDescription>Limpe a busca ou escolha outra secao.</UiAlertDescription>
            </UiAlert>
          </section>
        </div>
      </template>

      <ProductDetailSheet v-model:open="detailOpen" :sku="selectedSku" />
    </div>
  </main>
</template>
