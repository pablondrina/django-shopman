<script setup lang="ts">
import type { ProductResponse } from '~/types/shopman'

const route = useRoute()
const sku = computed(() => String(route.params.sku || ''))
const { setFromServer } = useCartState()

const { data, pending, error } = await useFetch<ProductResponse>(
  () => shopmanApiPath(`/api/v1/storefront/products/${encodeURIComponent(sku.value)}/`),
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
    <header class="topbar">
      <UContainer class="topbar-inner">
        <UButton to="/menu" variant="ghost" color="neutral" icon="i-lucide-arrow-left" label="Menu" />
      </UContainer>
    </header>

    <UContainer class="page">
      <USkeleton v-if="pending" class="h-96 w-full rounded-md" />

      <UAlert
        v-else-if="error || !product"
        color="error"
        variant="soft"
        title="Produto não encontrado"
      />

      <section v-else class="pdp-layout">
        <UCard class="pdp-image-card" :ui="{ body: 'p-0 sm:p-0' }">
          <img v-if="product.image_url" :src="product.image_url" :alt="product.name">
          <UAvatar v-else icon="i-lucide-cookie" size="3xl" />
        </UCard>

        <UCard class="pdp-panel">
          <UPageHeader
            :title="product.name"
            :description="product.short_description"
            :ui="{ root: 'py-0 sm:py-0', title: 'text-3xl', description: 'text-sm' }"
          >
            <UBadge
              :color="product.availability === 'unavailable' ? 'error' : 'primary'"
              variant="soft"
            >
              {{ product.availability_label }}
            </UBadge>
          </UPageHeader>

          <div>
            <div class="shop-price pdp-price">{{ product.price_display }}</div>
            <div v-if="product.original_price_display" class="shop-original-price">
              {{ product.original_price_display }}
            </div>
          </div>

          <ProductStepper
            v-if="meta"
            :meta="meta"
            :can-add="product.can_add_to_cart"
            :max-qty="product.available_qty"
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
        </UCard>
      </section>
    </UContainer>

    <BottomCartBar />
  </UPage>
</template>
