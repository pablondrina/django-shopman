<script setup lang="ts">
import {
  buildSectionsBySku,
  primarySectionBySku,
  searchPanelView,
  uniqueItemsBySku
} from '~/presentation/menu'
import type { MenuResponse } from '~/types/shopman'

// Overlay de busca na MESMA tela (sem navegar) — assim o foco/teclado funciona no iOS
// (foco dentro do gesto). A página /busca segue existindo como fallback (link direto).
const { open, registerInput, closeSearch } = useSearchOverlay()
const apiPath = useShopmanApiPath()
const route = useRoute()

// Carrega o cardápio sob demanda (na 1ª abertura) via $fetch — controle total de
// data/pending/error (useFetch com immediate:false+execute não atualizava aqui).
const data = ref<MenuResponse | null>(null)
const pending = ref(false)
const error = ref(false)
async function loadMenu () {
  if (data.value || pending.value) return
  pending.value = true
  error.value = false
  try {
    data.value = await $fetch<MenuResponse>(apiPath('/api/v1/storefront/menu/'), { credentials: 'include' })
  } catch {
    error.value = true
  } finally {
    pending.value = false
  }
}

const query = ref('')
// UiInput encaminha o id pro campo real; pegamos o elemento por id (o overlay está
// sempre no DOM, então o gatilho consegue focá-lo de forma síncrona, dentro do gesto).
function searchInputEl (): HTMLInputElement | null {
  return (document.getElementById('overlay-search-input') as HTMLInputElement | null)
}

onMounted(() => registerInput(searchInputEl()))
onBeforeUnmount(() => {
  registerInput(null)
  if (import.meta.client) {
    document.body.style.overflow = ''
    window.removeEventListener('keydown', onKeydown)
  }
})

function onKeydown (e: KeyboardEvent) { if (e.key === 'Escape') closeSearch() }

// Carrega o cardápio na 1ª abertura; trava o scroll do corpo; Esc fecha.
watch(open, (v) => {
  if (!import.meta.client) return
  if (v) void loadMenu()
  document.body.style.overflow = v ? 'hidden' : ''
  if (v) window.addEventListener('keydown', onKeydown)
  else window.removeEventListener('keydown', onKeydown)
})

// Fecha ao navegar (ex.: clicar num resultado).
watch(() => route.fullPath, () => { if (open.value) closeSearch() })

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
const resultItems = computed(() => panel.value.products.map(option => option.item).filter(item => item != null))

function goToSection (ref: string) {
  closeSearch()
  void navigateTo(`/menu?secao=${encodeURIComponent(ref)}`)
}
function clearQuery () {
  query.value = ''
  searchInputEl()?.focus()
}
</script>

<template>
  <Teleport to="body">
    <!-- Sempre no DOM; escondido por opacidade (não display:none) p/ o input continuar
         focável e o iOS abrir o teclado quando o gatilho foca dentro do gesto. -->
    <div
      class="fixed inset-0 z-50 flex flex-col bg-background transition-opacity duration-200"
      :class="open ? 'opacity-100' : 'pointer-events-none opacity-0'"
      :aria-hidden="!open"
      data-search-overlay
    >
      <div class="shop-searchbar shrink-0 shadow-sm">
        <div class="shop-container flex items-center gap-2 py-2">
          <UiButton
            variant="ghost"
            size="icon"
            icon="lucide:arrow-left"
            aria-label="Fechar busca"
            class="shrink-0 rounded-full"
            @click="closeSearch"
          />
          <UiInputGroup class="min-w-0 flex-1 rounded-full bg-white text-foreground">
            <UiInputGroupAddon>
              <Icon name="lucide:search" class="size-4" />
            </UiInputGroupAddon>
            <UiInput
              id="overlay-search-input"
              v-model="query"
              type="search"
              placeholder="Buscar no cardápio"
              autocomplete="off"
              class="min-w-0 flex-1 rounded-none border-0 bg-transparent shadow-none focus-visible:ring-0 dark:bg-transparent"
            />
            <UiInputGroupAddon v-if="query" align="inline-end">
              <UiInputGroupButton
                size="icon-xs"
                icon="lucide:x"
                aria-label="Limpar busca"
                @click="clearQuery"
              />
            </UiInputGroupAddon>
          </UiInputGroup>
        </div>
      </div>

      <div class="min-h-0 flex-1 overflow-y-auto">
        <div class="shop-container shop-stack-block pb-[calc(2rem+env(safe-area-inset-bottom,0px))] pt-4">
          <div v-if="pending" class="space-y-2">
            <UiSkeleton v-for="n in 6" :key="n" class="h-10 rounded-lg" />
          </div>

          <UiAlert v-else-if="error" variant="destructive">
            <UiAlertTitle>A busca tropeçou agora</UiAlertTitle>
            <UiAlertDescription>
              <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <span>Tente de novo em instantes.</span>
                <UiButton size="sm" variant="outline" @click="loadMenu()">Tentar de novo</UiButton>
              </div>
            </UiAlertDescription>
          </UiAlert>

          <template v-else>
            <div v-if="panel.collections.length" data-search-collections>
              <p class="shop-kicker">Coleções</p>
              <div class="mt-1">
                <UiButton
                  v-for="option in panel.collections"
                  :key="option.key"
                  variant="ghost"
                  class="shop-gold-hover h-auto w-full justify-start gap-3 rounded-none border-b px-1 py-3 font-normal last:border-b-0"
                  @click="goToSection(option.value)"
                >
                  <Icon :name="option.icon" class="size-4 text-muted-foreground" :class="option.icon === 'lucide:heart' ? 'text-foreground' : ''" />
                  <span class="min-w-0 flex-1 truncate text-left shop-body">{{ option.label }}</span>
                  <span class="shrink-0 shop-meta tabular-nums">{{ option.count }}</span>
                </UiButton>
              </div>
            </div>

            <div v-if="resultItems.length" data-search-results>
              <p class="shop-kicker">Produtos</p>
              <div class="mt-1 grid grid-cols-1 gap-x-8 md:grid-cols-2">
                <ProductListItem
                  v-for="item in resultItems"
                  :key="item!.sku"
                  :item="item!"
                  class="border-b"
                />
              </div>
            </div>

            <UiEmpty v-if="normalizedQuery && !resultItems.length" class="border">
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
      </div>
    </div>
  </Teleport>
</template>
