<script setup lang="ts">
import type { CatalogItemProjection } from '~/types/shopman'

const props = defineProps<{
  item: CatalogItemProjection
}>()

const meta = computed(() => ({
  sku: props.item.sku,
  name: props.item.name,
  price_q: props.item.base_price_q,
  price_display: props.item.price_display,
  image_url: props.item.image_url
}))
</script>

<template>
  <UCard
    as="article"
    class="shop-product-card"
    :ui="{ header: 'p-0 sm:p-0', body: 'p-0 sm:p-0', footer: 'p-3 sm:p-3' }"
  >
    <template #header>
      <NuxtLink :to="`/produto/${item.sku}`" class="shop-product-image" :aria-label="`Ver ${item.name}`">
        <img v-if="item.image_url" :src="item.image_url" :alt="item.name" loading="lazy">
        <UAvatar v-else icon="i-lucide-cookie" size="3xl" />
      </NuxtLink>
    </template>

    <div class="shop-product-copy">
      <div class="shop-product-title-row">
        <h3 class="shop-product-title">
          <NuxtLink :to="`/produto/${item.sku}`">{{ item.name }}</NuxtLink>
        </h3>
        <UBadge
          v-if="item.availability !== 'available'"
          size="xs"
          :color="item.availability === 'unavailable' ? 'error' : 'warning'"
          variant="soft"
        >
          {{ item.availability_label }}
        </UBadge>
      </div>
      <p v-if="item.short_description" class="shop-product-description">
        {{ item.short_description }}
      </p>
    </div>

    <template #footer>
      <div class="shop-price-row">
        <div>
          <div class="shop-price">{{ item.price_display }}</div>
          <div v-if="item.original_price_display" class="shop-original-price">
            {{ item.original_price_display }}
          </div>
        </div>
        <ProductStepper
          :meta="meta"
          :can-add="item.can_add_to_cart"
          :max-qty="item.available_qty"
        />
      </div>
    </template>
  </UCard>
</template>
