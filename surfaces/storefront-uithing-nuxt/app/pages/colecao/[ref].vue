<script setup lang="ts">
import { breadcrumbJsonLd, collectionJsonLd } from '~/presentation/seo'
import type { MenuResponse } from '~/types/shopman'

// Página de coleção indexável (rota própria, self-canonical) — diferente das
// variantes de filtro do /menu (que canonicalizam para /menu). Alimentada pelo
// endpoint Django de menu filtrado por coleção (build_catalog com collection_ref).
const route = useRoute()
const apiPath = useShopmanApiPath()
const requestUrl = useRequestURL()
const { setFromServer } = useCartState()

const collectionRef = computed(() => String(route.params.ref || ''))

const { data, pending, error, refresh } = await useFetch<MenuResponse>(
  () => apiPath(`/api/v1/storefront/menu/${encodeURIComponent(collectionRef.value)}/`),
  { credentials: 'include' }
)

// Coleção inexistente: 404 de verdade — o endpoint levanta Http404 via
// ensure_active_collection(); a SSR responde 404 + noindex (error.vue).
if (error.value?.statusCode === 404) {
  throw createError({ statusCode: 404, statusMessage: 'Coleção não encontrada', fatal: true })
}

watch(() => data.value?.cart, cart => {
  setFromServer(cart)
}, { immediate: true })

const catalog = computed(() => data.value?.catalog || null)
const section = computed(() => {
  const sections = catalog.value?.sections || []
  return sections.find(s => s.ref === collectionRef.value) || sections[0] || null
})
const items = computed(() => section.value?.items || catalog.value?.items || [])
const title = computed(() => section.value?.label || 'Coleção')
const description = computed(() => section.value?.description || '')

const canonicalUrl = computed(() => `${requestUrl.origin}${route.path}`)
const pageDescription = computed(() => description.value
  || (items.value.length ? `${items.value.length} itens em ${title.value}.` : title.value))

useSeoMeta({
  title: () => title.value,
  description: () => pageDescription.value,
  ogTitle: () => title.value,
  ogDescription: () => pageDescription.value,
  ogUrl: () => canonicalUrl.value
})
useCanonical()

// JSON-LD CollectionPage (ItemList) + BreadcrumbList — a coleção para o Google.
useHead({
  script: () => catalog.value && items.value.length
    ? [
        {
          type: 'application/ld+json',
          innerHTML: JSON.stringify(collectionJsonLd({
            name: title.value,
            url: canonicalUrl.value,
            origin: requestUrl.origin,
            items: items.value
          }))
        },
        {
          type: 'application/ld+json',
          innerHTML: JSON.stringify(breadcrumbJsonLd([
            { name: 'Início', url: `${requestUrl.origin}/` },
            { name: 'Cardápio', url: `${requestUrl.origin}/menu` },
            { name: title.value, url: canonicalUrl.value }
          ]))
        }
      ]
    : []
})
</script>

<template>
  <main class="min-w-0">
    <div class="shop-section">
      <div class="shop-container shop-stack-block">
        <nav aria-label="Trilha de navegação" class="shop-meta">
          <NuxtLink to="/menu" class="hover:underline">Cardápio</NuxtLink>
          <span aria-hidden="true"> / </span>
          <span class="text-foreground">{{ title }}</span>
        </nav>

        <div class="shop-stack-micro">
          <h1 class="shop-title">{{ title }}</h1>
          <p v-if="description" class="shop-muted">{{ description }}</p>
        </div>

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
          <UiAlertTitle>A coleção não quis abrir agora</UiAlertTitle>
          <UiAlertDescription>
            <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <span>Foi só um tropeço. Tente de novo em instantes.</span>
              <UiButton size="sm" variant="outline" @click="refresh">Tentar de novo</UiButton>
            </div>
          </UiAlertDescription>
        </UiAlert>

        <div v-else-if="items.length" class="grid grid-cols-1 gap-x-8 md:grid-cols-2 xl:grid-cols-3">
          <ProductListItem
            v-for="item in items"
            :key="item.sku"
            :item="item"
            framed
            class="border-b"
          />
        </div>

        <UiEmpty v-else class="border">
          <UiEmptyMedia variant="icon">
            <Icon name="lucide:croissant" />
          </UiEmptyMedia>
          <UiEmptyHeader>
            <UiEmptyTitle>Coleção em preparo</UiEmptyTitle>
            <UiEmptyDescription>
              Em breve novidades por aqui. Veja o
              <NuxtLink to="/menu" class="underline">cardápio completo</NuxtLink>.
            </UiEmptyDescription>
          </UiEmptyHeader>
        </UiEmpty>
      </div>
    </div>
  </main>
</template>
