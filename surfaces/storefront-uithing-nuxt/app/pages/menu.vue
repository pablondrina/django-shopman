<script setup lang="ts">
import {
  FILTERED_SECTION_VALUE,
  appliedFilterChips,
  buildSectionsBySku,
  filteredSections,
  primarySectionBySku,
  searchPanelView,
  uniqueItemsBySku
} from '~/presentation/menu'
import type { MenuResponse } from '~/types/shopman'

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
const appliedFilterKeys = ref<string[]>([])

const catalog = computed(() => data.value?.catalog || null)
const sections = computed(() => catalog.value?.sections || [])
const allItems = computed(() => catalog.value?.items || [])
const uniqueItems = computed(() => uniqueItemsBySku(allItems.value))
const favoriteRef = computed(() => catalog.value?.favorite_category_ref || '')
const normalizedQuery = computed(() => normalizeSearchText(query.value))
const appliedFilterKeySet = computed(() => new Set(appliedFilterKeys.value))
const hasAppliedFilters = computed(() => appliedFilterKeys.value.length > 0)
const sectionsBySku = computed(() => buildSectionsBySku(sections.value))
const sectionBySku = computed(() => primarySectionBySku(sectionsBySku.value))
const searchOrFilterMode = computed(() => Boolean(normalizedQuery.value || hasAppliedFilters.value))
const activeSections = computed(() => filteredSections(
  sections.value,
  normalizedQuery.value,
  appliedFilterKeys.value,
  sectionsBySku.value
))

const filteredCount = computed(() => uniqueItemsBySku(activeSections.value.flatMap(section => [...section.items])).length)
const sectionOptions = computed(() => {
  const source = searchOrFilterMode.value ? activeSections.value : sections.value
  return source.map(section => ({
    ref: section.ref,
    label: section.label,
    count: uniqueItemsBySku([...section.items]).length,
    isFavorite: !!favoriteRef.value && [section.ref, section.category?.ref, section.dynamic_ref].includes(favoriteRef.value)
  }))
})
const activeSectionLabel = computed(() => {
  if (activeSection.value === 'all') return 'Tudo'
  if (activeSection.value === FILTERED_SECTION_VALUE) return 'Filtrado'
  return sections.value.find(section => section.ref === activeSection.value)?.label || 'Seção'
})
const activeSectionCount = computed(() => {
  if (activeSection.value === 'all' || activeSection.value === FILTERED_SECTION_VALUE) return filteredCount.value
  return sectionOptions.value.find(section => section.ref === activeSection.value)?.count || 0
})
const activeFilterChips = computed(() => appliedFilterChips(appliedFilterKeys.value, sections.value))
const searchPanel = computed(() => searchPanelView({
  sections: sections.value,
  items: uniqueItems.value,
  search: normalizedQuery.value,
  favoriteRef: favoriteRef.value,
  sectionBySku: sectionBySku.value,
  sectionsBySku: sectionsBySku.value
}))
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
  if (searchPanelOpen.value) closeSearchPanel()
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

async function goToSectionFromSearch (ref: string) {
  closeSearchPanel()
  await nextTick()
  selectSection(ref)
}

function isFilterApplied (key: string) {
  return appliedFilterKeySet.value.has(key)
}

// Aplicar um chip fecha a busca e leva direto ao resultado filtrado —
// o efeito do toque precisa ser visível na hora. Remover um chip mantém
// o painel como está (o usuário está compondo/desempilhando).
function toggleMenuFilter (key: string) {
  const next = new Set(appliedFilterKeys.value)
  const isAdding = !next.has(key)
  if (isAdding) next.add(key)
  else next.delete(key)
  appliedFilterKeys.value = Array.from(next)
  activeSection.value = appliedFilterKeys.value.length ? FILTERED_SECTION_VALUE : 'all'
  if (isAdding) {
    closeSearchPanel()
    void nextTick(() => {
      scrollToSection(FILTERED_SECTION_VALUE)
      queueActiveSectionSync()
    })
    return
  }
  void nextTick(queueActiveSectionSync)
}

function clearMenuFilters () {
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

    <section data-menu-filterbar class="sticky top-14 z-30 border-y bg-background shadow-sm md:top-16">
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
                  <span v-if="searchOrFilterMode" class="ml-1 text-xs tabular-nums opacity-70">{{ filteredCount }}</span>
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
                  <span v-if="searchOrFilterMode" class="ml-1 text-xs tabular-nums opacity-70">{{ section.count }}</span>
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

        <div v-if="catalog && searchPanelOpen" class="pt-2" data-menu-search-panel>
          <UiLabel for="menu-search" class="sr-only">Buscar no cardápio</UiLabel>
          <UiInputGroup class="min-w-0">
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

          <div v-if="activeFilterChips.length && !normalizedQuery" class="mt-3" data-menu-active-filters>
            <p class="text-xs font-medium uppercase tracking-wide text-muted-foreground">Filtros ativos</p>
            <div class="mt-2 flex flex-wrap gap-1.5">
              <UiButton
                v-for="chip in activeFilterChips"
                :key="chip.key"
                variant="default"
                size="sm"
                class="h-8 rounded-full px-3"
                :aria-label="`Remover filtro ${chip.label}`"
                @click="toggleMenuFilter(chip.key)"
              >
                {{ chip.label }}
                <Icon name="lucide:x" class="ml-1 size-3.5" />
              </UiButton>
            </div>
          </div>

          <div v-if="searchPanel.collections.length" class="mt-3" data-menu-collection-list>
            <p class="text-xs font-medium uppercase tracking-wide text-muted-foreground">Coleções</p>
            <div class="mt-1">
              <UiButton
                v-for="option in searchPanel.collections"
                :key="option.key"
                variant="ghost"
                class="h-auto w-full justify-start gap-3 rounded-none border-b px-1 py-2.5 font-normal last:border-b-0"
                @click="goToSectionFromSearch(option.value)"
              >
                <Icon :name="option.icon" class="size-4 text-muted-foreground" :class="option.icon === 'lucide:heart' ? 'text-foreground' : ''" />
                <span class="min-w-0 flex-1 truncate text-left text-sm font-medium">{{ option.label }}</span>
                <span class="shrink-0 text-xs tabular-nums text-muted-foreground">{{ option.count }}</span>
              </UiButton>
            </div>
          </div>

          <div v-if="searchPanel.chips.length" class="mt-3" data-menu-filter-chips>
            <p class="text-xs font-medium uppercase tracking-wide text-muted-foreground">Filtre por</p>
            <div class="mt-2 flex flex-wrap gap-1.5">
              <UiButton
                v-for="chip in searchPanel.chips"
                :key="chip.key"
                :variant="isFilterApplied(chip.key) ? 'default' : 'outline'"
                size="sm"
                class="h-8 rounded-full px-3"
                :aria-pressed="isFilterApplied(chip.key)"
                @click="toggleMenuFilter(chip.key)"
              >
                <Icon v-if="chip.icon === 'lucide:heart'" name="lucide:heart" class="mr-1 size-3.5" />
                {{ chip.label }}
                <span v-if="chip.count != null" class="ml-1 text-xs tabular-nums opacity-60">{{ chip.count }}</span>
              </UiButton>
            </div>
          </div>

          <div v-if="searchPanel.products.length" class="mt-4" data-menu-product-results>
            <p class="text-xs font-medium uppercase tracking-wide text-muted-foreground">Vá direto</p>
            <div class="mt-1">
              <NuxtLink
                v-for="option in searchPanel.products"
                :key="option.key"
                :to="productRoute(option.value)"
                class="flex items-center gap-3 border-b py-2 last:border-b-0"
              >
                <div class="size-10 shrink-0 overflow-hidden rounded-lg bg-muted">
                  <img v-if="option.imageUrl" :src="option.imageUrl" :alt="option.label" loading="lazy" class="size-full object-cover">
                  <div v-else class="flex size-full items-center justify-center text-muted-foreground">
                    <Icon name="lucide:croissant" class="size-4" />
                  </div>
                </div>
                <span class="min-w-0 flex-1 truncate text-sm font-medium">{{ option.label }}</span>
                <span class="shrink-0 text-sm font-semibold tabular-nums">{{ option.meta }}</span>
              </NuxtLink>
            </div>
          </div>

          <UiItem v-if="normalizedQuery && !searchPanel.chips.length && !searchPanel.products.length" size="sm" class="mt-3 border-0">
            <UiItemMedia variant="icon">
              <Icon name="lucide:search-x" />
            </UiItemMedia>
            <UiItemContent>
              <UiItemTitle>Nada encontrado</UiItemTitle>
              <UiItemDescription>Apague a busca ou escolha uma coleção.</UiItemDescription>
            </UiItemContent>
          </UiItem>
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

        <div v-if="pending" class="grid grid-cols-1 gap-x-8 md:grid-cols-2 xl:grid-cols-3">
          <div v-for="n in 6" :key="n" class="flex gap-3 border-b py-3">
            <div class="min-w-0 flex-1 space-y-2 self-center">
              <UiSkeleton class="h-4 w-3/4" />
              <UiSkeleton class="h-3 w-full" />
              <UiSkeleton class="h-4 w-1/4" />
            </div>
            <UiSkeleton class="size-28 shrink-0 rounded-lg" />
          </div>
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
            <div v-if="activeSections.length" class="space-y-7">
              <div
                v-for="section in activeSections"
                :id="sectionDomId(section.ref)"
                :key="section.ref"
                :data-menu-section-ref="section.ref"
                class="scroll-mt-40 space-y-1"
              >
                <div class="space-y-0.5">
                  <h2 class="text-base font-semibold">{{ section.label }}</h2>
                  <p v-if="section.description" class="text-sm text-muted-foreground">{{ section.description }}</p>
                </div>
                <div class="grid grid-cols-1 gap-x-8 md:grid-cols-2 xl:grid-cols-3">
                  <ProductListItem
                    v-for="item in section.items"
                    :key="`${section.ref}-${item.sku}`"
                    :item="item"
                    class="border-b"
                  />
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
