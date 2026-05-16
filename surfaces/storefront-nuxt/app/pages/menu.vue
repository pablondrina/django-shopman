<script setup lang="ts">
import type {
  CatalogItemProjection,
  CatalogSectionProjection,
  MenuResponse,
  ProductMutationMeta
} from '~/types/shopman'

type UiColor = 'neutral' | 'primary' | 'success' | 'warning' | 'error' | 'info'

const { cart, setFromServer } = useCartState()
const apiPath = useShopmanApiPath()
const requestUrl = useRequestURL()
const route = useRoute()
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
  return items.slice(0, 4)
})
const heroSupportingItems = computed(() => featuredItems.value.filter(item => item.sku !== heroItem.value?.sku).slice(0, 3))
const totalItems = computed(() => catalog.value?.items.length || 0)
const primarySections = computed(() => catalog.value?.sections.slice(0, 5) || [])
const activeSectionRef = ref('')
const happyHour = computed(() => catalog.value?.happy_hour?.active ? catalog.value.happy_hour : null)
const favoriteCategoryRef = computed(() => catalog.value?.favorite_category_ref || '')

function normalizeText (value: string | null | undefined): string {
  return (value || '').normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase().trim()
}

function availabilityColor (item: CatalogItemProjection): UiColor {
  if (item.availability === 'available') return 'success'
  if (item.availability === 'low_stock') return 'warning'
  if (item.availability === 'planned_ok') return 'info'
  if (item.availability === 'unavailable') return 'error'
  return 'neutral'
}

function matchesSearch (item: CatalogItemProjection, section: CatalogSectionProjection, query: string): boolean {
  return normalizeText([
    item.name,
    item.short_description,
    item.category,
    section.label,
    (item.tags || []).join(' '),
    (item.search_terms || []).join(' '),
    (item.dietary_info || []).join(' '),
    (item.allergens || []).join(' ')
  ].filter(Boolean).join(' ')).includes(query)
}

function itemMeta (item: CatalogItemProjection): ProductMutationMeta {
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
const searchSummary = computed(() => {
  if (!hasSearch.value) return `${totalItems.value} itens no cardápio.`
  const count = visibleSections.value.reduce((sum, section) => sum + section.items.length, 0)
  return `${count} ${count === 1 ? 'resultado encontrado' : 'resultados encontrados'} para ${searchQuery.value}.`
})
function sectionHash (ref: string): string {
  return `#${encodeURIComponent(ref)}`
}

const sectionNavigation = computed(() => visibleSections.value.map(section => ({
  label: section.label,
  to: sectionHash(section.ref),
  badge: section.items.length,
  ref: section.ref,
  icon: useShopmanIcon(section.icon),
  active: activeSectionRef.value === section.ref,
  favorite: Boolean(favoriteCategoryRef.value && (
    favoriteCategoryRef.value === section.ref ||
    favoriteCategoryRef.value === section.category?.ref ||
    favoriteCategoryRef.value === section.dynamic_ref
  ))
})))

if (import.meta.client) {
  let sectionObserver: IntersectionObserver | null = null

  function centerSectionRail (ref: string) {
    const el = document.getElementById(`menu-section-nav-${ref}`)
    el?.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' })
  }

  function scrollToRouteSection () {
    const ref = decodeURIComponent(route.hash.replace(/^#/, ''))
    if (!ref) return
    activeSectionRef.value = ref
    const el = document.getElementById(ref)
    el?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    centerSectionRail(ref)
  }

  function setupSectionObserver () {
    sectionObserver?.disconnect()
    const refs = visibleSections.value.map(section => section.ref)
    if (!refs.length) return
    if (!activeSectionRef.value || !refs.includes(activeSectionRef.value)) activeSectionRef.value = refs[0] || ''
    sectionObserver = new IntersectionObserver((entries) => {
      const visible = entries
        .filter(entry => entry.isIntersecting)
        .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0]
      if (visible?.target?.id) activeSectionRef.value = visible.target.id
    }, {
      rootMargin: '-35% 0px -55% 0px',
      threshold: [0.1, 0.3, 0.6]
    })
    for (const ref of refs) {
      const el = document.getElementById(ref)
      if (el) sectionObserver.observe(el)
    }
  }

  watch(visibleSections, () => {
    nextTick(() => setupSectionObserver())
  }, { flush: 'post' })

  watch(activeSectionRef, (ref) => {
    if (ref) nextTick(() => centerSectionRail(ref))
  })

  watch(() => route.hash, () => {
    nextTick(() => scrollToRouteSection())
  })

  onMounted(() => {
    nextTick(() => {
      setupSectionObserver()
      scrollToRouteSection()
    })
  })
  onBeforeUnmount(() => {
    sectionObserver?.disconnect()
  })
}

function absoluteUrl (path: string): string {
  return new URL(path, requestUrl.origin).toString()
}

const menuItemListJsonLd = computed(() => {
  if (!catalog.value?.items.length) return null
  return {
    '@context': 'https://schema.org',
    '@type': 'ItemList',
    name: 'Cardápio',
    itemListElement: catalog.value.items.map((item, index) => ({
      '@type': 'ListItem',
      position: index + 1,
      name: item.name,
      url: absoluteUrl(`/produto/${item.sku}`)
    }))
  }
})

const menuBreadcrumbJsonLd = computed(() => ({
  '@context': 'https://schema.org',
  '@type': 'BreadcrumbList',
  itemListElement: [
    { '@type': 'ListItem', position: 1, name: 'Início', item: absoluteUrl('/') },
    { '@type': 'ListItem', position: 2, name: 'Cardápio', item: absoluteUrl('/menu') }
  ]
}))

useHead(() => ({
  title: 'Cardápio',
  script: [
    menuItemListJsonLd.value
      ? { type: 'application/ld+json', innerHTML: JSON.stringify(menuItemListJsonLd.value) }
      : null,
    { type: 'application/ld+json', innerHTML: JSON.stringify(menuBreadcrumbJsonLd.value) }
  ].filter(Boolean)
}))

useSeoMeta({
  title: 'Cardápio',
  description: () => catalog.value?.has_items
    ? `Cardápio com ${catalog.value.items.length} itens disponíveis para pedido.`
    : 'Cardápio publicado pela loja.'
})
</script>

<template>
  <div>
    <UContainer v-if="pending" class="py-16">
      <USkeleton class="h-96 w-full" />
    </UContainer>

    <UContainer v-else-if="error" class="py-16">
      <UAlert
        color="error"
        variant="soft"
        :title="operationalCopy.loadFailure.menu.title"
        :description="operationalCopy.loadFailure.menu.description"
      />
    </UContainer>

    <template v-else-if="catalog">
      <section v-if="catalog.has_items && heroItem" class="relative isolate overflow-hidden border-b border-default bg-default text-white">
        <img
          v-if="heroItem.image_url"
          :src="heroItem.image_url"
          :alt="heroItem.name"
          loading="eager"
          fetchpriority="high"
          decoding="async"
          sizes="100vw"
          class="absolute inset-0 size-full object-cover"
        >
        <div v-else class="absolute inset-0 bg-elevated" />
        <div class="absolute inset-0 bg-gradient-to-t from-black/90 via-black/58 to-black/24" />
        <div class="absolute inset-x-0 bottom-0 h-28 bg-gradient-to-t from-default to-transparent" />

        <UContainer class="relative flex min-h-[560px] items-end py-8 sm:min-h-[640px] lg:py-12">
          <div class="grid min-w-0 w-full gap-6 lg:grid-cols-[minmax(0,1fr)_390px] lg:items-end">
            <div class="min-w-0 w-full max-w-[22rem] pb-2 sm:max-w-3xl">
              <p class="shop-section-kicker shop-section-kicker--inverse-muted">
                Cardápio do dia
              </p>
              <h1 class="shop-hero-copy mt-4 max-w-[22rem] text-3xl font-bold leading-tight sm:max-w-2xl sm:text-5xl lg:text-6xl">
                Cardápio com disponibilidade informada.
              </h1>
              <p class="mt-5 max-w-[22rem] text-base leading-relaxed text-white/76 sm:max-w-xl sm:text-lg">
                Preços e disponibilidade vêm do cardápio publicado pela loja.
              </p>

              <div class="mt-7 flex flex-wrap gap-3">
                <UButton label="Explorar cardápio" to="#cardapio" size="xl" color="neutral" />
                <UButton
                  v-if="!cart.is_empty"
                  :label="cart.summary_pending ? 'Atualizando...' : cart.grand_total_display"
                  to="/cart"
                  color="neutral"
                  variant="outline"
                  size="xl"
                  class="bg-white/5 text-white ring-white/30 hover:bg-white/10"
                />
              </div>

              <div v-if="primarySections.length" class="section-nav mt-7 flex max-w-full gap-2 overflow-x-auto pb-1">
                <UButton
                  v-for="section in primarySections"
                  :key="section.ref"
                  :to="`#${section.ref}`"
                  :label="section.label"
                  color="neutral"
                  variant="soft"
                  size="sm"
                  class="shrink-0 bg-white/10 text-white ring-white/20 hover:bg-white/15"
                />
              </div>
            </div>

            <aside class="shop-glass-panel min-w-0 w-full max-w-[22rem] justify-self-start overflow-hidden rounded-lg p-4 sm:max-w-none">
              <div class="flex items-start gap-3">
                <NuxtLink
                  :to="`/produto/${heroItem.sku}`"
                  class="product-image relative size-24 shrink-0 overflow-hidden rounded-lg bg-white/10"
                  :aria-label="`Ver ${heroItem.name}`"
                >
                  <img v-if="heroItem.image_url" :src="heroItem.image_url" :alt="heroItem.name" loading="lazy" decoding="async" sizes="96px" class="size-full object-cover">
                  <UIcon v-else name="i-lucide-image" class="absolute inset-0 m-auto size-8 text-white/60" />
                </NuxtLink>
                <div class="min-w-0 flex-1">
                  <div class="mb-2 flex flex-wrap gap-2">
                    <UBadge v-if="heroItem.promotion_label" color="primary" variant="solid">{{ heroItem.promotion_label }}</UBadge>
                    <UBadge :color="availabilityColor(heroItem)" variant="subtle">{{ heroItem.availability_label }}</UBadge>
                  </div>
                  <NuxtLink :to="`/produto/${heroItem.sku}`" class="line-clamp-2 text-lg font-bold leading-snug text-white hover:text-primary">
                    {{ heroItem.name }}
                  </NuxtLink>
                  <p v-if="heroItem.short_description" class="mt-1 line-clamp-2 text-sm leading-relaxed text-white/68">
                    {{ heroItem.short_description }}
                  </p>
                </div>
              </div>

              <div class="mt-4 flex items-end justify-between gap-3 border-t border-white/15 pt-4">
                <div class="min-w-0">
                  <p v-if="heroItem.original_price_display" class="text-sm text-white/48 line-through">{{ heroItem.original_price_display }}</p>
                  <p class="text-2xl font-bold tabular-nums">{{ heroItem.price_display }}</p>
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

              <div v-if="heroSupportingItems.length" class="mt-4 grid gap-2 border-t border-white/15 pt-4">
                <NuxtLink
                  v-for="item in heroSupportingItems"
                  :key="item.sku"
                  :to="`/produto/${item.sku}`"
                  class="flex items-center justify-between gap-3 rounded-lg px-2 py-1.5 text-sm text-white/72 hover:bg-white/10 hover:text-white"
                >
                  <span class="truncate">{{ item.name }}</span>
                  <span class="shrink-0 tabular-nums">{{ item.price_display }}</span>
                </NuxtLink>
              </div>
            </aside>
          </div>
        </UContainer>
      </section>

      <UContainer v-else-if="!catalog.has_items" class="py-16">
        <UEmpty
          icon="i-lucide-store"
          title="Cardápio indisponível"
          description="Nenhum item publicado no momento. Volte em breve."
        />
      </UContainer>

      <section v-if="featuredItems.length" id="destaques" class="shop-quiet-band py-10 sm:py-14">
        <UContainer>
          <div class="mb-5 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <p class="shop-section-kicker">
                Seleção
              </p>
              <h2 class="mt-2 text-2xl font-bold text-highlighted sm:text-3xl">Destaques do cardápio</h2>
              <p class="mt-2 max-w-2xl text-sm leading-relaxed text-muted sm:text-base">
                Itens em evidência, conforme o cardápio publicado.
              </p>
            </div>
            <UBadge color="neutral" variant="subtle" class="w-fit">
              {{ totalItems }} {{ totalItems === 1 ? 'item publicado' : 'itens publicados' }}
            </UBadge>
          </div>
          <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <ProductCard v-for="item in featuredItems" :key="item.sku" :item="item" />
          </div>
        </UContainer>
      </section>

      <section v-if="happyHour" class="py-6">
        <UContainer>
          <UAlert
            color="primary"
            variant="subtle"
            title="Happy hour ativo"
            :description="`${happyHour.discount_percent}% de desconto entre ${happyHour.start} e ${happyHour.end}. Produtos elegíveis já mostram o preço aplicado.`"
          />
        </UContainer>
      </section>

      <section v-if="catalog.has_items" id="cardapio" class="py-10 sm:py-14">
        <UContainer>
          <div class="mb-5 flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <p class="shop-section-kicker">
                Catálogo
              </p>
              <h2 class="mt-2 text-2xl font-bold text-highlighted sm:text-3xl">Cardápio completo</h2>
              <p class="mt-2 text-sm leading-relaxed text-muted sm:text-base">{{ catalogDescription }}</p>
            </div>
            <UButton v-if="!cart.is_empty" to="/cart" :label="cart.summary_pending ? 'Atualizando...' : cart.grand_total_display" class="w-fit" />
          </div>

          <div class="sticky top-[calc(var(--ui-header-height)+8px)] z-20 -mx-4 border-y border-default bg-default/92 px-4 py-3 backdrop-blur-xl sm:mx-0 sm:rounded-lg sm:border">
            <p class="sr-only" aria-live="polite">{{ searchSummary }}</p>
            <div class="grid min-w-0 gap-3 xl:grid-cols-[minmax(18rem,1fr)_minmax(0,auto)] xl:items-center">
              <div role="search">
                <UInput
                  v-model="searchQuery"
                  icon="i-lucide-search"
                  color="neutral"
                  variant="outline"
                  size="lg"
                  placeholder="Buscar no cardápio..."
                  aria-label="Buscar no cardápio"
                  class="w-full"
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
              </div>

              <nav
                v-if="sectionNavigation.length"
                class="section-nav flex min-w-0 max-w-full gap-2 overflow-x-auto py-1"
                aria-label="Seções do cardápio"
              >
                <UButton
                  v-for="section in sectionNavigation"
                  :key="section.to"
                  :to="section.to"
                  :color="section.active ? 'primary' : 'neutral'"
                  :variant="section.active ? 'solid' : 'soft'"
                  :icon="section.icon"
                  size="sm"
                  class="shrink-0"
                  :id="`menu-section-nav-${section.ref}`"
                >
                  <span class="max-w-36 truncate">{{ section.label }}</span>
                  <span v-if="section.favorite" class="ml-1 text-xs">Preferido</span>
                  <span class="ml-1 text-xs text-muted tabular-nums">{{ section.badge }}</span>
                </UButton>
              </nav>
            </div>
          </div>

          <UEmpty
            v-if="hasSearch && !hasResults"
            icon="i-lucide-search-x"
            title="Nada encontrado"
            :description="'Sem resultados para ' + searchQuery + '.'"
            class="mt-10"
          />

          <div v-else class="mt-8 grid gap-8 lg:grid-cols-[232px_minmax(0,1fr)] lg:items-start">
            <aside
              v-if="sectionNavigation.length"
              class="hidden lg:block lg:sticky lg:top-[calc(var(--ui-header-height)+92px)]"
            >
              <div class="rounded-lg border border-default bg-elevated/55 p-2">
                <UNavigationMenu
                  :items="sectionNavigation"
                  orientation="vertical"
                  variant="link"
                  color="neutral"
                  aria-label="Categorias"
                />
              </div>
            </aside>

            <div class="grid gap-11">
              <section
                v-for="section in visibleSections"
                :id="section.ref"
                :key="section.ref"
                class="scroll-mt-[calc(var(--ui-header-height)+120px)]"
              >
                <div class="mb-4 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
                  <div>
                    <div class="flex flex-wrap items-center gap-2 text-sm font-semibold text-primary">
                      <UIcon :name="useShopmanIcon(section.icon)" class="size-4 shrink-0" aria-hidden="true" />
                      <span>{{ section.label }}</span>
                      <UBadge
                        v-if="sectionNavigation.find(item => item.ref === section.ref)?.favorite"
                        color="primary"
                        variant="subtle"
                        size="xs"
                      >
                        Preferido
                      </UBadge>
                    </div>
                    <p v-if="section.description" class="mt-1 max-w-2xl text-sm leading-relaxed text-muted">
                      {{ section.description }}
                    </p>
                  </div>
                  <UBadge color="neutral" variant="subtle" class="w-fit">
                    {{ section.items.length }} {{ section.items.length === 1 ? 'item' : 'itens' }}
                  </UBadge>
                </div>

                <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                  <ProductCard v-for="item in section.items" :key="item.sku" :item="item" />
                </div>
              </section>
            </div>
          </div>
        </UContainer>
      </section>
    </template>
  </div>
</template>
