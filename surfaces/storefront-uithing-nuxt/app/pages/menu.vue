<script setup lang="ts">
import type { CatalogItemProjection, CatalogSectionProjection, MenuResponse } from '~/types/shopman'

const apiPath = useShopmanApiPath()
const { setFromServer } = useCartState()
const { data, pending, error, refresh } = await useFetch<MenuResponse>(apiPath('/api/v1/storefront/menu/'), {
  credentials: 'include'
})

watch(() => data.value?.cart, cart => {
  setFromServer(cart)
}, { immediate: true })

const query = ref('')
const activeSection = ref('all')
const searchPanelOpen = ref(false)
const pillRailTailWidth = ref(160)

const catalog = computed(() => data.value?.catalog || null)
const sections = computed(() => catalog.value?.sections || [])
const allItems = computed(() => catalog.value?.items || [])
const favoriteRef = computed(() => catalog.value?.favorite_category_ref || '')
const normalizedQuery = computed(() => normalizeSearchText(query.value))
const sectionBySku = computed(() => {
  const map = new Map<string, CatalogSectionProjection>()
  for (const section of sections.value) {
    for (const item of section.items) {
      if (!map.has(item.sku)) map.set(item.sku, section)
    }
  }
  return map
})
const activeSections = computed(() => {
  const q = normalizedQuery.value
  if (!q) return sections.value
  return sections.value
    .map(section => ({
      ...section,
      items: section.items.filter(item => matches(item, section, q))
    }))
    .filter(section => section.items.length)
})

const filteredCount = computed(() => activeSections.value.reduce((sum, section) => sum + section.items.length, 0))
const allFilteredCount = computed(() => {
  const q = normalizedQuery.value
  if (!q) return allItems.value.length
  return sections.value.reduce((sum, section) => {
    return sum + section.items.filter(item => matches(item, section, q)).length
  }, 0)
})
const sectionOptions = computed(() => {
  const q = normalizedQuery.value
  return sections.value
    .map(section => ({
      ref: section.ref,
      label: section.label,
      count: q ? section.items.filter(item => matches(item, section, q)).length : section.items.length,
      isFavorite: !!favoriteRef.value && [section.ref, section.category?.ref, section.dynamic_ref].includes(favoriteRef.value)
    }))
    .filter(section => !q || section.count > 0)
})
const activeSectionLabel = computed(() => {
  if (activeSection.value === 'all') return 'Tudo'
  return sections.value.find(section => section.ref === activeSection.value)?.label || 'Seção'
})
const activeSectionCount = computed(() => {
  if (activeSection.value === 'all') return filteredCount.value
  return sectionOptions.value.find(section => section.ref === activeSection.value)?.count || 0
})
const searchResultOptions = computed(() => {
  const q = normalizedQuery.value
  if (!q) return []
  return allItems.value
    .filter(item => matches(item, sectionBySku.value.get(item.sku), q))
    .slice(0, 8)
})
const menuFocusLabel = computed(() => {
  if (pending.value) return 'Carregando o cardápio.'
  const count = formatCount(activeSectionCount.value, 'item encontrado', 'itens encontrados')
  const section = activeSectionLabel.value
  const term = query.value.trim()
  if (term && activeSection.value !== 'all') return `${count} em ${section} para "${term}".`
  if (term) return `${count} para "${term}".`
  if (activeSection.value !== 'all') return `${count} em ${section}.`
  return `${formatCount(filteredCount.value, 'item disponível', 'itens disponíveis')}.`
})

function matches (item: CatalogItemProjection, section: CatalogSectionProjection | undefined, search: string) {
  return normalizeSearchText([
    item.name,
    item.short_description,
    item.category,
    section?.label,
    (item.tags || []).join(' '),
    (item.search_terms || []).join(' '),
    (item.allergens || []).join(' '),
    (item.dietary_info || []).join(' ')
  ].join(' ')).includes(search)
}

function productRoute (sku: string) {
  return `/product/${encodeURIComponent(sku)}`
}

function focusSearchInput () {
  if (!import.meta.client) return
  document.getElementById('menu-search')?.focus()
}

function openSearchPanel () {
  searchPanelOpen.value = true
  void nextTick(focusSearchInput)
}

function closeSearchPanel () {
  searchPanelOpen.value = false
  query.value = ''
}

function sectionDomId (ref: string) {
  return `menu-section-${ref.replace(/[^a-zA-Z0-9_-]/g, '-')}`
}

function menuScrollOffset () {
  if (!import.meta.client) return 140
  const headerHeight = document.querySelector('header')?.getBoundingClientRect().height || 64
  const filterHeight = document.querySelector('[data-menu-filterbar]')?.getBoundingClientRect().height || 56
  return headerHeight + filterHeight + 16
}

function scrollBehavior (): ScrollBehavior {
  if (!import.meta.client) return 'auto'
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'
}

function updatePillRailTailWidth () {
  if (!import.meta.client) return
  const rail = document.querySelector<HTMLElement>('[data-menu-pillrail]')
  pillRailTailWidth.value = Math.max(112, (rail?.clientWidth || 224) - 24)
}

function centerSectionPill (ref: string, behavior: ScrollBehavior = 'auto') {
  if (!import.meta.client) return
  updatePillRailTailWidth()
  const pill = Array.from(document.querySelectorAll<HTMLElement>('[data-menu-pill-ref]'))
    .find(element => element.dataset.menuPillRef === ref)
  const rail = pill?.closest<HTMLElement>('[data-menu-pillrail]')
  if (!pill || !rail) return
  const pillRect = pill.getBoundingClientRect()
  const railRect = rail.getBoundingClientRect()
  const left = rail.scrollLeft + (pillRect.left - railRect.left)
  const maxLeft = Math.max(0, rail.scrollWidth - rail.clientWidth)
  rail.scrollTo({
    left: Math.min(maxLeft, Math.max(0, left)),
    behavior
  })
}

function scrollToSection (ref: string) {
  if (!import.meta.client) return
  const target = ref === 'all'
    ? document.querySelector<HTMLElement>('[data-menu-results]')
    : document.getElementById(sectionDomId(ref))
  if (!target) return

  target.scrollIntoView({
    block: 'start',
    inline: 'nearest',
    behavior: scrollBehavior()
  })
}

function selectSection (value: string | number | undefined) {
  const ref = String(value || 'all')
  holdActiveSection(ref)
  activeSection.value = ref
  void nextTick(() => {
    centerSectionPill(ref, scrollBehavior())
    scrollToSection(ref)
    window.setTimeout(() => {
      if (programmaticScrollRef !== ref) return
      activeSection.value = ref
      centerSectionPill(ref, scrollBehavior())
      scrollToSection(ref)
    }, 180)
    window.setTimeout(() => {
      if (programmaticScrollRef !== ref) return
      activeSection.value = ref
      centerSectionPill(ref)
      programmaticScrollRef = ''
      programmaticScrollUntil = 0
      queueActiveSectionSync()
    }, 900)
  })
}

async function chooseSectionFromSearch (ref: string) {
  searchPanelOpen.value = false
  query.value = ''
  await nextTick()
  selectSection(ref)
}

function chooseSearchResult (sku: string) {
  searchPanelOpen.value = false
  query.value = ''
  return navigateTo(productRoute(sku))
}

let scrollRaf = 0
let programmaticScrollRef = ''
let programmaticScrollUntil = 0

function holdActiveSection (ref: string) {
  programmaticScrollRef = ref
  programmaticScrollUntil = Date.now() + 900
}

function syncActiveSectionFromScroll () {
  if (!import.meta.client) return
  if (programmaticScrollRef && Date.now() < programmaticScrollUntil) {
    activeSection.value = programmaticScrollRef
    return
  }

  const sectionEls = Array.from(document.querySelectorAll<HTMLElement>('[data-menu-section-ref]'))
  if (!sectionEls.length) {
    activeSection.value = 'all'
    centerSectionPill('all')
    return
  }

  const offset = menuScrollOffset()
  const activationLine = offset + 48
  const lastSection = sectionEls[sectionEls.length - 1]
  const nearDocumentEnd = window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 8
  if (nearDocumentEnd && lastSection) {
    const current = lastSection.dataset.menuSectionRef || 'all'
    activeSection.value = current
    centerSectionPill(current)
    return
  }

  if (sectionEls[0].getBoundingClientRect().top > activationLine) {
    activeSection.value = 'all'
    centerSectionPill('all')
    return
  }

  let current = sectionEls[0].dataset.menuSectionRef || 'all'
  for (const section of sectionEls) {
    if (section.getBoundingClientRect().top <= activationLine) {
      current = section.dataset.menuSectionRef || current
    }
  }
  activeSection.value = current
  centerSectionPill(current)
}

function queueActiveSectionSync () {
  if (!import.meta.client || scrollRaf) return
  scrollRaf = window.requestAnimationFrame(() => {
    scrollRaf = 0
    syncActiveSectionFromScroll()
  })
}

watch(sectionOptions, options => {
  if (activeSection.value !== 'all' && !options.some(section => section.ref === activeSection.value)) {
    activeSection.value = 'all'
  }
  void nextTick(queueActiveSectionSync)
})

onMounted(() => {
  updatePillRailTailWidth()
  window.addEventListener('scroll', queueActiveSectionSync, { passive: true })
  window.addEventListener('resize', updatePillRailTailWidth, { passive: true })
  window.addEventListener('resize', queueActiveSectionSync, { passive: true })
  queueActiveSectionSync()
})

onBeforeUnmount(() => {
  window.removeEventListener('scroll', queueActiveSectionSync)
  window.removeEventListener('resize', updatePillRailTailWidth)
  window.removeEventListener('resize', queueActiveSectionSync)
  if (scrollRaf) window.cancelAnimationFrame(scrollRaf)
})

useSeoMeta({
  title: 'Cardápio',
  description: () => catalog.value?.has_items ? `${allItems.value.length} itens publicados.` : 'Cardápio publicado.'
})
</script>

<template>
  <main class="shop-section">
    <div class="shop-container space-y-5">
      <UiBreadcrumbs
        :items="[
          { label: 'Início', link: '/' },
          { label: 'Cardápio' }
        ]"
      />

      <div class="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 class="text-2xl font-semibold leading-tight">Cardápio</h1>
          <p class="mt-1 text-sm text-muted-foreground">
            {{ pending ? 'Carregando o cardápio.' : `${formatCount(filteredCount, 'item disponível', 'itens disponíveis')} para escolher.` }}
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
        <UiAlertTitle>Cardápio indisponível</UiAlertTitle>
        <UiAlertDescription>
          <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <span>Não conseguimos carregar o cardápio agora.</span>
            <UiButton size="sm" variant="outline" @click="refresh">Atualizar</UiButton>
          </div>
        </UiAlertDescription>
      </UiAlert>

      <template v-else-if="catalog">
        <section data-menu-filterbar class="sticky top-16 z-30 w-screen border-y bg-background shadow-sm [margin-left:calc(50%_-_50vw)] [margin-right:calc(50%_-_50vw)]">
          <div class="shop-container py-2">
            <div class="flex items-center gap-2">
              <UiButton
                variant="outline"
                size="icon"
                icon="lucide:search"
                aria-label="Buscar no cardápio"
                class="shrink-0 rounded-full"
                @click="searchPanelOpen ? closeSearchPanel() : openSearchPanel()"
              />
              <UiTabs v-model="activeSection" class="min-w-0 flex-1" @update:model-value="selectSection">
                <div data-menu-pillrail class="no-scrollbar overflow-x-auto">
                  <UiTabsList :pill="false" class="gap-1 bg-transparent p-0">
                    <UiTabsTrigger
                      value="all"
                      data-menu-pill-ref="all"
                      :pill="false"
                      class="h-9 rounded-full border bg-background px-3 data-[state=active]:border-primary data-[state=active]:bg-primary data-[state=active]:text-primary-foreground data-[state=active]:shadow-none"
                    >
                      Tudo
                      <span class="ml-1 text-xs tabular-nums opacity-70">{{ allFilteredCount }}</span>
                    </UiTabsTrigger>
                    <UiTabsTrigger
                      v-for="section in sectionOptions"
                      :key="section.ref"
                      :value="section.ref"
                      :data-menu-pill-ref="section.ref"
                      :pill="false"
                      class="h-9 rounded-full border bg-background px-3 data-[state=active]:border-primary data-[state=active]:bg-primary data-[state=active]:text-primary-foreground data-[state=active]:shadow-none"
                    >
                      <Icon v-if="section.isFavorite" name="lucide:heart" class="mr-1 size-3.5" />
                      {{ section.label }}
                      <span class="ml-1 text-xs tabular-nums opacity-70">{{ section.count }}</span>
                    </UiTabsTrigger>
                    <span
                      aria-hidden="true"
                      data-menu-pillrail-tail
                      class="block h-px shrink-0"
                      :style="{ width: `${pillRailTailWidth}px` }"
                    />
                  </UiTabsList>
                </div>
              </UiTabs>
            </div>

            <div v-if="searchPanelOpen" class="pt-2">
              <UiLabel for="menu-search" class="sr-only">Buscar no cardápio</UiLabel>
              <UiInputGroup>
                <UiInputGroupAddon>
                  <Icon name="lucide:search" class="size-4" />
                </UiInputGroupAddon>
                <UiInput
                  id="menu-search"
                  v-model="query"
                  type="search"
                  placeholder="Buscar no cardápio"
                  autocomplete="off"
                  class="flex-1 rounded-none border-0 bg-transparent shadow-none focus-visible:ring-0 dark:bg-transparent"
                />
                <UiInputGroupAddon align="inline-end">
                  <UiInputGroupButton
                    size="icon-xs"
                    icon="lucide:x"
                    aria-label="Fechar busca"
                    @click="closeSearchPanel"
                  />
                </UiInputGroupAddon>
              </UiInputGroup>

              <UiItemGroup class="mt-2 rounded-lg border bg-background">
                <template v-if="normalizedQuery">
                  <UiItem
                    v-for="item in searchResultOptions"
                    :key="item.sku"
                    as="button"
                    type="button"
                    size="sm"
                    class="w-full rounded-none text-left first:rounded-t-lg last:rounded-b-lg"
                    @click="chooseSearchResult(item.sku)"
                  >
                    <UiItemMedia v-if="item.image_url" variant="image">
                      <img :src="item.image_url" :alt="item.name" loading="lazy">
                    </UiItemMedia>
                    <UiItemMedia v-else variant="icon">
                      <Icon name="lucide:utensils" />
                    </UiItemMedia>
                    <UiItemContent>
                      <UiItemTitle>{{ item.name }}</UiItemTitle>
                      <UiItemDescription>{{ item.price_display }} · {{ sectionBySku.get(item.sku)?.label || item.availability_label }}</UiItemDescription>
                    </UiItemContent>
                    <UiItemActions>
                      <Icon name="lucide:arrow-up-right" class="size-4 text-muted-foreground" />
                    </UiItemActions>
                  </UiItem>
                  <UiItem v-if="!searchResultOptions.length" size="sm">
                    <UiItemMedia variant="icon">
                      <Icon name="lucide:search-x" />
                    </UiItemMedia>
                    <UiItemContent>
                      <UiItemTitle>Nada encontrado</UiItemTitle>
                      <UiItemDescription>Apague a busca ou escolha uma coleção.</UiItemDescription>
                    </UiItemContent>
                  </UiItem>
                </template>
                <template v-else>
                  <UiItem
                    v-for="section in sectionOptions"
                    :key="section.ref"
                    as="button"
                    type="button"
                    size="sm"
                    class="w-full rounded-none text-left first:rounded-t-lg last:rounded-b-lg"
                    @click="chooseSectionFromSearch(section.ref)"
                  >
                    <UiItemMedia variant="icon">
                      <Icon :name="section.isFavorite ? 'lucide:heart' : 'lucide:rows-3'" />
                    </UiItemMedia>
                    <UiItemContent>
                      <UiItemTitle>{{ section.label }}</UiItemTitle>
                      <UiItemDescription>{{ formatCount(section.count, 'item', 'itens') }}</UiItemDescription>
                    </UiItemContent>
                    <UiItemActions>
                      <Icon name="lucide:chevron-right" class="size-4 text-muted-foreground" />
                    </UiItemActions>
                  </UiItem>
                </template>
              </UiItemGroup>
            </div>

            <p class="sr-only" aria-live="polite">{{ menuFocusLabel }}</p>
          </div>
        </section>

        <section data-menu-results class="min-w-0 scroll-mt-36 space-y-4">
          <div v-if="activeSections.length" class="space-y-6">
            <div
              v-for="section in activeSections"
              :id="sectionDomId(section.ref)"
              :key="section.ref"
              :data-menu-section-ref="section.ref"
              class="scroll-mt-36 space-y-3"
            >
              <div class="space-y-0.5">
                <h2 class="text-base font-semibold">{{ section.label }}</h2>
                <p v-if="section.description" class="text-sm text-muted-foreground">{{ section.description }}</p>
              </div>
              <div class="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
                <ProductTile v-for="item in section.items" :key="`${section.ref}-${item.sku}`" :item="item" :section-label="section.label" />
              </div>
            </div>
          </div>

          <UiEmpty v-else class="border">
            <UiEmptyMedia variant="icon">
              <Icon name="lucide:search-x" />
            </UiEmptyMedia>
            <UiEmptyHeader>
              <UiEmptyTitle>Nada por esse filtro</UiEmptyTitle>
              <UiEmptyDescription>Limpe a busca ou escolha outra seção.</UiEmptyDescription>
            </UiEmptyHeader>
          </UiEmpty>
        </section>
      </template>
    </div>
  </main>
</template>
