<script setup lang="ts">
import type { CatalogItemProjection, ProductCommandMeta } from '~/types/shopman'

type BadgeColor = 'neutral' | 'success' | 'warning' | 'info' | 'error'

const props = defineProps<{ item: CatalogItemProjection }>()

const meta = computed((): ProductCommandMeta => ({
  sku: props.item.sku,
  name: props.item.name,
  price_q: props.item.base_price_q,
  price_display: props.item.price_display,
  image_url: props.item.image_url
}))

const availabilityColor = computed<BadgeColor>(() => {
  switch (props.item.availability) {
    case 'available': return 'success'
    case 'low_stock': return 'warning'
    case 'planned_ok': return 'info'
    case 'unavailable': return 'error'
    default: return 'neutral'
  }
})
</script>

<template>
  <article class="product-card shop-link-card overflow-hidden rounded-lg border border-default bg-default">
    <div class="grid grid-cols-[112px_1fr] sm:grid-cols-1">
      <NuxtLink
        :to="`/produto/${item.sku}`"
        class="product-image relative block min-h-28 overflow-hidden bg-elevated sm:aspect-4/3"
        :aria-label="`Ver ${item.name}`"
      >
        <img
          v-if="item.image_url"
          :src="item.image_url"
          :alt="item.name"
          loading="lazy"
          decoding="async"
          sizes="(min-width: 1280px) 25vw, (min-width: 768px) 50vw, 112px"
          class="size-full object-cover"
        >
        <UIcon v-else name="i-lucide-cookie" class="absolute inset-0 m-auto size-8 text-muted" />

      </NuxtLink>

      <div class="flex min-w-0 flex-col p-3 sm:p-4">
        <div class="min-w-0 flex-1">
          <div class="mb-2 flex flex-wrap gap-1.5">
            <UBadge :color="availabilityColor" variant="subtle" size="xs">
              {{ item.availability_label }}
            </UBadge>
            <UBadge v-if="item.promotion_label" color="primary" variant="solid" size="xs">
              {{ item.promotion_label }}
            </UBadge>
            <UBadge v-if="item.is_new" color="info" variant="subtle" size="xs">Novo</UBadge>
          </div>

          <h3 class="text-sm font-semibold leading-snug text-highlighted sm:text-base">
            <NuxtLink :to="`/produto/${item.sku}`" class="hover:text-primary">
              {{ item.name }}
            </NuxtLink>
          </h3>
          <p v-if="item.short_description" class="mt-1 line-clamp-2 text-sm leading-relaxed text-muted">
            {{ item.short_description }}
          </p>
          <div v-if="item.dietary_info.length" class="mt-2 hidden flex-wrap gap-1 sm:flex">
            <UBadge
              v-for="tag in item.dietary_info.slice(0, 2)"
              :key="tag"
              color="neutral"
              variant="subtle"
              size="xs"
            >
              {{ tag }}
            </UBadge>
          </div>
        </div>

        <div class="mt-3 flex items-end justify-between gap-3 border-t border-default pt-3">
          <div>
            <div v-if="item.original_price_display" class="text-xs text-muted line-through">
              {{ item.original_price_display }}
            </div>
            <div class="text-lg font-bold tabular-nums text-highlighted">{{ item.price_display }}</div>
          </div>
          <ProductStepper
            :meta="meta"
            :can-add="item.can_add_to_cart"
            :max-qty="item.available_qty"
            :unavailable-label="item.availability_label"
            size="xs"
          />
        </div>
      </div>
    </div>
  </article>
</template>
