<script setup lang="ts">
import type { ProductDetailProjection, ProductResponse } from '~/types/shopman'

const route = useRoute()
const sku = computed(() => String(route.params.sku || ''))
const { setFromServer } = useCartState()
const { shop } = useShopSession()
const apiPath = useShopmanApiPath()
const requestUrl = useRequestURL()

definePageMeta({
  path: '/produto/:sku'
})

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
    items.push({
      label: product.value.breadcrumb_category.name,
      to: product.value.breadcrumb_category.url
    })
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

function hasAllergenInfo (p: ProductDetailProjection): boolean {
  return !!(
    p.allergen?.has_any ||
    p.allergen?.allergens?.length ||
    p.allergen?.dietary_info?.length ||
    p.allergen?.serves ||
    p.trace_notice
  )
}

function hasNutritionInfo (p: ProductDetailProjection): boolean {
  return !!(
    p.nutrition?.has_any ||
    p.nutrition?.serving_size_display ||
    p.nutrition?.servings_per_container ||
    p.nutrition?.energy_kcal_display ||
    p.nutrition?.rows?.length
  )
}

function hasConservationInfo (p: ProductDetailProjection): boolean {
  return !!(
    p.conservation?.has_any ||
    p.conservation?.shelf_life_label ||
    p.conservation?.storage_tip
  )
}

const detailAccordionItems = computed(() => {
  const p = product.value
  if (!p) return []
  return [
    p.components?.length ? { label: 'Composição', slot: 'components' } : null,
    p.ingredients_text ? { label: 'Ingredientes', slot: 'ingredients' } : null,
    (p.unit_weight_label || p.approx_dimensions_label) ? { label: 'Dimensões e peso', slot: 'dimensions' } : null,
    hasAllergenInfo(p) ? { label: 'Alérgenos e restrições', slot: 'allergens' } : null,
    hasNutritionInfo(p) ? { label: 'Tabela nutricional', slot: 'nutrition' } : null,
    hasConservationInfo(p) ? { label: 'Conservação', slot: 'conservation' } : null
  ].filter(Boolean)
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
      url: new URL(`/produto/${product.value.sku}`, requestUrl.origin).toString(),
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
    item: item.to ? new URL(item.to, requestUrl.origin).toString() : undefined
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
  <UContainer class="py-6 sm:py-10">
    <USkeleton v-if="pending" class="h-96 w-full" />

    <UAlert v-else-if="error || !product" color="error" variant="soft" title="Produto não encontrado" description="Verifique o endereço ou volte ao cardápio." />

    <div v-else>
      <UButton to="/menu" color="neutral" variant="ghost" label="Cardápio" class="mb-4 justify-start px-0 sm:hidden" />
      <UBreadcrumb :items="breadcrumbItems" class="mb-5 hidden min-w-0 sm:flex" />

      <div class="grid gap-7 lg:grid-cols-[minmax(0,1fr)_430px] lg:items-start">
        <div class="order-2 grid gap-4 lg:order-1">
          <section class="relative overflow-hidden rounded-lg border border-default bg-elevated">
            <div class="product-image aspect-[4/3] overflow-hidden sm:aspect-[16/11]">
              <img
                v-if="product.image_url"
                :src="product.image_url"
                :alt="product.name"
                loading="eager"
                fetchpriority="high"
                decoding="async"
                sizes="(min-width: 1024px) calc(100vw - 520px), 100vw"
                class="size-full object-cover"
              >
              <div v-else class="flex size-full items-center justify-center">
                <UIcon name="i-lucide-cookie" class="size-16 text-muted" />
              </div>
            </div>
          </section>

          <div v-if="product.gallery?.length" class="grid grid-cols-4 gap-2">
            <div
              v-for="(img, idx) in product.gallery"
              :key="idx"
              class="aspect-square overflow-hidden rounded-lg border border-default bg-elevated"
            >
              <img :src="img" :alt="`${product.name} ${idx + 1}`" loading="lazy" decoding="async" sizes="25vw" class="size-full object-cover">
            </div>
          </div>

          <section class="shop-soft-panel rounded-lg p-4 sm:p-5">
            <div class="grid gap-4 sm:grid-cols-3">
              <div class="border-l border-primary/50 pl-3">
                <div>
                  <p class="text-sm font-semibold text-highlighted">Disponibilidade da loja</p>
                  <p class="mt-1 text-sm leading-relaxed text-muted">Status informado pelo cardápio.</p>
                </div>
              </div>
              <div class="border-l border-primary/50 pl-3">
                <div>
                  <p class="text-sm font-semibold text-highlighted">Pedido acompanhado</p>
                  <p class="mt-1 text-sm leading-relaxed text-muted">Depois de enviar, use a página do pedido.</p>
                </div>
              </div>
              <div class="border-l border-primary/50 pl-3">
                <div>
                  <p class="text-sm font-semibold text-highlighted">Próxima ação clara</p>
                  <p class="mt-1 text-sm leading-relaxed text-muted">Se algo mudar, mostramos como continuar.</p>
                </div>
              </div>
            </div>
          </section>
        </div>

        <aside class="order-1 grid gap-4 lg:order-2 lg:sticky lg:top-[calc(var(--ui-header-height)+24px)]">
          <section class="rounded-lg border border-default bg-default p-4 shadow-sm sm:p-5">
            <div class="flex flex-wrap gap-2">
              <UBadge v-if="product.promotion_label" color="primary" variant="solid">{{ product.promotion_label }}</UBadge>
              <UBadge :color="availabilityColor" variant="subtle">{{ product.availability_label }}</UBadge>
              <UBadge v-if="product.is_bundle" color="neutral" variant="subtle">Combo</UBadge>
              <UBadge v-if="product.max_qty" color="neutral" variant="subtle">Limite {{ product.max_qty }}</UBadge>
            </div>

            <h1 class="mt-4 text-3xl font-bold leading-tight text-highlighted sm:text-4xl">
              {{ product.name }}
            </h1>
            <p v-if="product.short_description" class="mt-3 break-words text-base leading-relaxed text-muted sm:text-lg">
              {{ product.short_description }}
            </p>

            <div v-if="product.long_description" class="mt-4 rounded-lg border border-default bg-elevated/45 p-3 text-sm leading-relaxed text-muted">
              {{ product.long_description }}
            </div>

            <div class="mt-5 flex flex-col items-start gap-4 border-t border-default pt-5 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <div v-if="product.original_price_display" class="text-sm text-muted line-through">
                  {{ product.original_price_display }}
                </div>
                <div class="text-3xl font-bold tabular-nums text-highlighted sm:text-4xl">
                  {{ product.price_display }}
                </div>
                <div v-if="product.unit_weight_label" class="mt-1 text-sm text-muted">
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
                size="md"
              />
            </div>

            <UAlert
              v-if="product.availability === 'planned_ok'"
              color="info"
              variant="subtle"
              title="Encomenda antecipada"
              description="Este item depende de confirmação operacional antes de seguir no pedido."
              class="mt-5"
            />
          </section>

          <UAccordion
            v-if="detailAccordionItems.length"
            :items="detailAccordionItems"
            class="rounded-lg border border-default bg-elevated/45 p-1"
            :ui="{ trigger: 'px-4 py-3', content: 'px-4 pb-4 pt-1' }"
          >
            <template v-if="product.components?.length" #components>
              <div class="grid gap-2 rounded-md bg-default/55 p-3">
                <div
                  v-for="component in product.components"
                  :key="component.sku"
                  class="flex items-center justify-between gap-4 text-sm"
                >
                  <span class="min-w-0 truncate text-muted">{{ component.name }}</span>
                  <span class="shrink-0 font-medium tabular-nums">{{ component.qty_display }}</span>
                </div>
              </div>
            </template>
            <template v-if="product.ingredients_text" #ingredients>
              <div class="rounded-md bg-default/55 p-3">
                <p class="text-sm leading-relaxed text-muted">{{ product.ingredients_text }}</p>
              </div>
            </template>
            <template v-if="product.unit_weight_label || product.approx_dimensions_label" #dimensions>
              <dl class="grid gap-3 rounded-md bg-default/55 p-3 text-sm">
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
            <template v-if="hasAllergenInfo(product)" #allergens>
              <div class="grid gap-3 rounded-md bg-default/55 p-3 text-sm">
                <div v-if="product.allergen?.allergens?.length">
                  <p class="font-medium text-highlighted">Contém ou pode conter</p>
                  <div class="mt-2 flex flex-wrap gap-2">
                    <UBadge
                      v-for="allergen in product.allergen.allergens"
                      :key="allergen"
                      color="warning"
                      variant="subtle"
                    >
                      {{ allergen }}
                    </UBadge>
                  </div>
                </div>
                <div v-if="product.allergen?.dietary_info?.length">
                  <p class="font-medium text-highlighted">Perfil alimentar</p>
                  <div class="mt-2 flex flex-wrap gap-2">
                    <UBadge
                      v-for="diet in product.allergen.dietary_info"
                      :key="diet"
                      color="neutral"
                      variant="subtle"
                    >
                      {{ diet }}
                    </UBadge>
                  </div>
                </div>
                <p v-if="product.allergen?.serves" class="text-muted">
                  Serve: {{ product.allergen.serves }}
                </p>
                <p v-if="product.trace_notice" class="leading-relaxed text-muted">{{ product.trace_notice }}</p>
              </div>
            </template>
            <template v-if="hasNutritionInfo(product)" #nutrition>
              <div class="overflow-hidden rounded-md border border-default bg-default/55 text-sm">
                <div class="grid grid-cols-3 gap-3 border-b border-default px-3 py-2 font-medium text-highlighted">
                  <span>Informação</span>
                  <span class="text-right">Quantidade</span>
                  <span class="text-right">%VD</span>
                </div>
                <div v-if="product.nutrition.serving_size_display" class="grid grid-cols-3 gap-3 border-b border-default px-3 py-2">
                  <span class="text-muted">Porção</span>
                  <span class="text-right">{{ product.nutrition.serving_size_display }}</span>
                  <span />
                </div>
                <div v-if="product.nutrition.servings_per_container" class="grid grid-cols-3 gap-3 border-b border-default px-3 py-2">
                  <span class="text-muted">Porções por embalagem</span>
                  <span class="text-right">{{ product.nutrition.servings_per_container }}</span>
                  <span />
                </div>
                <div v-if="product.nutrition.energy_kcal_display" class="grid grid-cols-3 gap-3 border-b border-default px-3 py-2">
                  <span class="text-muted">Valor energético</span>
                  <span class="text-right">{{ product.nutrition.energy_kcal_display }} kcal</span>
                  <span class="text-right">{{ product.nutrition.energy_pdv ?? '—' }}</span>
                </div>
                <div
                  v-for="row in product.nutrition.rows"
                  :key="row.field"
                  class="grid grid-cols-3 gap-3 border-b border-default px-3 py-2 last:border-b-0"
                >
                  <span class="text-muted">{{ row.label }}</span>
                  <span class="text-right">{{ row.value_display }} {{ row.unit }}</span>
                  <span class="text-right">{{ row.percent_daily_value ?? '—' }}</span>
                </div>
              </div>
            </template>
            <template v-if="hasConservationInfo(product)" #conservation>
              <dl class="grid gap-3 rounded-md bg-default/55 p-3 text-sm">
                <div v-if="product.conservation.shelf_life_label" class="flex justify-between gap-4">
                  <dt class="text-muted">Validade</dt>
                  <dd class="font-medium text-right">{{ product.conservation.shelf_life_label }}</dd>
                </div>
                <div v-if="product.conservation.storage_tip" class="grid gap-1">
                  <dt class="text-muted">Armazenamento</dt>
                  <dd class="leading-relaxed">{{ product.conservation.storage_tip }}</dd>
                </div>
              </dl>
            </template>
          </UAccordion>

          <UButton to="/menu" color="neutral" variant="ghost" label="Voltar ao cardápio" class="justify-center" />
        </aside>
      </div>
    </div>
  </UContainer>
</template>
