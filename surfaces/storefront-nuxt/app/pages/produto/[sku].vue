<script setup lang="ts">
import type { ProductResponse } from '~/types/shopman'

const route = useRoute()
const sku = computed(() => String(route.params.sku || ''))
const { setFromServer } = useCartState()
const apiPath = useShopmanApiPath()

const { data, pending, error } = await useFetch<ProductResponse>(
  () => apiPath(`/api/v1/storefront/products/${encodeURIComponent(sku.value)}/`),
  { credentials: 'include' }
)

watchEffect(() => setFromServer(data.value?.cart))

const product = computed(() => data.value?.product)
const meta = computed(() => product.value
  ? {
      sku: product.value.sku,
      name: product.value.name,
      price_q: product.value.base_price_q,
      price_display: product.value.price_display,
      image_url: product.value.image_url
    }
  : null)

useHead(() => ({
  title: product.value ? `${product.value.name} | Shopman Nuxt` : 'Produto | Shopman Nuxt'
}))
</script>

<template>
  <UPage class="shell">
    <ShopHeader />

    <UContainer class="page-container">
      <USkeleton v-if="pending" class="h-96 w-full rounded-md" />

      <UAlert
        v-else-if="error || !product"
        color="error"
        variant="soft"
        title="Produto não encontrado"
      />

      <section v-else class="pdp-layout">
        <UPageCard variant="naked" class="pdp-media-card" :ui="{ container: 'p-0 sm:p-0' }">
          <div class="pdp-image-card">
            <img v-if="product.image_url" :src="product.image_url" :alt="product.name">
            <UIcon v-else name="i-lucide-cookie" class="size-12 text-neutral-400" />
          </div>
        </UPageCard>

        <UPageCard
          variant="outline"
          class="pdp-panel"
          :ui="{ container: 'p-5 sm:p-6', wrapper: 'gap-5' }"
        >
          <template #header>
            <UButton
              to="/menu"
              icon="i-lucide-arrow-left"
              color="neutral"
              variant="ghost"
              size="sm"
              label="Cardápio"
              class="mb-4"
            />
            <UPageHeader
              :title="product.name"
              :description="product.short_description"
              :ui="{
                root: 'py-0 sm:py-0 border-b-0',
                title: 'text-2xl sm:text-3xl',
                description: 'text-base',
                links: 'gap-2'
              }"
            >
              <template #description>
                <span v-if="product.short_description">{{ product.short_description }}</span>
              </template>
            </UPageHeader>
          </template>

          <template #body>
            <div class="pdp-purchase">
              <div>
                <div class="shop-price pdp-price">{{ product.price_display }}</div>
                <div v-if="product.original_price_display" class="shop-original-price">
                  {{ product.original_price_display }}
                </div>
                <UBadge v-if="product.promotion_label" color="primary" variant="solid" class="mt-2">
                  {{ product.promotion_label }}
                </UBadge>
              </div>
              <UBadge
                :color="product.availability === 'unavailable' ? 'error' : 'primary'"
                variant="soft"
              >
                {{ product.availability_label }}
              </UBadge>
            </div>

            <ProductStepper
              v-if="meta"
              :meta="meta"
              :can-add="product.can_add_to_cart"
              :max-qty="product.available_qty"
              add-label="Adicionar ao carrinho"
              :unavailable-label="product.availability_label"
              size="md"
              class="pdp-cta-row"
            />

            <USeparator />

            <p v-if="product.long_description" class="pdp-copy">
              {{ product.long_description }}
            </p>

            <dl class="pdp-facts">
              <div v-if="product.unit_weight_label" class="pdp-fact">
                <dt class="muted">Peso</dt>
                <dd>{{ product.unit_weight_label }}</dd>
              </div>
              <div v-if="product.ingredients_text" class="pdp-fact">
                <dt class="muted">Ingredientes</dt>
                <dd>{{ product.ingredients_text }}</dd>
              </div>
            </dl>
          </template>
        </UPageCard>
      </section>
    </UContainer>

    <BottomCartBar />
    <ShopBottomTabs />
  </UPage>
</template>
