<script setup lang="ts">
import type { CatalogItemProjection } from '~/types/shopman'

type ProductBadge = {
  label: string
  color: 'primary' | 'neutral'
  variant: 'solid' | 'soft' | 'outline'
}

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

const productBadges = computed<ProductBadge[]>(() => {
  const badges: ProductBadge[] = []
  if (props.item.promotion_label) badges.push({ label: props.item.promotion_label, color: 'primary', variant: 'solid' })
  if (props.item.is_new) badges.push({ label: 'Novo', color: 'neutral', variant: 'soft' })
  if (props.item.is_featured) badges.push({ label: 'Popular', color: 'neutral', variant: 'outline' })
  return badges
})

const dietaryTags = computed(() => props.item.dietary_info.slice(0, 2))
</script>

<template>
  <UPageCard
    as="article"
    variant="outline"
    spotlight
    spotlight-color="neutral"
    class="shop-product-card"
    :ui="{
      container: 'p-0 sm:p-0 gap-0',
      wrapper: 'h-full'
    }"
  >
    <div class="shop-product-card-inner">
      <NuxtLink :to="`/produto/${item.sku}`" class="shop-product-image" :aria-label="`Ver ${item.name}`">
        <img v-if="item.image_url" :src="item.image_url" :alt="item.name" loading="lazy">
        <span v-else class="shop-product-image-placeholder">
          <UIcon name="i-lucide-cookie" class="size-8" />
        </span>

        <span v-if="productBadges.length" class="shop-product-image-badges">
          <UBadge
            v-for="badge in productBadges"
            :key="badge.label"
            :color="badge.color"
            :variant="badge.variant"
            size="xs"
          >
            {{ badge.label }}
          </UBadge>
        </span>
      </NuxtLink>

      <div class="shop-product-content">
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

          <div v-if="dietaryTags.length" class="shop-product-tags">
            <UBadge
              v-for="tag in dietaryTags"
              :key="tag"
              color="neutral"
              variant="soft"
              size="xs"
            >
              {{ tag }}
            </UBadge>
          </div>
        </div>

        <div class="shop-price-row">
          <div class="shop-price-stack">
            <div v-if="item.original_price_display" class="shop-original-price">
              {{ item.original_price_display }}
            </div>
            <div class="shop-price">{{ item.price_display }}</div>
          </div>
          <ProductStepper
            :meta="meta"
            :can-add="item.can_add_to_cart"
            :max-qty="item.available_qty"
            add-label="Adicionar"
            :unavailable-label="item.availability_label"
          />
        </div>
      </div>
    </div>
  </UPageCard>
</template>
