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

function normalizeText (value: string | null | undefined): string {
  return (value || '').normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase().trim()
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
  return normalizeText([item.name, item.short_description, item.category, section.label, item.tags.join(' '), item.dietary_info.join(' ')].filter(Boolean).join(' ')).includes(query)
}

function itemMeta (item: CatalogItemProjection): ProductCommandMeta {
  return { sku: item.sku, name: item.name, price_q: item.base_price_q, price_display: item.price_display, image_url: item.image_url }
}

const visibleSections = computed(() => {
  if (!catalog.value) return []
  const query = normalizedSearch.value
  if (!query) return catalog.value.sections
  return catalog.value.sections
    .map(section => ({ ...section, items: section.items.filter(item => matchesSearch(item, section, query)) }))
    .filter(section => section.items.length)
})

const hasSearch = computed(() => normalizedSearch.value.length > 0)
const hasResults = computed(() => visibleSections.value.some(s => s.items.length))
const catalogDescription = computed(() => hasSearch.value ? `Resultados para "${searchQuery.value}".` : 'Navegue por categoria ou busque pelo nome.')
const sectionNavigation = computed(() => catalog.value?.sections.map(section => ({
  label: section.label,
  icon: sectionIcon(section),
  to: `#${section.ref}`,
  badge: section.items.length
})) || [])

useHead({ title: 'Cardápio' })
</script>

<template>
  <div>
    <UContainer v-if="pending" class="py-16">
      <USkeleton class="h-96 w-full" />
    </UContainer>

    <UContainer v-else-if="error" class="py-16">
      <UAlert color="error" variant="soft" title="Não foi possível carregar o cardápio" />
    </UContainer>

    <template v-else-if="catalog">
      <!-- Hero -->
      <UPageHero v-if="catalog.has_items && heroItem">
        <template #headline>
          <UBadge color="neutral" variant="subtle" class="rounded-full px-3 py-1">
            Fresquinho do forno
          </UBadge>
        </template>

        <template #title>
          <span class="block">Feito à mão,</span>
          <span class="block">todo dia.</span>
        </template>

        <template #description>
          Do forno para a sua mesa. Escolha, peça e acompanhe — tudo no seu tempo.
        </template>

        <template #links>
          <UButton label="Ver cardápio" to="#cardapio" icon="i-lucide-arrow-down" size="xl" />
          <UButton
            v-if="!cart.is_empty"
            :label="'Carrinho · ' + cart.grand_total_display"
            to="/cart"
            icon="i-lucide-shopping-bag"
            color="neutral"
            variant="outline"
            size="xl"
          />
        </template>

        <!-- Hero product card -->
        <UPageCard
          :to="`/produto/${heroItem.sku}`"
          :title="heroItem.name"
          :description="heroItem.short_description"
          variant="outline"
          orientation="horizontal"
          spotlight
          class="w-full"
        >
          <NuxtLink
            :to="`/produto/${heroItem.sku}`"
            class="product-image block overflow-hidden rounded-lg bg-elevated aspect-4/3 lg:aspect-auto lg:h-full lg:min-h-72"
          >
            <img v-if="heroItem.image_url" :src="heroItem.image_url" :alt="heroItem.name" class="size-full object-cover">
            <UIcon v-else name="i-lucide-cookie" class="absolute inset-0 m-auto size-12 text-muted" />
          </NuxtLink>

          <template #header>
            <div class="flex flex-wrap items-center gap-2">
              <UBadge v-if="heroItem.promotion_label" color="primary" variant="solid">{{ heroItem.promotion_label }}</UBadge>
              <UBadge v-else color="neutral" variant="subtle">Destaque</UBadge>
              <span class="text-sm text-muted">{{ heroItem.availability_label }}</span>
            </div>
          </template>

          <template #footer>
            <div class="flex items-end justify-between gap-4">
              <div>
                <div v-if="heroItem.original_price_display" class="text-sm text-muted line-through">
                  {{ heroItem.original_price_display }}
                </div>
                <div class="text-2xl font-bold tabular-nums">{{ heroItem.price_display }}</div>
              </div>
              <ProductStepper
                :meta="itemMeta(heroItem)"
                :can-add="heroItem.can_add_to_cart"
                :max-qty="heroItem.available_qty"
                add-label="Adicionar"
                :unavailable-label="heroItem.availability_label"
                size="sm"
              />
            </div>
          </template>
        </UPageCard>
      </UPageHero>

      <UPageHero v-else-if="!catalog.has_items">
        <template #title>Cardápio indisponível</template>
        <template #description>Nenhum item publicado no momento. Volte em breve!</template>
      </UPageHero>

      <!-- Featured -->
      <UPageSection v-if="featuredItems.length" id="destaques" headline="Seleção" title="Destaques do cardápio" description="Os mais vendidos e curados pela casa.">
        <UPageGrid>
          <ProductCard v-for="item in featuredItems" :key="item.sku" :item="item" />
        </UPageGrid>
      </UPageSection>

      <!-- Full catalog -->
      <UPageSection v-if="catalog.has_items" id="cardapio" title="Cardápio completo" :description="catalogDescription">
        <UPageCard variant="subtle" :ui="{ container: 'p-3 sm:p-4 gap-3', wrapper: 'gap-3' }">
          <UInput
            v-model="searchQuery"
            icon="i-lucide-search"
            color="neutral"
            variant="outline"
            size="lg"
            placeholder="Buscar no cardápio..."
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
            class="section-nav lg:hidden overflow-x-auto py-1"
            aria-label="Seções do cardápio"
          />
        </UPageCard>

        <UEmpty
          v-if="hasSearch && !hasResults"
          icon="i-lucide-search-x"
          title="Nada encontrado"
          :description="'Sem resultados para ' + searchQuery + '.'"
        />

        <div v-else class="grid lg:grid-cols-[220px_1fr] gap-6 items-start">
          <!-- Sidebar -->
          <UCard
            v-if="catalog.sections.length"
            class="hidden lg:block sticky top-[calc(var(--ui-header-height)+24px)]"
            :ui="{ body: 'p-2 sm:p-2' }"
          >
            <UNavigationMenu
              :items="sectionNavigation"
              orientation="vertical"
              variant="link"
              color="neutral"
              aria-label="Categorias"
            />
          </UCard>

          <!-- Sections -->
          <div class="grid gap-12">
            <section
              v-for="section in visibleSections"
              :id="section.ref"
              :key="section.ref"
              class="scroll-mt-[calc(var(--ui-header-height)+104px)]"
            >
              <UPageHeader :title="section.label" :description="section.description">
                <template #headline>
                  <UBadge color="neutral" variant="subtle">
                    <UIcon :name="sectionIcon(section)" class="size-3.5" />
                    {{ section.items.length }} {{ section.items.length === 1 ? 'item' : 'itens' }}
                  </UBadge>
                </template>
              </UPageHeader>

              <UPageGrid class="mt-4">
                <ProductCard v-for="item in section.items" :key="item.sku" :item="item" />
              </UPageGrid>
            </section>
          </div>
        </div>
      </UPageSection>
    </template>
  </div>
</template>
