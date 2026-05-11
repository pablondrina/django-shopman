<script setup lang="ts">
import type { CatalogItemProjection, ProductCommandMeta } from '~/types/shopman'

const props = defineProps<{ item: CatalogItemProjection }>()

const meta = computed((): ProductCommandMeta => ({
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
    :ui="{ header: 'p-0' }"
    class="h-full"
  >
    <template #header>
      <NuxtLink
        :to="`/produto/${item.sku}`"
        class="product-image block relative overflow-hidden bg-elevated aspect-4/3"
        :aria-label="`Ver ${item.name}`"
      >
        <img v-if="item.image_url" :src="item.image_url" :alt="item.name" loading="lazy" class="size-full object-cover">
        <UIcon v-else name="i-lucide-cookie" class="absolute inset-0 m-auto size-8 text-muted" />

        <UBadge v-if="item.promotion_label" color="primary" variant="solid" class="absolute top-2 left-2">
          {{ item.promotion_label }}
        </UBadge>
      </NuxtLink>
    </template>

    <div class="grid gap-1.5">
      <h3 class="text-sm font-semibold leading-snug">
        <NuxtLink :to="`/produto/${item.sku}`">{{ item.name }}</NuxtLink>
      </h3>
      <p v-if="item.short_description" class="text-sm text-muted leading-relaxed line-clamp-2">
        {{ item.short_description }}
      </p>
      <div v-if="item.dietary_info.length" class="flex flex-wrap gap-1">
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

    <template #footer>
      <div class="flex items-end justify-between gap-3">
        <div>
          <div v-if="item.original_price_display" class="text-sm text-muted line-through">
            {{ item.original_price_display }}
          </div>
          <div class="text-base font-bold tabular-nums">{{ item.price_display }}</div>
        </div>
        <ProductStepper
          :meta="meta"
          :can-add="item.can_add_to_cart"
          :max-qty="item.available_qty"
          :unavailable-label="item.availability_label"
          size="xs"
        />
      </div>
    </template>
  </UCard>
</template>
