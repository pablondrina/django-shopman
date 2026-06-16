<script setup lang="ts">
import {
  appliedFilterChips,
  buildSectionsBySku,
  primarySectionBySku,
  searchPanelView,
  uniqueItemsBySku
} from '~/presentation/menu'
import type { MenuResponse } from '~/types/shopman'

const apiPath = useShopmanApiPath()
const route = useRoute()
const router = useRouter()
const { setFromServer } = useCartState()
const { data, pending, error, refresh } = await useFetch<MenuResponse>(apiPath('/api/v1/storefront/menu/'), {
  credentials: 'include'
})

watch(() => data.value?.cart, cart => {
  setFromServer(cart)
}, { immediate: true })

function parseFilters (raw: unknown): string[] {
  return String(raw || '').split(',').map(part => part.trim()).filter(Boolean)
}

const query = ref('')
const baseFilters = ref<string[]>(parseFilters(route.query.filtro))

const catalog = computed(() => data.value?.catalog || null)
const sections = computed(() => catalog.value?.sections || [])
const uniqueItems = computed(() => uniqueItemsBySku(catalog.value?.items || []))
const favoriteRef = computed(() => catalog.value?.favorite_category_ref || '')
const normalizedQuery = computed(() => normalizeSearchText(query.value))
const sectionsBySku = computed(() => buildSectionsBySku(sections.value))
const sectionBySku = computed(() => primarySectionBySku(sectionsBySku.value))
const panel = computed(() => searchPanelView({
  sections: sections.value,
  items: uniqueItems.value,
  search: normalizedQuery.value,
  favoriteRef: favoriteRef.value,
  sectionBySku: sectionBySku.value,
  sectionsBySku: sectionsBySku.value
}))
const activeChips = computed(() => appliedFilterChips(baseFilters.value, sections.value))
const resultItems = computed(() => panel.value.products.map(option => option.item).filter(item => item != null))

function menuTargetFor (keys: string[]): string {
  return keys.length ? `/menu?filtro=${encodeURIComponent(keys.join(','))}` : '/menu'
}

function isFilterApplied (key: string) {
  return baseFilters.value.includes(key)
}

// Chip novo aplica e leva direto ao cardápio filtrado (efeito visível na
// hora); remover um chip ativo mantém a página, atualizando a URL.
function toggleChip (key: string) {
  if (isFilterApplied(key)) {
    baseFilters.value = baseFilters.value.filter(item => item !== key)
    void router.replace({ query: baseFilters.value.length ? { filtro: baseFilters.value.join(',') } : {} })
    return
  }
  void navigateTo(menuTargetFor([...baseFilters.value, key]))
}

function goToSection (ref: string) {
  void navigateTo(`/menu?secao=${encodeURIComponent(ref)}`)
}

onMounted(() => {
  document.getElementById('busca-input')?.focus()
})

useSeoMeta({
  title: 'Buscar'
})
// Canonical sem query → variantes ?q= não geram duplicate content.
useCanonical()
</script>

<template>
  <main class="min-w-0 pb-6">
    <div class="shop-searchbar sticky top-16 z-30 bg-background shadow-sm" data-busca-bar>
      <div class="shop-container flex items-center gap-2 py-2">
        <UiButton
          variant="ghost"
          size="icon"
          icon="lucide:arrow-left"
          aria-label="Voltar ao cardápio"
          class="shrink-0 rounded-full"
          :to="menuTargetFor(baseFilters)"
        />
        <UiInputGroup class="min-w-0 flex-1 rounded-full bg-white text-foreground">
          <UiInputGroupAddon>
            <Icon name="lucide:search" class="size-4" />
          </UiInputGroupAddon>
          <UiInput
            id="busca-input"
            v-model="query"
            type="search"
            placeholder="Buscar no cardápio"
            autocomplete="off"
            class="flex-1 rounded-none border-0 bg-transparent shadow-none focus-visible:ring-0 dark:bg-transparent"
          />
          <UiInputGroupAddon v-if="query" align="inline-end">
            <UiInputGroupButton
              size="icon-xs"
              icon="lucide:x"
              aria-label="Limpar busca"
              @click="query = ''"
            />
          </UiInputGroupAddon>
        </UiInputGroup>
      </div>
    </div>

    <div class="shop-container space-y-5 pt-4">
      <div v-if="pending" class="space-y-2">
        <UiSkeleton v-for="n in 6" :key="n" class="h-10 rounded-lg" />
      </div>

      <UiAlert v-else-if="error" variant="destructive">
        <UiAlertTitle>Busca indisponível</UiAlertTitle>
        <UiAlertDescription>
          <UiButton size="sm" variant="outline" @click="refresh">Atualizar</UiButton>
        </UiAlertDescription>
      </UiAlert>

      <template v-else>
        <div v-if="activeChips.length && !normalizedQuery" data-busca-active-filters>
          <p class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Filtros ativos</p>
          <div class="mt-2 flex flex-wrap gap-1.5">
            <UiButton
              v-for="chip in activeChips"
              :key="chip.key"
              variant="default"
              size="sm"
              class="h-8 rounded-full px-3"
              :aria-label="`Remover filtro ${chip.label}`"
              @click="toggleChip(chip.key)"
            >
              {{ chip.label }}
              <Icon name="lucide:x" class="ml-1 size-3.5" />
            </UiButton>
          </div>
          <UiButton variant="outline" size="sm" class="mt-3 h-8 rounded-full px-3" :to="menuTargetFor(baseFilters)">
            Ver resultados no cardápio
          </UiButton>
        </div>

        <div v-if="panel.collections.length" data-busca-collections>
          <p class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Coleções</p>
          <div class="mt-1">
            <UiButton
              v-for="option in panel.collections"
              :key="option.key"
              variant="ghost"
              class="shop-gold-hover h-auto w-full justify-start gap-3 rounded-none border-b px-1 py-2.5 font-normal last:border-b-0"
              @click="goToSection(option.value)"
            >
              <Icon :name="option.icon" class="size-4 text-muted-foreground" :class="option.icon === 'lucide:heart' ? 'text-foreground' : ''" />
              <span class="min-w-0 flex-1 truncate text-left text-sm">{{ option.label }}</span>
              <span class="shrink-0 text-xs tabular-nums text-muted-foreground">{{ option.count }}</span>
            </UiButton>
          </div>
        </div>

        <div v-if="panel.chips.length" data-busca-filter-chips>
          <p class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Filtre por</p>
          <div class="mt-2 flex flex-wrap gap-1.5">
            <UiButton
              v-for="chip in panel.chips"
              :key="chip.key"
              :variant="isFilterApplied(chip.key) ? 'default' : 'outline'"
              size="sm"
              class="h-8 rounded-full px-3"
              :aria-pressed="isFilterApplied(chip.key)"
              @click="toggleChip(chip.key)"
            >
              <Icon v-if="chip.icon === 'lucide:heart'" name="lucide:heart" class="mr-1 size-3.5" />
              {{ chip.label }}
              <span v-if="chip.count != null" class="ml-1 text-xs tabular-nums opacity-60">{{ chip.count }}</span>
            </UiButton>
          </div>
        </div>

        <div v-if="resultItems.length" data-busca-results>
          <p class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Produtos</p>
          <div class="mt-1 grid grid-cols-1 gap-x-8 md:grid-cols-2">
            <ProductListItem
              v-for="item in resultItems"
              :key="item!.sku"
              :item="item!"
              class="border-b"
            />
          </div>
        </div>

        <UiEmpty v-if="normalizedQuery && !panel.chips.length && !resultItems.length" class="border">
          <UiEmptyMedia variant="icon">
            <Icon name="lucide:search-x" />
          </UiEmptyMedia>
          <UiEmptyHeader>
            <UiEmptyTitle>Nada encontrado</UiEmptyTitle>
            <UiEmptyDescription>Apague a busca ou escolha uma coleção.</UiEmptyDescription>
          </UiEmptyHeader>
        </UiEmpty>
      </template>
    </div>
  </main>
</template>
