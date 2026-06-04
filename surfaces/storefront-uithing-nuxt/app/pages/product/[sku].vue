<script setup lang="ts">
import type { ProductMutationMeta, ProductResponse } from '~/types/shopman'

const route = useRoute()
const apiPath = useShopmanApiPath()
const sku = computed(() => String(route.params.sku || ''))
const { setFromServer, qtyForSku } = useCartState()

const { data, pending, error, refresh } = await useFetch<ProductResponse>(
  () => apiPath(`/api/v1/storefront/products/${encodeURIComponent(sku.value)}/`),
  { credentials: 'include' }
)

watch(() => data.value?.cart, cart => {
  setFromServer(cart)
}, { immediate: true })

const product = computed(() => data.value?.product || null)
const mobileCtaTouched = ref(false)
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
const mobileCtaQty = computed(() => mobileCtaTouched.value ? currentQty.value : 0)
const mobileCtaAddTarget = computed(() => Math.max(currentQty.value, 1))
const relatedSuggestion = computed(() => {
  const upsell = data.value?.cart.upsell || null
  return upsell && upsell.sku !== sku.value ? upsell : null
})
const detailDescription = computed(() => {
  if (!product.value?.long_description) return ''
  return product.value.long_description === product.value.short_description ? '' : product.value.long_description
})

watch(() => sku.value, () => {
  mobileCtaTouched.value = false
})

useSeoMeta({
  title: () => product.value?.name || 'Produto',
  description: () => product.value?.seo_description || product.value?.short_description || 'Produto'
})
</script>

<template>
  <main class="shop-section">
    <div class="shop-container">
      <UiBreadcrumbs
        class="mb-4"
        :items="[
          { label: 'Início', link: '/' },
          { label: 'Cardápio', link: '/menu' },
          { label: product?.name || 'Produto' }
        ]"
      />

      <div v-if="pending" class="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <UiSkeleton class="h-96 rounded-lg" />
        <UiSkeleton class="h-96 rounded-lg" />
      </div>

      <UiAlert v-else-if="error" variant="destructive">
        <UiAlertTitle>Produto indisponível</UiAlertTitle>
        <UiAlertDescription>
          <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <span>Não foi possível carregar este produto.</span>
            <UiButton size="sm" variant="outline" @click="refresh">Atualizar</UiButton>
          </div>
        </UiAlertDescription>
      </UiAlert>

      <article v-else-if="product && meta" class="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_420px]">
        <section class="min-w-0 space-y-4">
          <div class="shop-panel overflow-hidden">
            <img
              v-if="product.image_url"
              :src="product.image_url"
              :alt="product.name"
              class="aspect-[4/3] w-full object-cover"
              fetchpriority="high"
            >
            <div v-else class="flex aspect-[4/3] items-center justify-center bg-muted text-muted-foreground">
              <Icon name="lucide:image" class="size-10" />
            </div>
          </div>

          <div v-if="product.gallery.length" class="grid grid-cols-3 gap-3">
            <img
              v-for="image in product.gallery.slice(0, 3)"
              :key="image"
              :src="image"
              :alt="product.name"
              class="aspect-square rounded-lg border object-cover"
              loading="lazy"
            >
          </div>
        </section>

        <aside class="min-w-0 space-y-4 lg:sticky lg:top-24 lg:self-start">
          <UiCard class="pb-0">
            <UiCardHeader>
              <div class="mb-2 flex flex-wrap gap-2">
                <UiBadge :variant="availabilityVariant(product.availability)">{{ product.availability_label }}</UiBadge>
                <UiBadge v-if="product.promotion_label" variant="default">{{ product.promotion_label }}</UiBadge>
              </div>
              <UiCardTitle as="h1" class="text-3xl leading-tight">{{ product.name }}</UiCardTitle>
              <UiCardDescription>{{ product.short_description }}</UiCardDescription>
            </UiCardHeader>
            <UiCardContent class="space-y-5">
              <p v-if="detailDescription" class="text-sm leading-6 text-muted-foreground">{{ detailDescription }}</p>
              <div class="flex flex-col items-start gap-4 sm:flex-row sm:items-end sm:justify-between">
                <div>
                  <p v-if="product.original_price_display" class="text-sm text-muted-foreground line-through">
                    {{ product.original_price_display }}
                  </p>
                  <div class="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                    <p class="text-2xl font-semibold">{{ product.price_display }}</p>
                    <p v-if="product.unit_weight_label" class="text-sm text-muted-foreground">
                      {{ product.unit_weight_label }}
                    </p>
                  </div>
                </div>
                <div class="hidden md:block">
                  <CartQuantityAction
                    :meta="meta"
                    :qty="currentQty"
                    :disabled="!product.can_add_to_cart"
                    :max-qty="product.available_qty ?? product.max_qty"
                  />
                </div>
              </div>
            </UiCardContent>
            <UiAccordion type="multiple" class="w-full border-t">
              <UiAccordionItem v-if="product.components.length" value="components">
                <UiAccordionTrigger>Itens do combo</UiAccordionTrigger>
                <UiAccordionContent>
                  <div v-for="component in product.components" :key="component.sku" class="flex justify-between gap-3 py-1 text-sm">
                    <span>{{ component.name }}</span>
                    <span>{{ component.qty_display }}</span>
                  </div>
                </UiAccordionContent>
              </UiAccordionItem>
              <UiAccordionItem v-if="product.allergen?.has_any || product.ingredients_text || product.trace_notice" value="ingredients">
                <UiAccordionTrigger>Ingredientes e restrições</UiAccordionTrigger>
                <UiAccordionContent>
                  <div class="space-y-2 text-sm leading-6 text-muted-foreground">
                    <p v-if="product.ingredients_text">{{ product.ingredients_text }}</p>
                    <p v-if="product.allergen?.allergens.length">Alérgenos: {{ product.allergen.allergens.join(', ') }}</p>
                    <p v-if="product.allergen?.dietary_info.length">Dieta: {{ product.allergen.dietary_info.join(', ') }}</p>
                    <p v-if="product.trace_notice">{{ product.trace_notice }}</p>
                  </div>
                </UiAccordionContent>
              </UiAccordionItem>
              <UiAccordionItem v-if="product.nutrition?.has_any" value="nutrition">
                <UiAccordionTrigger>Nutricional</UiAccordionTrigger>
                <UiAccordionContent>
                  <UiDescriptionList>
                    <template v-if="product.nutrition?.serving_size_display">
                      <UiDescriptionListTerm>Porção</UiDescriptionListTerm>
                      <UiDescriptionListDetails>{{ product.nutrition.serving_size_display }}</UiDescriptionListDetails>
                    </template>
                    <template v-for="row in product.nutrition?.rows || []" :key="row.field">
                      <UiDescriptionListTerm>{{ row.label }}</UiDescriptionListTerm>
                      <UiDescriptionListDetails class="font-medium">{{ row.value_display }}</UiDescriptionListDetails>
                    </template>
                  </UiDescriptionList>
                </UiAccordionContent>
              </UiAccordionItem>
              <UiAccordionItem v-if="product.conservation?.has_any || product.unit_weight_label || product.approx_dimensions_label" value="care">
                <UiAccordionTrigger>Conservação</UiAccordionTrigger>
                <UiAccordionContent>
                  <div class="space-y-2 text-sm text-muted-foreground">
                    <p v-if="product.conservation?.shelf_life_label">{{ product.conservation.shelf_life_label }}</p>
                    <p v-if="product.conservation?.storage_tip">{{ product.conservation.storage_tip }}</p>
                    <p v-if="product.unit_weight_label">Peso: {{ product.unit_weight_label }}</p>
                    <p v-if="product.approx_dimensions_label">Dimensões: {{ product.approx_dimensions_label }}</p>
                  </div>
                </UiAccordionContent>
              </UiAccordionItem>
            </UiAccordion>
          </UiCard>
        </aside>
      </article>

      <CartUpsellRail
        v-if="relatedSuggestion"
        :upsell="relatedSuggestion"
        heading="Veja também"
        class="mt-6"
      />

      <div
        v-if="product && meta"
        class="sticky bottom-20 z-30 mt-5 rounded-lg border border-foreground bg-foreground p-3 text-background shadow-lg md:hidden"
      >
        <div class="flex items-center justify-between gap-3">
          <div class="min-w-0">
            <p class="truncate text-sm font-medium">{{ product.name }}</p>
            <p class="text-lg font-semibold text-background">{{ product.price_display }}</p>
            <p v-if="product.unit_weight_label" class="text-xs text-background/70">
              {{ compactUnitWeightLabel(product.unit_weight_label) }}
            </p>
          </div>
          <CartQuantityAction
            :meta="meta"
            :qty="mobileCtaQty"
            :disabled="!product.can_add_to_cart"
            :max-qty="product.available_qty ?? product.max_qty"
            :add-target-qty="mobileCtaAddTarget"
            tone="inverted"
            @changed="mobileCtaTouched = true"
          />
        </div>
      </div>
    </div>
  </main>
</template>
