<script setup lang="ts">
import type { CatalogItemProjection, CatalogSectionProjection, MenuResponse } from '~/types/shopman'

const { setFromServer } = useCartState()
const apiPath = useShopmanApiPath()
const { data, pending, error } = await useFetch<MenuResponse>(apiPath('/api/v1/storefront/menu/'), {
  credentials: 'include'
})

watchEffect(() => setFromServer(data.value?.cart))

const searchQuery = ref('')
const catalog = computed(() => data.value?.catalog)
const normalizedSearch = computed(() => normalizeText(searchQuery.value))

function normalizeText (value: string | null | undefined): string {
  return (value || '')
    .normalize('NFD')
    .replace(/\p{Diacritic}/gu, '')
    .toLowerCase()
    .trim()
}

function sectionIcon (section: CatalogSectionProjection): string {
  const source = normalizeText(`${section.icon || ''} ${section.label}`)
  if (source.includes('cafe') || source.includes('coffee')) return 'i-lucide-coffee'
  if (source.includes('croissant') || source.includes('folhado')) return 'i-lucide-croissant'
  if (source.includes('pao') || source.includes('paes') || source.includes('padaria') || source.includes('bakery') || source.includes('focaccia') || source.includes('brioche')) return 'i-lucide-wheat'
  if (source.includes('combo') || source.includes('cesta') || source.includes('kit')) return 'i-lucide-package'
  if (source.includes('doce') || source.includes('chocolate') || source.includes('sobremesa')) return 'i-lucide-cookie'
  if (source.includes('bebida') || source.includes('suco')) return 'i-lucide-cup-soda'
  return 'i-lucide-utensils'
}

function matchesSearch (item: CatalogItemProjection, section: CatalogSectionProjection, query: string): boolean {
  const haystack = normalizeText([
    item.name,
    item.short_description,
    item.category,
    section.label,
    item.tags.join(' '),
    item.dietary_info.join(' ')
  ].filter(Boolean).join(' '))

  return haystack.includes(query)
}

const visibleSections = computed(() => {
  if (!catalog.value) return []
  const query = normalizedSearch.value
  if (!query) return catalog.value.sections

  return catalog.value.sections
    .map(section => ({
      ...section,
      items: section.items.filter(item => matchesSearch(item, section, query))
    }))
    .filter(section => section.items.length)
})

const hasSearch = computed(() => normalizedSearch.value.length > 0)
const hasResults = computed(() => visibleSections.value.some(section => section.items.length))
const sectionNavigation = computed(() => catalog.value?.sections.map(section => ({
  label: section.label,
  icon: sectionIcon(section),
  to: `#${section.ref}`,
  badge: section.items.length
})) || [])

useHead({
  title: 'Cardápio | Shopman Nuxt'
})
</script>

<template>
  <UPage class="shell">
    <ShopHeader />

    <UContainer id="menu-top" class="page-container menu-page-container">
      <UPageHeader
        title="Cardápio"
        description="Escolha seus itens e acompanhe o carrinho em tempo real."
        :links="[
          { label: 'Carrinho', to: '/cart', icon: 'i-lucide-shopping-bag', color: 'neutral', variant: 'outline', size: 'sm', class: 'hidden sm:inline-flex' }
        ]"
        :ui="{
          root: 'py-0 sm:py-0 border-b-0',
          title: 'text-2xl sm:text-3xl',
          description: 'text-sm sm:text-base',
          links: 'gap-2'
        }"
      />

      <div v-if="pending">
        <USkeleton class="h-28 w-full rounded-md" />
      </div>

      <UAlert
        v-else-if="error"
        color="error"
        variant="soft"
        title="Não foi possível carregar o menu"
      />

      <div v-else-if="catalog?.has_items" class="menu-toolbar">
        <UInput
          v-model="searchQuery"
          icon="i-lucide-search"
          color="neutral"
          variant="outline"
          size="lg"
          placeholder="Buscar produto ou categoria"
          class="menu-search"
          :ui="{ base: 'h-11 text-base' }"
        >
          <template #trailing>
            <UButton
              v-if="searchQuery"
              icon="i-lucide-x"
              color="neutral"
              variant="ghost"
              size="xs"
              aria-label="Limpar busca"
              @click="searchQuery = ''"
            />
          </template>
        </UInput>

        <UNavigationMenu
          v-if="catalog.sections.length"
          :items="sectionNavigation"
          variant="pill"
          color="neutral"
          class="menu-section-nav"
          :ui="{
            root: 'w-full overflow-x-auto',
            list: 'flex-nowrap gap-1.5',
            item: 'shrink-0',
            link: 'whitespace-nowrap min-h-10 px-4',
            linkLabel: 'whitespace-nowrap overflow-visible',
            linkLeadingIcon: 'size-4'
          }"
          aria-label="Seções do menu"
        />
      </div>
    </UContainer>

    <UContainer v-if="catalog" class="menu-list-container">
      <UEmpty
        v-if="!catalog.has_items"
        icon="i-lucide-store"
        title="Cardápio indisponível"
        description="Nenhum item publicado no momento."
      />

      <UEmpty
        v-else-if="hasSearch && !hasResults"
        icon="i-lucide-search-x"
        title="Nada encontrado"
        :description="`Sem resultados para ${searchQuery}.`"
      />

      <template v-else>
        <section
        v-for="section in catalog.sections"
          v-show="visibleSections.some(visible => visible.ref === section.ref)"
        :id="section.ref"
        :key="section.ref"
          class="menu-section"
      >
          <div class="section-heading">
            <div class="section-heading-copy">
              <UIcon :name="sectionIcon(section)" class="size-5" />
              <div>
                <h2 class="section-title">{{ section.label }}</h2>
                <p v-if="section.description" class="section-description">{{ section.description }}</p>
              </div>
            </div>
            <UBadge color="neutral" variant="soft">
              {{ visibleSections.find(visible => visible.ref === section.ref)?.items.length || 0 }} itens
            </UBadge>
          </div>

          <UPageGrid class="shop-products-grid">
            <ProductCard
              v-for="item in visibleSections.find(visible => visible.ref === section.ref)?.items || []"
              :key="item.sku"
              :item="item"
            />
          </UPageGrid>
        </section>
      </template>
    </UContainer>

    <BottomCartBar />
    <ShopBottomTabs />
  </UPage>
</template>
