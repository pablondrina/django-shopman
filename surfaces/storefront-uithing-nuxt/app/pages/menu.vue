<script setup lang="ts">
import type { CatalogItemProjection, CatalogSectionProjection, MenuResponse } from '~/types/shopman'

type SearchFilterKind = 'collection' | 'product' | 'keyword'

type SearchListOption = {
  key: string
  kind: SearchFilterKind
  value: string
  label: string
  meta: string
  icon: string
  imageUrl?: string
  item?: CatalogItemProjection
  section?: CatalogSectionProjection
}

type SearchResultGroup = {
  ref: string
  label: string
  options: SearchListOption[]
}

const FILTERED_SECTION_VALUE = 'filtered'

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
const selectedFilterKeys = ref<string[]>([])
const appliedFilterKeys = ref<string[]>([])

const catalog = computed(() => data.value?.catalog || null)
const sections = computed(() => catalog.value?.sections || [])
const allItems = computed(() => catalog.value?.items || [])
const uniqueItems = computed(() => uniqueItemsBySku(allItems.value))
const favoriteRef = computed(() => catalog.value?.favorite_category_ref || '')
const normalizedQuery = computed(() => normalizeSearchText(query.value))
const selectedFilterKeySet = computed(() => new Set(selectedFilterKeys.value))
const appliedFilterKeySet = computed(() => new Set(appliedFilterKeys.value))
const hasAppliedFilters = computed(() => appliedFilterKeys.value.length > 0)
const hasPendingFilterSelection = computed(() => {
  if (!selectedFilterKeys.value.length) return false
  if (selectedFilterKeys.value.length !== appliedFilterKeys.value.length) return true
  return selectedFilterKeys.value.some(key => !appliedFilterKeySet.value.has(key))
})
const sectionsBySku = computed(() => {
  const map = new Map<string, CatalogSectionProjection[]>()
  for (const section of sections.value) {
    for (const item of section.items) {
      const memberships = map.get(item.sku) || []
      memberships.push(section)
      map.set(item.sku, memberships)
    }
  }
  return map
})
const sectionBySku = computed(() => {
  const map = new Map<string, CatalogSectionProjection>()
  for (const [sku, memberships] of sectionsBySku.value.entries()) {
    const firstStaticSection = memberships.find(section => !section.is_dynamic)
    map.set(sku, firstStaticSection || memberships[0])
  }
  return map
})
const searchOrFilterMode = computed(() => Boolean(normalizedQuery.value || hasAppliedFilters.value))
const resultSections = computed(() => {
  if (!searchOrFilterMode.value) return sections.value
  const staticSections = sections.value.filter(section => !section.is_dynamic)
  const dynamicSections = sections.value.filter(section => section.is_dynamic)
  return [...staticSections, ...dynamicSections]
})
const activeSections = computed(() => {
  const q = normalizedQuery.value
  const seenSkus = new Set<string>()
  return resultSections.value
    .map(section => ({
      ...section,
      items: section.items.filter(item => {
        if (!itemPassesMenuFilters(item, section, q)) return false
        if (!searchOrFilterMode.value) return true
        if (seenSkus.has(item.sku)) return false
        seenSkus.add(item.sku)
        return true
      })
    }))
    .filter(section => section.items.length)
})

const filteredCount = computed(() => uniqueItemsBySku(activeSections.value.flatMap(section => [...section.items])).length)
const allFilteredCount = computed(() => {
  return filteredCount.value
})
const activeSectionCounts = computed(() => {
  return new Map(activeSections.value.map(section => [
    section.ref,
    uniqueItemsBySku([...section.items]).length
  ]))
})
const sectionOptions = computed(() => {
  const visibleSections = searchOrFilterMode.value ? resultSections.value : sections.value
  return visibleSections
    .map(section => ({
      ref: section.ref,
      label: section.label,
      count: searchOrFilterMode.value
        ? activeSectionCounts.value.get(section.ref) || 0
        : uniqueItemsBySku([...section.items]).length,
      isFavorite: !!favoriteRef.value && [section.ref, section.category?.ref, section.dynamic_ref].includes(favoriteRef.value)
    }))
    .filter(section => !searchOrFilterMode.value || section.count > 0)
})
const activeSectionLabel = computed(() => {
  if (activeSection.value === 'all') return 'Tudo'
  if (activeSection.value === FILTERED_SECTION_VALUE) return 'Filtrado'
  return sections.value.find(section => section.ref === activeSection.value)?.label || 'Seção'
})
const activeSectionCount = computed(() => {
  if (activeSection.value === 'all') return filteredCount.value
  if (activeSection.value === FILTERED_SECTION_VALUE) return filteredCount.value
  return sectionOptions.value.find(section => section.ref === activeSection.value)?.count || 0
})
const collectionSearchOptions = computed<SearchListOption[]>(() => {
  const q = normalizedQuery.value
  if (!q) return []
  return sections.value
    .map(section => ({
      section,
      score: collectionSearchScore(section, q)
    }))
    .filter(result => result.score < Number.POSITIVE_INFINITY)
    .sort((a, b) => a.score - b.score || a.section.label.localeCompare(b.section.label))
    .map(result => ({
      key: filterKey('collection', result.section.ref),
      kind: 'collection',
      value: result.section.ref,
      label: result.section.label,
      meta: formatCount(uniqueItemsBySku([...result.section.items]).length, 'item', 'itens'),
      icon: 'lucide:rows-3',
      section: result.section
    }))
    .slice(0, 12)
})
const productSearchOptions = computed<SearchListOption[]>(() => {
  const q = normalizedQuery.value
  if (!q) return []
  return uniqueItems.value
    .map(item => ({
      item,
      section: sectionBySku.value.get(item.sku),
      score: productSearchScore(item, q)
    }))
    .filter(result => result.score < Number.POSITIVE_INFINITY)
    .sort((a, b) => a.score - b.score || a.item.name.localeCompare(b.item.name))
    .map(result => ({
      key: filterKey('product', result.item.sku),
      kind: 'product',
      value: result.item.sku,
      label: result.item.name,
      meta: result.item.price_display,
      icon: 'lucide:utensils',
      imageUrl: result.item.image_url,
      item: result.item,
      section: result.section
    }))
    .slice(0, 12)
})
const keywordSearchOptions = computed<SearchListOption[]>(() => {
  const q = normalizedQuery.value
  if (!q) return []
  const options = new Map<string, SearchListOption & { skus: Set<string> }>()
  for (const item of uniqueItems.value) {
    const section = sectionBySku.value.get(item.sku)
    for (const keyword of keywordLabelsForItem(item)) {
      const normalized = normalizeSearchText(keyword)
      if (!normalized || !normalized.includes(q)) continue
      const key = filterKey('keyword', keyword)
      if (!options.has(key)) {
        options.set(key, {
          key,
          kind: 'keyword',
          value: keyword,
          label: keyword,
          meta: '0 itens',
          icon: 'lucide:tag',
          section,
          skus: new Set()
        })
      }
      options.get(key)?.skus.add(item.sku)
    }
  }
  return Array.from(options.values())
    .map(option => {
      const count = uniqueItems.value.filter(item => {
        return matchesProductAcrossCatalog(item, normalizeSearchText(option.value))
      }).length
      return {
        ...option,
        count,
        meta: formatCount(count, 'item', 'itens')
      }
    })
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label))
    .map(({ count: _count, skus: _skus, ...option }) => option)
    .slice(0, 8)
})
const searchResultGroups = computed<SearchResultGroup[]>(() => {
  if (!normalizedQuery.value) {
    return [{
      ref: 'collections',
      label: 'Coleções',
      options: sections.value.map(section => ({
        key: filterKey('collection', section.ref),
        kind: 'collection',
        value: section.ref,
        label: section.label,
        meta: formatCount(uniqueItemsBySku([...section.items]).length, 'item', 'itens'),
        icon: !!favoriteRef.value && [section.ref, section.category?.ref, section.dynamic_ref].includes(favoriteRef.value) ? 'lucide:heart' : 'lucide:rows-3',
        section
      }))
    }]
  }

  return [
    { ref: 'collections', label: 'Coleções', options: collectionSearchOptions.value },
    { ref: 'keywords', label: 'Palavras-chave', options: keywordSearchOptions.value },
    { ref: 'products', label: 'Produtos', options: productSearchOptions.value }
  ].filter(group => group.options.length)
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

function matchesProductAcrossCatalog (item: CatalogItemProjection, search: string) {
  return normalizeSearchText([
    item.name,
    item.short_description,
    item.category,
    ...((sectionsBySku.value.get(item.sku) || []).flatMap(section => [section.label, section.description, section.ref])),
    (item.tags || []).join(' '),
    (item.search_terms || []).join(' '),
    (item.allergens || []).join(' '),
    (item.dietary_info || []).join(' ')
  ].join(' ')).includes(search)
}

function collectionSearchScore (section: CatalogSectionProjection, search: string) {
  const label = normalizeSearchText(section.label)
  const haystack = normalizeSearchText([section.label, section.description, section.ref].join(' '))
  if (label === search) return 0
  if (label.startsWith(search)) return 1
  if (label.includes(search)) return 2
  if (haystack.includes(search)) return 3
  return Number.POSITIVE_INFINITY
}

function productSearchScore (item: CatalogItemProjection, search: string) {
  const name = normalizeSearchText(item.name)
  const directTerms = normalizeSearchText([
    item.name,
    (item.tags || []).join(' '),
    (item.search_terms || []).join(' ')
  ].join(' '))
  if (name === search) return 0
  if (name.startsWith(search)) return 1
  if (name.includes(search)) return 2
  if (directTerms.includes(search)) return 3
  if (matchesProductAcrossCatalog(item, search)) return 4
  return Number.POSITIVE_INFINITY
}

function uniqueItemsBySku (items: ReadonlyArray<CatalogItemProjection>) {
  const seen = new Set<string>()
  return items.filter(item => {
    if (seen.has(item.sku)) return false
    seen.add(item.sku)
    return true
  })
}

function itemPassesMenuFilters (item: CatalogItemProjection, section: CatalogSectionProjection | undefined, search: string) {
  if (search && !matches(item, section, search)) return false
  if (appliedFilterKeySet.value.size && !itemMatchesAnyFilter(item, section, appliedFilterKeys.value)) return false
  return true
}

function keywordLabelsForItem (item: CatalogItemProjection) {
  const itemName = normalizeSearchText(item.name)
  const itemCategory = normalizeSearchText(item.category || '')
  return Array.from(new Set([
    ...(item.tags || []),
    ...(item.search_terms || []),
    ...(item.allergens || []),
    ...(item.dietary_info || [])
  ].map(term => term.trim()).filter(term => {
    const normalized = normalizeSearchText(term)
    if (!normalized || normalized === itemName || normalized === itemCategory) return false
    if (term.length > 32 || /[,.]/.test(term)) return false
    return term.split(/\s+/).length <= 3
  })))
}

function filterKey (kind: SearchFilterKind, value: string) {
  return `${kind}:${value}`
}

function parseFilterKey (key: string): { kind: SearchFilterKind, value: string } | null {
  const [kind, ...rest] = key.split(':')
  if (!['collection', 'product', 'keyword'].includes(kind) || !rest.length) return null
  return { kind: kind as SearchFilterKind, value: rest.join(':') }
}

function itemMatchesFilter (item: CatalogItemProjection, section: CatalogSectionProjection | undefined, key: string) {
  const parsed = parseFilterKey(key)
  if (!parsed) return false
  if (parsed.kind === 'product') return item.sku === parsed.value
  if (parsed.kind === 'collection') return section?.ref === parsed.value
  return matchesProductAcrossCatalog(item, normalizeSearchText(parsed.value))
}

function itemMatchesAnyFilter (item: CatalogItemProjection, section: CatalogSectionProjection | undefined, keys: string[]) {
  if (!keys.length) return true
  return keys.some(key => itemMatchesFilter(item, section, key))
}

function productRoute (sku: string) {
  return `/product/${encodeURIComponent(sku)}`
}

function focusSearchInput () {
  if (!import.meta.client) return
  document.getElementById('menu-search')?.focus()
}

function openSearchPanel () {
  selectedFilterKeys.value = [...appliedFilterKeys.value]
  searchPanelOpen.value = true
  void nextTick(focusSearchInput)
}

function closeSearchPanel () {
  searchPanelOpen.value = false
  query.value = ''
  selectedFilterKeys.value = [...appliedFilterKeys.value]
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
  if (!import.meta.client) return false
  updatePillRailTailWidth()
  const pill = Array.from(document.querySelectorAll<HTMLElement>('[data-menu-pill-ref]'))
    .find(element => element.dataset.menuPillRef === ref)
  const rail = pill?.closest<HTMLElement>('[data-menu-pillrail]')
  if (!pill || !rail) return false
  const pillRect = pill.getBoundingClientRect()
  const railRect = rail.getBoundingClientRect()
  const left = rail.scrollLeft + (pillRect.left - railRect.left)
  const maxLeft = Math.max(0, rail.scrollWidth - rail.clientWidth)
  rail.scrollTo({
    left: Math.min(maxLeft, Math.max(0, left)),
    behavior
  })
  return true
}

function alignActiveSectionPill (ref: string, behavior?: ScrollBehavior) {
  const shouldAnimate = lastCenteredPillRef && lastCenteredPillRef !== ref
  const didCenter = centerSectionPill(ref, behavior || (shouldAnimate ? scrollBehavior() : 'auto'))
  if (didCenter) lastCenteredPillRef = ref
}

function scrollToSection (ref: string) {
  if (!import.meta.client) return
  const target = (ref === 'all' || ref === FILTERED_SECTION_VALUE)
    ? document.querySelector<HTMLElement>('[data-menu-results]')
    : document.getElementById(sectionDomId(ref))
  if (!target) return

  window.scrollTo({
    top: Math.max(0, target.getBoundingClientRect().top + window.scrollY - menuScrollOffset()),
    behavior: scrollBehavior()
  })
}

function selectSection (value: string | number | undefined) {
  const ref = String(value || 'all')
  if (ref === 'clear-filter') {
    clearMenuFilters()
    return
  }
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
  selectedFilterKeys.value = [...appliedFilterKeys.value]
  await nextTick()
  selectSection(ref)
}

function chooseSearchResult (sku: string) {
  searchPanelOpen.value = false
  query.value = ''
  selectedFilterKeys.value = [...appliedFilterKeys.value]
  return navigateTo(productRoute(sku))
}

function updateSearchListboxModel (value: string | string[] | undefined) {
  if (searchPanelOpen.value) {
    selectedFilterKeys.value = Array.isArray(value) ? value.map(String) : []
    return
  }
  if (value != null && !Array.isArray(value)) activeSection.value = String(value)
}

function chooseSearchOption (event: Event, option: SearchListOption) {
  event.preventDefault()
  if (option.kind === 'collection') {
    void chooseSectionFromSearch(option.value)
    return
  }
  if (option.kind === 'product') {
    void chooseSearchResult(option.value)
    return
  }
  applySingleFilter(option.key)
}

function isFilterKeySelected (key: string) {
  return selectedFilterKeySet.value.has(key)
}

function toggleFilterKey (key: string) {
  const next = new Set(selectedFilterKeys.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  selectedFilterKeys.value = Array.from(next)
}

function applySelectedMenuFilters () {
  if (!selectedFilterKeys.value.length) return
  appliedFilterKeys.value = [...selectedFilterKeys.value]
  activeSection.value = FILTERED_SECTION_VALUE
  searchPanelOpen.value = false
  query.value = ''
  void nextTick(() => {
    scrollToSection(FILTERED_SECTION_VALUE)
    queueActiveSectionSync()
  })
}

function applySingleFilter (key: string) {
  selectedFilterKeys.value = [key]
  applySelectedMenuFilters()
}

function clearMenuFilters () {
  selectedFilterKeys.value = []
  appliedFilterKeys.value = []
  activeSection.value = 'all'
  void nextTick(() => {
    scrollToSection('all')
    queueActiveSectionSync()
  })
}

let scrollRaf = 0
let programmaticScrollRef = ''
let programmaticScrollUntil = 0
let lastCenteredPillRef = ''

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
    alignActiveSectionPill('all')
    return
  }

  const offset = menuScrollOffset()
  const activationLine = offset + 48
  const lastSection = sectionEls[sectionEls.length - 1]
  const nearDocumentEnd = window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 8
  if (nearDocumentEnd && lastSection) {
    const current = lastSection.dataset.menuSectionRef || 'all'
    activeSection.value = current
    alignActiveSectionPill(current)
    return
  }

  if (sectionEls[0].getBoundingClientRect().top > activationLine) {
    const current = hasAppliedFilters.value ? FILTERED_SECTION_VALUE : 'all'
    activeSection.value = current
    alignActiveSectionPill(current)
    return
  }

  let current = sectionEls[0].dataset.menuSectionRef || 'all'
  for (const section of sectionEls) {
    if (section.getBoundingClientRect().top <= activationLine) {
      current = section.dataset.menuSectionRef || current
    }
  }
  activeSection.value = current
  alignActiveSectionPill(current)
}

function queueActiveSectionSync () {
  if (!import.meta.client || scrollRaf) return
  scrollRaf = window.requestAnimationFrame(() => {
    scrollRaf = 0
    syncActiveSectionFromScroll()
  })
}

watch(sectionOptions, options => {
  if (
    activeSection.value !== 'all' &&
    activeSection.value !== FILTERED_SECTION_VALUE &&
    !options.some(section => section.ref === activeSection.value)
  ) {
    activeSection.value = hasAppliedFilters.value ? FILTERED_SECTION_VALUE : 'all'
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
  description: () => catalog.value?.has_items ? `${uniqueItems.value.length} itens publicados.` : 'Cardápio publicado.'
})
</script>

<template>
  <main class="min-w-0">
    <h1 class="sr-only">Cardápio</h1>

    <section data-menu-filterbar class="sticky top-16 z-30 border-y bg-background shadow-sm">
      <div class="shop-container py-2">
        <div v-if="catalog" class="flex items-center gap-2">
          <UiButton
            variant="outline"
            size="icon"
            icon="lucide:search"
            aria-label="Buscar no cardápio"
            class="shrink-0 rounded-full"
            @click="searchPanelOpen ? closeSearchPanel() : openSearchPanel()"
          />
          <UiTabs v-model="activeSection" class="min-w-0 flex-1" @update:model-value="selectSection">
            <div data-menu-pillrail class="no-scrollbar overflow-x-auto scroll-smooth motion-reduce:scroll-auto">
              <UiTabsList :pill="false" class="gap-1 bg-transparent p-0">
                <UiTabsTrigger
                  v-if="hasAppliedFilters"
                  :value="FILTERED_SECTION_VALUE"
                  :data-menu-pill-ref="FILTERED_SECTION_VALUE"
                  :pill="false"
                  class="h-9 rounded-full border bg-background px-3 transition-colors duration-150 ease-out data-[state=active]:border-primary data-[state=active]:bg-primary data-[state=active]:text-primary-foreground data-[state=active]:shadow-none"
                >
                  <Icon name="lucide:funnel" class="mr-1 size-3.5" />
                  Filtrado
                  <span class="ml-1 text-xs tabular-nums opacity-70">{{ filteredCount }}</span>
                </UiTabsTrigger>
                <UiButton
                  v-if="hasAppliedFilters"
                  variant="outline"
                  size="sm"
                  icon="lucide:x"
                  class="h-9 shrink-0 rounded-full px-3"
                  data-menu-clear-filter-pill
                  @click="clearMenuFilters"
                >
                  Limpar filtro
                </UiButton>
                <UiTabsTrigger
                  value="all"
                  data-menu-pill-ref="all"
                  :pill="false"
                  class="h-9 rounded-full border bg-background px-3 transition-colors duration-150 ease-out data-[state=active]:border-primary data-[state=active]:bg-primary data-[state=active]:text-primary-foreground data-[state=active]:shadow-none"
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
                  class="h-9 rounded-full border bg-background px-3 transition-colors duration-150 ease-out data-[state=active]:border-primary data-[state=active]:bg-primary data-[state=active]:text-primary-foreground data-[state=active]:shadow-none"
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

        <div v-if="catalog && searchPanelOpen" class="pt-2">
          <UiLabel for="menu-search" class="sr-only">Buscar no cardápio</UiLabel>
          <UiListbox
            :model-value="selectedFilterKeys"
            multiple
            highlight-on-hover
            class="border-0 bg-transparent p-0 shadow-none"
            data-menu-search-listbox
            @update:model-value="updateSearchListboxModel"
          >
            <div class="flex items-center gap-2">
              <UiInputGroup class="min-w-0 flex-1">
                <UiInputGroupAddon>
                  <Icon name="lucide:search" class="size-4" />
                </UiInputGroupAddon>
                <UiListboxFilter v-model="query" as-child auto-focus>
                  <UiInput
                    id="menu-search"
                    type="search"
                    placeholder="Buscar no cardápio"
                    autocomplete="off"
                    class="flex-1 rounded-none border-0 bg-transparent shadow-none focus-visible:ring-0 dark:bg-transparent"
                  />
                </UiListboxFilter>
                <UiInputGroupAddon align="inline-end">
                  <UiInputGroupButton
                    size="icon-xs"
                    icon="lucide:x"
                    aria-label="Fechar busca"
                    @click="closeSearchPanel"
                  />
                </UiInputGroupAddon>
              </UiInputGroup>
              <UiButton
                v-if="hasPendingFilterSelection"
                size="sm"
                icon="lucide:funnel"
                class="shrink-0"
                @click="applySelectedMenuFilters"
              >
                Aplicar filtro
              </UiButton>
            </div>

            <UiListboxContent
              class="mt-2 rounded-lg border bg-background p-1"
              :data-menu-filter-result-list="normalizedQuery ? '' : undefined"
              :data-menu-collection-list="normalizedQuery ? undefined : ''"
            >
              <template v-if="searchResultGroups.length">
                <UiListboxGroup
                  v-for="group in searchResultGroups"
                  :key="group.ref"
                >
                  <UiListboxGroupLabel>{{ group.label }}</UiListboxGroupLabel>
                  <UiListboxItem
                    v-for="option in group.options"
                    :key="option.key"
                    :value="option.key"
                    class="px-2 py-2"
                    @select="chooseSearchOption($event, option)"
                  >
                    <UiItemMedia v-if="option.imageUrl" variant="image">
                      <img :src="option.imageUrl" :alt="option.label" loading="lazy">
                    </UiItemMedia>
                    <UiItemMedia v-else variant="icon">
                      <Icon :name="option.icon" />
                    </UiItemMedia>
                    <div class="min-w-0 flex-1">
                      <p class="truncate font-medium">{{ option.label }}</p>
                      <p class="truncate text-xs text-muted-foreground">{{ option.meta }}</p>
                    </div>
                    <UiButton
                      :variant="isFilterKeySelected(option.key) ? 'default' : 'outline'"
                      size="icon-sm"
                      icon="lucide:funnel"
                      :aria-label="isFilterKeySelected(option.key) ? `Remover ${option.label} do filtro` : `Filtrar por ${option.label}`"
                      :aria-pressed="isFilterKeySelected(option.key)"
                      class="ml-1 shrink-0 rounded-full"
                      @click.stop.prevent="toggleFilterKey(option.key)"
                    />
                  </UiListboxItem>
                </UiListboxGroup>
              </template>
              <UiItem v-else size="sm" class="border-0">
                <UiItemMedia variant="icon">
                  <Icon name="lucide:search-x" />
                </UiItemMedia>
                <UiItemContent>
                  <UiItemTitle>Nada encontrado</UiItemTitle>
                  <UiItemDescription>Apague a busca ou escolha uma coleção.</UiItemDescription>
                </UiItemContent>
              </UiItem>
            </UiListboxContent>
          </UiListbox>
        </div>

        <p class="sr-only" aria-live="polite">{{ menuFocusLabel }}</p>
      </div>
    </section>

    <div class="shop-section">
      <div class="shop-container space-y-5">
        <UiBreadcrumbs
          :items="[
            { label: 'Início', link: '/' },
            { label: 'Cardápio' }
          ]"
        />

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
          <UiAlert v-if="catalog.happy_hour?.active" variant="warning" icon="lucide:badge-percent">
            <UiAlertTitle>Happy hour ativo</UiAlertTitle>
            <UiAlertDescription>{{ catalog.happy_hour.discount_percent }}% de desconto aplicado no cardápio.</UiAlertDescription>
          </UiAlert>

          <section data-menu-results class="min-w-0 scroll-mt-40 space-y-4">
            <div v-if="activeSections.length" class="space-y-6">
              <div
                v-for="section in activeSections"
                :id="sectionDomId(section.ref)"
                :key="section.ref"
                :data-menu-section-ref="section.ref"
                class="scroll-mt-40 space-y-3"
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
    </div>
  </main>
</template>
