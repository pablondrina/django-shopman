<script setup lang="ts">
import { tileBadge } from '~/presentation/menu'
import type { CatalogItemProjection, ProductMutationMeta } from '~/types/shopman'

const props = defineProps<{
  item: CatalogItemProjection
  sectionLabel?: string
}>()

const badge = computed(() => tileBadge(props.item))

const { qtyForSku } = useCartState()
const meta = computed<ProductMutationMeta>(() => ({
  sku: props.item.sku,
  name: props.item.name,
  price_q: props.item.base_price_q,
  price_display: props.item.price_display,
  image_url: props.item.image_url
}))
const currentQty = computed(() => qtyForSku(props.item.sku))

function productRoute (sku: string) {
  return `/product/${encodeURIComponent(sku)}`
}
</script>

<template>
  <div class="flex min-w-0 flex-col" data-product-tile>
    <!-- Foto como retrato vintage: paspatur branco recortado + sombra + leve inclinação. -->
    <div class="drop-shadow-md transition-transform duration-200 hover:-rotate-1 motion-reduce:hover:rotate-0">
      <div class="shop-photo-frame">
        <div class="shop-photo-mat relative block bg-white">
          <UiAspectRatio :ratio="4 / 3" class="overflow-hidden bg-muted">
            <img
              v-if="item.image_url"
              :src="item.image_url"
              :alt="item.name"
              loading="lazy"
              decoding="async"
              class="size-full object-cover"
            >
            <div v-else class="flex size-full items-center justify-center text-muted-foreground">
              <Icon name="lucide:image" class="size-7" />
            </div>
            <UiButton
              :to="productRoute(item.sku)"
              variant="ghost"
              class="absolute inset-0 z-10 size-full rounded-none bg-transparent p-0 hover:bg-black/5"
              :aria-label="`Ver detalhes de ${item.name}`"
            >
              <span class="sr-only">Ver detalhes de {{ item.name }}</span>
            </UiButton>
            <div v-if="badge" class="absolute left-2 top-2 z-20">
              <UiBadge :variant="badge.variant" class="font-normal shadow-sm">{{ badge.label }}</UiBadge>
            </div>
          </UiAspectRatio>
        </div>
      </div>
    </div>

    <div class="flex min-w-0 flex-1 flex-col">
      <div class="shop-stack-tight px-1 pt-3">
        <div class="min-w-0">
          <h3 class="shop-item-title line-clamp-2">{{ item.name }}</h3>
          <p class="mt-1 line-clamp-2 shop-meta sm:min-h-10">
            {{ item.short_description || sectionLabel }}
          </p>
        </div>

        <div class="hidden flex-wrap gap-1 sm:flex">
          <UiBadge v-if="item.promotion_label" variant="default" class="font-normal">{{ item.promotion_label }}</UiBadge>
          <UiBadge v-if="item.is_new" variant="secondary" class="font-normal">Novo</UiBadge>
          <UiBadge v-if="item.is_featured" variant="secondary" class="font-normal">Destaque</UiBadge>
          <!-- tags secundárias (dieta): mesma cor/peso/tamanho da descrição -->
          <UiBadge v-for="tag in item.dietary_info.slice(0, 2)" :key="tag" variant="outline" class="border-muted-foreground/40 text-xs font-normal text-muted-foreground">{{ tag }}</UiBadge>
        </div>

        <div class="flex flex-wrap items-end justify-between gap-x-3 gap-y-2">
          <div class="min-w-0 flex-1">
            <p v-if="item.original_price_display" class="shop-meta line-through">
              {{ item.original_price_display }}
            </p>
            <p class="shop-price">{{ item.price_display }}</p>
            <p v-if="item.unit_weight_label" class="shop-meta">
              {{ compactUnitWeightLabel(item.unit_weight_label) }}
            </p>
          </div>

          <div class="ml-auto shrink-0">
            <CartQuantityAction
              :meta="meta"
              :qty="currentQty"
              :disabled="!item.can_add_to_cart"
              :max-qty="item.available_qty"
              compact
            />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
