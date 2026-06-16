<script setup lang="ts">
import { tileBadge } from '~/presentation/menu'
import type { CatalogItemProjection, ProductMutationMeta } from '~/types/shopman'

const props = defineProps<{
  item: CatalogItemProjection
}>()

const { qtyForSku } = useCartState()
const meta = computed<ProductMutationMeta>(() => ({
  sku: props.item.sku,
  name: props.item.name,
  price_q: props.item.base_price_q,
  price_display: props.item.price_display,
  image_url: props.item.image_url
}))
const currentQty = computed(() => qtyForSku(props.item.sku))
const badge = computed(() => tileBadge(props.item))
</script>

<template>
  <article class="relative flex min-w-0 items-stretch gap-3 py-3" data-product-list-item>
    <NuxtLink
      :to="`/product/${encodeURIComponent(item.sku)}`"
      class="absolute inset-0 z-0 rounded-md"
      :aria-label="`Ver detalhes de ${item.name}`"
    />

    <div class="min-w-0 flex-1 self-center">
      <h3 class="line-clamp-2 text-base leading-5">{{ item.name }}</h3>
      <p v-if="item.short_description" class="mt-1.5 line-clamp-2 text-xs leading-[14px] text-muted-foreground">
        {{ item.short_description }}
      </p>
      <UiBadge v-if="badge" :variant="badge.variant" class="mt-1.5 font-normal">{{ badge.label }}</UiBadge>
      <p class="mt-1.5 flex flex-wrap items-baseline gap-x-2 text-sm">
        <span v-if="item.original_price_display" class="text-xs text-muted-foreground line-through">{{ item.original_price_display }}</span>
        <span class="font-semibold tabular-nums">{{ item.price_display }}</span>
        <span v-if="item.unit_weight_label" class="text-xs text-muted-foreground">{{ compactUnitWeightLabel(item.unit_weight_label) }}</span>
      </p>
    </div>

    <div class="relative shrink-0 self-start">
      <div class="size-28 overflow-hidden rounded-lg bg-muted" :class="item.availability === 'unavailable' ? 'opacity-60 grayscale' : ''">
        <img
          v-if="item.image_url"
          :src="item.image_url"
          :alt="item.name"
          loading="lazy"
          decoding="async"
          class="size-full object-cover"
        >
        <div v-else class="flex size-full items-center justify-center text-muted-foreground">
          <Icon name="lucide:croissant" class="size-6" />
        </div>
      </div>
      <div class="absolute bottom-1 right-1 z-10">
        <CartQuantityAction
          :meta="meta"
          :qty="currentQty"
          :disabled="!item.can_add_to_cart"
          :max-qty="item.available_qty"
          compact
          add-icon-only
        />
      </div>
    </div>
  </article>
</template>
