<script setup lang="ts">
import { tileBadge } from '~/presentation/menu'
import { crossSellItems, detailDescription, nutritionTable } from '~/presentation/product'
import { absoluteImage, breadcrumbJsonLd, metaDescription, priceFromQ, productJsonLd } from '~/presentation/seo'
import type { ProductMutationMeta, ProductResponse } from '~/types/shopman'

const route = useRoute()
const apiPath = useShopmanApiPath()
const requestUrl = useRequestURL()
const session = useShopSession()
const sku = computed(() => String(route.params.sku || ''))
const { setFromServer, qtyForSku } = useCartState()

const { data, pending, error, refresh } = await useFetch<ProductResponse>(
  () => apiPath(`/api/v1/storefront/products/${encodeURIComponent(sku.value)}/`),
  { credentials: 'include' }
)

// SKU inexistente: 404 de verdade (SSR responde 404 + noindex via error.vue),
// não uma página-fantasma 200 indexável. Falhas de rede seguem no retry inline.
if (error.value?.statusCode === 404) {
  throw createError({ statusCode: 404, statusMessage: 'Produto não encontrado', fatal: true })
}

watch(() => data.value?.cart, cart => {
  setFromServer(cart)
}, { immediate: true })

const product = computed(() => data.value?.product || null)
const meta = computed<ProductMutationMeta | null>(() => product.value
  ? {
      sku: product.value.sku,
      name: product.value.name,
      price_q: product.value.base_price_q,
      price_display: product.value.price_display,
      image_url: product.value.image_url
    }
  : null)
const currentQty = computed(() => product.value ? qtyForSku(product.value.sku) : 0)
const badge = computed(() => product.value ? tileBadge(product.value) : null)
const longDescription = computed(() => product.value ? detailDescription(product.value) : '')
const nutrition = computed(() => nutritionTable(product.value?.nutrition || null))
const crossSell = computed(() => product.value ? crossSellItems(product.value) : [])

const canonicalUrl = computed(() => `${requestUrl.origin}${route.path}`)
const ogImage = computed(() => absoluteImage(requestUrl.origin, product.value?.image_url))
const pageDescription = computed(() => metaDescription(product.value) || 'Produto')

useSeoMeta({
  title: () => product.value?.name || 'Produto',
  description: () => pageDescription.value,
  ogTitle: () => product.value?.name || 'Produto',
  ogDescription: () => pageDescription.value,
  ogUrl: () => canonicalUrl.value,
  ogImage: () => ogImage.value || undefined,
  twitterCard: 'summary_large_image',
  twitterTitle: () => product.value?.name || 'Produto',
  twitterDescription: () => pageDescription.value,
  twitterImage: () => ogImage.value || undefined
})

// og:type=product + product:price (cards do WhatsApp/Facebook) e canonical —
// via meta crua (TS-safe). JSON-LD Product/Offer + BreadcrumbList p/ rich results.
useHead({
  link: [{ rel: 'canonical', href: () => canonicalUrl.value }],
  meta: [
    { property: 'og:type', content: 'product' },
    { property: 'product:price:amount', content: () => priceFromQ(product.value?.base_price_q) },
    { property: 'product:price:currency', content: 'BRL' }
  ],
  script: () => product.value
    ? [
        {
          type: 'application/ld+json',
          innerHTML: JSON.stringify(productJsonLd({
            product: product.value,
            origin: requestUrl.origin,
            url: canonicalUrl.value,
            brandName: session.shop.value?.brand_name || ''
          }))
        },
        {
          type: 'application/ld+json',
          innerHTML: JSON.stringify(breadcrumbJsonLd([
            { name: 'Início', url: `${requestUrl.origin}/` },
            { name: 'Cardápio', url: `${requestUrl.origin}/menu` },
            { name: product.value.name, url: canonicalUrl.value }
          ]))
        }
      ]
    : []
})
</script>

<template>
  <main class="pb-6 pt-0 lg:pb-8">
    <!-- Breadcrumb full-width encostando na navbar; sem respiro até a foto (a barra
         dourada encosta direto na imagem da PDP). -->
    <div v-if="product" class="shop-breadcrumb-bar">
      <div class="shop-container py-2">
        <UiBreadcrumbs
          :items="[
            { label: 'Início', link: '/' },
            { label: 'Cardápio', link: '/menu' },
            { label: product.name }
          ]"
        />
      </div>
    </div>
    <div class="shop-container">
      <div v-if="pending" class="space-y-4">
        <UiSkeleton class="-mx-4 aspect-[4/3] rounded-none sm:-mx-6 lg:mx-0 lg:h-96 lg:w-1/2 lg:rounded-lg" />
        <UiSkeleton class="h-8 w-2/3" />
        <UiSkeleton class="h-4 w-full" />
        <UiSkeleton class="h-10 w-1/3" />
      </div>

      <UiAlert v-else-if="error" variant="destructive" class="mt-4">
        <UiAlertTitle>Não foi possível abrir este produto</UiAlertTitle>
        <UiAlertDescription>
          <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <span>Tivemos um percalço ao carregar — tente de novo em instantes.</span>
            <UiButton size="sm" variant="outline" @click="refresh">Tentar de novo</UiButton>
          </div>
        </UiAlertDescription>
      </UiAlert>

      <template v-else-if="product && meta">
        <!-- Imagem + informações num único card claro. Mobile/tablet: full-bleed
             (sangra até as bordas, sem cantos/laterais). Desktop: card 2-col contido. -->
        <article class="-mx-4 overflow-hidden border-b bg-card sm:-mx-6 lg:mx-0 lg:grid lg:grid-cols-[minmax(0,1fr)_420px] lg:items-stretch lg:rounded-lg lg:border">
          <section class="min-w-0">
            <div class="relative">
              <img
                v-if="product.image_url"
                :src="product.image_url"
                :alt="product.name"
                class="aspect-[4/3] w-full object-cover"
                :class="product.availability === 'unavailable' ? 'shop-photo-unavailable' : ''"
                fetchpriority="high"
              >
              <div v-else class="flex aspect-[4/3] w-full items-center justify-center bg-muted text-muted-foreground">
                <Icon name="lucide:croissant" class="size-10" />
              </div>
              <!-- Indisponível: etiqueta de VIDRO translúcida em tokens da marca (cream +
                   marrom), harmonizando com a sépia, consistente com os cards. -->
              <div v-if="product.availability === 'unavailable'" class="absolute bottom-3 left-3 z-10">
                <UiBadge class="border-transparent bg-background/75 font-normal text-foreground shadow-sm backdrop-blur-sm">Indisponível</UiBadge>
              </div>
            </div>

            <div v-if="product.gallery.length" class="grid grid-cols-3 gap-3 p-4 pb-0 lg:p-6 lg:pb-0">
              <img
                v-for="image in product.gallery.slice(0, 3)"
                :key="image"
                :src="image"
                :alt="product.name"
                class="aspect-[4/3] rounded-lg border object-cover"
                loading="lazy"
              >
            </div>
          </section>

          <div class="min-w-0 p-4 sm:p-6">

            <div v-if="(badge && product.availability !== 'unavailable') || product.promotion_label" class="mb-2 flex flex-wrap gap-2">
              <UiBadge v-if="badge && product.availability !== 'unavailable'" :variant="badge.variant" class="font-normal">{{ badge.label }}</UiBadge>
              <UiBadge v-if="product.promotion_label" variant="default" class="font-normal">{{ product.promotion_label }}</UiBadge>
            </div>

            <div class="flex items-start justify-between gap-3">
              <h1 class="shop-title line-clamp-2">{{ product.name }}</h1>
              <FavoriteHeart :sku="product.sku" :initial="product.is_favorite" class="-mr-1 shrink-0" />
            </div>
            <p class="mt-2 line-clamp-2 shop-muted">{{ product.short_description }}</p>
            <p v-if="longDescription" class="mt-2 shop-muted">{{ longDescription }}</p>
            <DietaryWarningBadges :warnings="product.dietary_warnings" class="mt-3" />

            <div class="mt-2 flex flex-wrap items-end justify-between gap-4">
              <div>
                <p v-if="product.original_price_display" class="shop-meta line-through">
                  {{ product.original_price_display }}
                </p>
                <div class="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                  <p class="shop-price-strong">{{ product.price_display }}</p>
                  <p v-if="product.unit_weight_label" class="shop-meta">
                    {{ product.unit_weight_label }}
                  </p>
                </div>
              </div>
              <div class="hidden md:block">
                <StockNotifyButton v-if="product.is_notifiable" :sku="product.sku" :name="product.name" :subscribed="product.is_notify_subscribed" />
                <CartQuantityAction
                  v-else
                  :meta="meta"
                  :qty="currentQty"
                  :disabled="!product.can_add_to_cart"
                  :max-qty="product.available_qty ?? product.max_qty"
                />
              </div>
            </div>

            <UiAccordion type="multiple" class="-mx-4 mt-6 border-t sm:-mx-6 lg:mx-0 [&_[data-slot=accordion-trigger]]:font-semibold sm:[&_[data-slot=accordion-trigger]]:px-6 lg:[&_[data-slot=accordion-trigger]]:px-0 [&_[data-slot=accordion-content]>div]:px-8 sm:[&_[data-slot=accordion-content]>div]:px-10 lg:[&_[data-slot=accordion-content]>div]:px-4">
              <UiAccordionItem v-if="product.components.length" value="components">
                <UiAccordionTrigger>Itens do combo</UiAccordionTrigger>
                <UiAccordionContent>
                  <div v-for="component in product.components" :key="component.sku" class="flex justify-between gap-3 py-1 shop-body">
                    <span>{{ component.name }}</span>
                    <span>{{ component.qty_display }}</span>
                  </div>
                </UiAccordionContent>
              </UiAccordionItem>
              <UiAccordionItem v-if="product.allergen?.has_any || product.ingredients_text || product.trace_notice" value="ingredients">
                <UiAccordionTrigger>Ingredientes e restrições</UiAccordionTrigger>
                <UiAccordionContent>
                  <div class="space-y-2 shop-muted">
                    <p v-if="product.ingredients_text">{{ product.ingredients_text }}</p>
                    <p v-if="product.allergen?.allergens.length">Alérgenos: {{ product.allergen.allergens.join(', ') }}</p>
                    <p v-if="product.allergen?.dietary_info.length">Dieta: {{ product.allergen.dietary_info.join(', ') }}</p>
                    <p v-if="product.trace_notice">{{ product.trace_notice }}</p>
                  </div>
                </UiAccordionContent>
              </UiAccordionItem>
              <UiAccordionItem v-if="nutrition" value="nutrition">
                <UiAccordionTrigger>Nutricional</UiAccordionTrigger>
                <UiAccordionContent>
                  <div class="space-y-1 shop-body">
                    <p v-if="nutrition.serving" class="pb-1 shop-meta">Porção: {{ nutrition.serving }}</p>
                    <div
                      v-for="row in nutrition.rows"
                      :key="row.label"
                      class="flex items-baseline justify-between gap-3 border-b border-border/60 py-1.5 last:border-b-0"
                    >
                      <span class="text-muted-foreground">{{ row.label }}</span>
                      <span class="text-right">
                        <span class="shop-price">{{ row.value }}</span>
                        <span v-if="row.pdv != null" class="ml-2 shop-meta tabular-nums">{{ row.pdv }}% VD</span>
                      </span>
                    </div>
                  </div>
                </UiAccordionContent>
              </UiAccordionItem>
              <UiAccordionItem v-if="product.conservation?.has_any || product.unit_weight_label || product.approx_dimensions_label" value="care">
                <UiAccordionTrigger>Conservação</UiAccordionTrigger>
                <UiAccordionContent>
                  <div class="space-y-2 shop-muted">
                    <p v-if="product.conservation?.shelf_life_label">{{ product.conservation.shelf_life_label }}</p>
                    <p v-if="product.conservation?.storage_tip">{{ product.conservation.storage_tip }}</p>
                    <p v-if="product.unit_weight_label">Peso: {{ product.unit_weight_label }}</p>
                    <p v-if="product.approx_dimensions_label">Dimensões: {{ product.approx_dimensions_label }}</p>
                  </div>
                </UiAccordionContent>
              </UiAccordionItem>
            </UiAccordion>
          </div>
        </article>

        <section v-if="crossSell.length" class="mt-8" data-product-cross-sell>
          <h2 class="shop-heading">Você também pode gostar</h2>
          <div class="mt-1 grid grid-cols-1 gap-x-8 md:grid-cols-2">
            <ProductListItem
              v-for="item in crossSell"
              :key="item.sku"
              :item="item"
              class="border-b last:border-b-0 md:[&:nth-last-child(2)]:border-b-0"
            />
          </div>
        </section>

        <div
          class="sticky bottom-20 z-30 mt-4 rounded-lg border border-ink bg-ink p-3 text-ink-foreground shadow-lg md:hidden"
        >
          <div class="flex items-center justify-between gap-3">
            <div class="min-w-0">
              <p class="truncate shop-body">{{ product.name }}</p>
              <p class="shop-price-strong text-background">{{ product.price_display }}</p>
              <p v-if="product.unit_weight_label" class="text-xs text-background/70">
                {{ compactUnitWeightLabel(product.unit_weight_label) }}
              </p>
            </div>
            <StockNotifyButton v-if="product.is_notifiable" :sku="product.sku" :name="product.name" :subscribed="product.is_notify_subscribed" compact inverted />
            <CartQuantityAction
              v-else
              :meta="meta"
              :qty="currentQty"
              :disabled="!product.can_add_to_cart"
              :max-qty="product.available_qty ?? product.max_qty"
              tone="inverted"
            />
          </div>
        </div>
      </template>
    </div>
  </main>
</template>
