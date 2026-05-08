<script setup lang="ts">
import type {
  CatalogItemProjection,
  CatalogSectionProjection,
  MenuResponse,
  ProductCommandMeta
} from '~/types/shopman'

const { cart, setFromServer } = useCartState()
const apiPath = useShopmanApiPath()
const { data, pending, error } = await useFetch<MenuResponse>(apiPath('/api/v1/storefront/menu/'), {
  credentials: 'include'
})

watchEffect(() => setFromServer(data.value?.cart))

const searchQuery = ref('')
const catalog = computed(() => data.value?.catalog)
const normalizedSearch = computed(() => normalizeText(searchQuery.value))
const heroItem = computed(() => catalog.value?.featured?.[0] || catalog.value?.items?.[0] || null)
const featuredItems = computed(() => {
  if (!catalog.value) return []
  const items = catalog.value.featured.length ? catalog.value.featured : catalog.value.items
  return items.slice(0, 3)
})
const catalogItemsLabel = computed(() => {
  const count = catalog.value?.items.length || 0
  return count === 1 ? '1 item' : `${count} itens`
})

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

function itemMeta (item: CatalogItemProjection): ProductCommandMeta {
  return {
    sku: item.sku,
    name: item.name,
    price_q: item.base_price_q,
    price_display: item.price_display,
    image_url: item.image_url
  }
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

    <UContainer v-if="pending" class="page-container">
      <USkeleton class="h-[28rem] w-full rounded-md" />
    </UContainer>

    <UContainer v-else-if="error" class="page-container">
      <UAlert
        color="error"
        variant="soft"
        title="Não foi possível carregar o menu"
      />
    </UContainer>

    <template v-else-if="catalog">
      <UPageHero
        v-if="catalog.has_items"
        class="commerce-hero"
        :links="[
          { label: 'Ver cardápio', href: '#cardapio', icon: 'i-lucide-arrow-down', color: 'primary', size: 'lg', class: 'commerce-primary-cta' },
          { label: cart.is_empty ? 'Carrinho' : cart.grand_total_display, to: '/cart', icon: 'i-lucide-shopping-bag', color: 'neutral', variant: 'outline', size: 'lg' }
        ]"
        :ui="{
          root: 'py-0',
          container: 'py-8 sm:py-10 lg:py-12 lg:grid lg:grid-cols-[minmax(0,0.9fr)_minmax(420px,1.1fr)] lg:items-center lg:gap-12',
          wrapper: 'items-start text-left',
          headline: 'justify-start',
          title: 'text-4xl sm:text-5xl lg:text-[56px] tracking-tight',
          description: 'max-w-xl text-base sm:text-lg text-muted',
          links: 'justify-start'
        }"
      >
        <template #headline>
          <UBadge color="neutral" variant="subtle" class="rounded-full px-3 py-1">
            {{ catalogItemsLabel }} disponíveis
          </UBadge>
        </template>

        <template #title>
          Cardápio da casa
        </template>

        <template #description>
          Pães, cafés e combos com disponibilidade validada no servidor a cada escolha.
        </template>

        <UPageCard
          v-if="heroItem"
          variant="outline"
          spotlight
          spotlight-color="neutral"
          class="commerce-hero-card"
          :ui="{ container: 'p-0 sm:p-0 gap-0', wrapper: 'gap-0' }"
        >
          <div class="commerce-hero-product">
            <NuxtLink
              :to="`/produto/${heroItem.sku}`"
              class="commerce-hero-image"
              :aria-label="`Ver ${heroItem.name}`"
            >
              <img v-if="heroItem.image_url" :src="heroItem.image_url" :alt="heroItem.name">
              <UIcon v-else name="i-lucide-cookie" class="size-12 text-neutral-400" />
            </NuxtLink>

            <div class="commerce-hero-product-body">
              <div class="commerce-product-eyebrow">
                <UBadge
                  v-if="heroItem.promotion_label"
                  color="primary"
                  variant="solid"
                >
                  {{ heroItem.promotion_label }}
                </UBadge>
                <UBadge v-else color="neutral" variant="soft">
                  Destaque
                </UBadge>
                <span>{{ heroItem.availability_label }}</span>
              </div>

              <div>
                <h2 class="commerce-hero-product-title">
                  <NuxtLink :to="`/produto/${heroItem.sku}`">
                    {{ heroItem.name }}
                  </NuxtLink>
                </h2>
                <p v-if="heroItem.short_description" class="commerce-hero-product-description">
                  {{ heroItem.short_description }}
                </p>
              </div>

              <div class="commerce-hero-product-footer">
                <div>
                  <div v-if="heroItem.original_price_display" class="shop-original-price">
                    {{ heroItem.original_price_display }}
                  </div>
                  <div class="commerce-hero-price">{{ heroItem.price_display }}</div>
                </div>
                <ProductStepper
                  :meta="itemMeta(heroItem)"
                  :can-add="heroItem.can_add_to_cart"
                  :max-qty="heroItem.available_qty"
                  add-label="Adicionar"
                  :unavailable-label="heroItem.availability_label"
                />
              </div>
            </div>
          </div>
        </UPageCard>
      </UPageHero>

      <UContainer v-else class="page-container">
        <UEmpty
          icon="i-lucide-store"
          title="Cardápio indisponível"
          description="Nenhum item publicado no momento."
        />
      </UContainer>

      <UPageSection
        v-if="featuredItems.length"
        id="destaques"
        headline="Seleção"
        title="Destaques do cardápio"
        description="Uma primeira olhada nos itens mais fortes da vitrine."
        :ui="{
          root: 'scroll-mt-(--ui-header-height)',
          container: 'py-8 sm:py-10 gap-6',
          headline: 'font-medium text-xs text-primary uppercase tracking-wide'
        }"
      >
        <UPageGrid class="commerce-featured-grid">
          <ProductCard
            v-for="item in featuredItems"
            :key="item.sku"
            :item="item"
          />
        </UPageGrid>
      </UPageSection>

      <UPageSection
        v-if="catalog.has_items"
        id="cardapio"
        title="Cardápio completo"
        :description="hasSearch ? `Filtrando por “${searchQuery}”.` : 'Navegue por categoria ou busque pelo item desejado.'"
        :ui="{
          root: 'scroll-mt-(--ui-header-height)',
          container: 'py-8 sm:py-10 gap-6'
        }"
      >
        <UPageCard
          variant="subtle"
          class="commerce-controls"
          :ui="{ container: 'p-3 sm:p-4 gap-3', wrapper: 'gap-3' }"
        >
          <div class="commerce-controls-grid">
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
              class="menu-section-nav commerce-mobile-nav"
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
        </UPageCard>

        <UEmpty
          v-if="hasSearch && !hasResults"
          icon="i-lucide-search-x"
          title="Nada encontrado"
          :description="`Sem resultados para ${searchQuery}.`"
        />

        <div v-else class="commerce-catalog-layout">
          <UPageCard
            v-if="catalog.sections.length"
            variant="outline"
            class="commerce-sidebar"
            :ui="{ container: 'p-2 sm:p-2', wrapper: 'gap-1' }"
          >
            <UNavigationMenu
              :items="sectionNavigation"
              orientation="vertical"
              variant="link"
              color="neutral"
              :ui="{
                root: 'w-full',
                list: 'gap-1',
                link: 'justify-between rounded-md px-3 py-2',
                linkLabel: 'whitespace-normal text-left',
                linkLeadingIcon: 'size-4'
              }"
              aria-label="Categorias"
            />
          </UPageCard>

          <div class="commerce-sections">
            <section
              v-for="section in visibleSections"
              :id="section.ref"
              :key="section.ref"
              class="menu-section"
            >
              <UPageHeader
                :title="section.label"
                :description="section.description"
                :ui="{
                  root: 'py-0 sm:py-0 border-b-0',
                  title: 'text-xl sm:text-2xl',
                  description: 'text-sm text-muted'
                }"
              >
                <template #headline>
                  <UBadge color="neutral" variant="soft">
                    <UIcon :name="sectionIcon(section)" class="size-3.5" />
                    {{ section.items.length }} itens
                  </UBadge>
                </template>
              </UPageHeader>

              <UPageGrid class="shop-products-grid">
                <ProductCard
                  v-for="item in section.items"
                  :key="item.sku"
                  :item="item"
                />
              </UPageGrid>
            </section>
          </div>
        </div>
      </UPageSection>
    </template>

    <BottomCartBar />
    <ShopBottomTabs />
  </UPage>
</template>
