<script setup lang="ts">
import type { ProductResponse } from '~/types/shopman'

const route = useRoute()
const sku = computed(() => String(route.params.sku || ''))
const { setFromServer } = useCartState()
const { shop } = useShopSession()
const apiPath = useShopmanApiPath()

const { data, pending, error, refresh } = await useFetch<ProductResponse>(
  () => apiPath(`/api/v1/storefront/products/${encodeURIComponent(sku.value)}/`),
  { credentials: 'include' }
)

watchEffect(() => setFromServer(data.value?.cart))

if (import.meta.client) {
  let pollTimer: ReturnType<typeof setInterval> | null = null
  let eventSource: EventSource | null = null

  function startPolling () {
    stopPolling()
    pollTimer = setInterval(() => { refresh() }, 30_000)
  }
  function stopPolling () {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  function startSse () {
    stopSse()
    try {
      const url = apiPath('/storefront/stock/events/storefront/')
      eventSource = new EventSource(url, { withCredentials: true })
      eventSource.addEventListener('message', () => { refresh() })
      eventSource.addEventListener('stock-update', () => { refresh() })
      eventSource.addEventListener('error', () => {
        // SSE may close in dev/preview; polling continues as a fallback
      })
    } catch {
      // EventSource not supported or blocked — polling fallback handles it
    }
  }
  function stopSse () {
    if (eventSource) {
      eventSource.close()
      eventSource = null
    }
  }

  onMounted(() => {
    startPolling()
    startSse()
  })
  onBeforeUnmount(() => {
    stopPolling()
    stopSse()
  })
}

const product = computed(() => data.value?.product)
const meta = computed(() => product.value
  ? { sku: product.value.sku, name: product.value.name, price_q: product.value.base_price_q, price_display: product.value.price_display, image_url: product.value.image_url }
  : null)

const breadcrumbItems = computed(() => {
  const items: Array<{ label: string, to?: string }> = [
    { label: 'Início', to: '/' },
    { label: 'Cardápio', to: '/menu' }
  ]
  if (product.value?.breadcrumb_category) {
    items.push({ label: product.value.breadcrumb_category.name, to: product.value.breadcrumb_category.url || '/menu' })
  }
  if (product.value) {
    items.push({ label: product.value.name })
  }
  return items
})

const availabilityColor = computed(() => {
  switch (product.value?.availability) {
    case 'available': return 'success'
    case 'low_stock': return 'warning'
    case 'planned_ok': return 'info'
    case 'unavailable': return 'error'
    default: return 'neutral'
  }
})

useHead(() => ({
  title: product.value?.name || 'Produto'
}))

useSeoMeta({
  title: () => product.value?.name || 'Produto',
  description: () => product.value?.seo_description || product.value?.short_description || '',
  keywords: () => product.value?.seo_keywords?.join(', ') || '',
  ogTitle: () => product.value?.name || 'Produto',
  ogDescription: () => product.value?.seo_description || product.value?.short_description || '',
  ogImage: () => product.value?.image_url || '',
  ogType: 'website',
  twitterCard: 'summary_large_image'
})

const jsonLd = computed(() => {
  if (!product.value) return null
  const brandName = shop.value?.brand_name || 'Shopman'
  return {
    '@context': 'https://schema.org',
    '@type': 'Product',
    name: product.value.name,
    description: product.value.long_description || product.value.short_description,
    image: product.value.image_url ? [product.value.image_url] : [],
    sku: product.value.sku,
    brand: { '@type': 'Brand', name: brandName },
    offers: {
      '@type': 'Offer',
      priceCurrency: 'BRL',
      price: (product.value.base_price_q / 100).toFixed(2),
      availability: product.value.availability === 'unavailable'
        ? 'https://schema.org/OutOfStock'
        : 'https://schema.org/InStock'
    }
  }
})

const breadcrumbJsonLd = computed(() => ({
  '@context': 'https://schema.org',
  '@type': 'BreadcrumbList',
  itemListElement: breadcrumbItems.value.map((item, idx) => ({
    '@type': 'ListItem',
    position: idx + 1,
    name: item.label,
    item: item.to ? `${typeof window !== 'undefined' ? window.location.origin : ''}${item.to}` : undefined
  }))
}))

useHead(() => ({
  script: [
    jsonLd.value
      ? { type: 'application/ld+json', innerHTML: JSON.stringify(jsonLd.value) }
      : {},
    breadcrumbJsonLd.value
      ? { type: 'application/ld+json', innerHTML: JSON.stringify(breadcrumbJsonLd.value) }
      : {}
  ].filter(s => Object.keys(s).length > 0)
}))
</script>

<template>
  <UContainer class="py-8 sm:py-12">
    <USkeleton v-if="pending" class="h-96 w-full" />

    <UAlert v-else-if="error || !product" color="error" variant="soft" title="Produto não encontrado" description="Verifique o endereço ou volte ao cardápio." />

    <div v-else>
      <UBreadcrumb :items="breadcrumbItems" class="mb-6" />

      <div class="grid lg:grid-cols-2 gap-8 lg:gap-12 items-start">
        <div class="grid gap-3">
          <div class="overflow-hidden rounded-xl bg-elevated aspect-4/3 relative">
            <img v-if="product.image_url" :src="product.image_url" :alt="product.name" class="size-full object-cover">
            <div v-else class="flex items-center justify-center size-full">
              <UIcon name="i-lucide-cookie" class="size-16 text-muted" />
            </div>
            <UBadge
              v-if="product.promotion_label"
              color="primary"
              variant="solid"
              class="absolute top-4 left-4"
            >
              {{ product.promotion_label }}
            </UBadge>
          </div>

          <div v-if="product.gallery?.length" class="grid grid-cols-4 gap-2">
            <div
              v-for="(img, idx) in product.gallery"
              :key="idx"
              class="aspect-square overflow-hidden rounded-md bg-elevated"
            >
              <img :src="img" :alt="`${product.name} ${idx + 1}`" class="size-full object-cover">
            </div>
          </div>
        </div>

        <div class="grid gap-6">
          <div>
            <UBadge
              :color="availabilityColor"
              variant="subtle"
              size="md"
              class="mb-3"
            >
              {{ product.availability_label }}
            </UBadge>

            <h1 class="text-3xl sm:text-4xl font-bold tracking-tight text-highlighted leading-tight">
              {{ product.name }}
            </h1>
            <p v-if="product.short_description" class="mt-3 text-lg text-muted leading-relaxed">
              {{ product.short_description }}
            </p>
          </div>

          <UCard variant="outline" :ui="{ body: 'p-5' }">
            <div class="flex items-end justify-between gap-4">
              <div>
                <div v-if="product.original_price_display" class="text-sm text-muted line-through">
                  {{ product.original_price_display }}
                </div>
                <div class="text-3xl sm:text-4xl font-bold tabular-nums text-highlighted">
                  {{ product.price_display }}
                </div>
                <div v-if="product.unit_weight_label" class="text-sm text-muted mt-1">
                  Peso aproximado: {{ product.unit_weight_label }}
                </div>
              </div>

              <ProductStepper
                v-if="meta"
                :meta="meta"
                :can-add="product.can_add_to_cart"
                :max-qty="product.available_qty"
                add-label="Adicionar"
                :unavailable-label="product.availability_label"
                size="lg"
              />
            </div>
          </UCard>

          <div v-if="product.long_description" class="prose prose-sm max-w-none text-muted leading-relaxed">
            <p>{{ product.long_description }}</p>
          </div>

          <UAccordion
            v-if="product.ingredients_text || product.unit_weight_label || product.approx_dimensions_label || product.trace_notice"
            :items="[
              product.ingredients_text ? { label: 'Ingredientes', icon: 'i-lucide-list', slot: 'ingredients' } : null,
              (product.unit_weight_label || product.approx_dimensions_label) ? { label: 'Dimensões e peso', icon: 'i-lucide-scale', slot: 'dimensions' } : null,
              product.trace_notice ? { label: 'Informações sobre alérgenos', icon: 'i-lucide-shield-alert', slot: 'allergens' } : null
            ].filter(Boolean)"
          >
            <template v-if="product.ingredients_text" #ingredients>
              <p class="text-sm leading-relaxed text-muted">{{ product.ingredients_text }}</p>
            </template>
            <template v-if="product.unit_weight_label || product.approx_dimensions_label" #dimensions>
              <dl class="grid gap-3 text-sm">
                <div v-if="product.unit_weight_label" class="flex justify-between gap-4">
                  <dt class="text-muted">Peso</dt>
                  <dd class="font-medium">{{ product.unit_weight_label }}</dd>
                </div>
                <div v-if="product.approx_dimensions_label" class="flex justify-between gap-4">
                  <dt class="text-muted">Dimensões</dt>
                  <dd class="font-medium">{{ product.approx_dimensions_label }}</dd>
                </div>
              </dl>
            </template>
            <template v-if="product.trace_notice" #allergens>
              <p class="text-sm leading-relaxed text-muted">{{ product.trace_notice }}</p>
            </template>
          </UAccordion>

          <UAlert
            v-if="product.availability === 'planned_ok'"
            icon="i-lucide-clock"
            color="info"
            variant="subtle"
            title="Encomenda antecipada"
            description="A casa prepara este item especialmente para você. A confirmação só é cobrada depois."
          />
        </div>
      </div>
    </div>
  </UContainer>
</template>
