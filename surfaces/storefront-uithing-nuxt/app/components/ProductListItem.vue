<script setup lang="ts">
import { tileBadge } from '~/presentation/menu'
import type { CatalogItemProjection, ProductMutationMeta } from '~/types/shopman'

const props = defineProps<{
  item: CatalogItemProjection
  // Moldura vintage na miniatura (ligada no cardápio; desligada na busca).
  framed?: boolean
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
      :to="`/produto/${encodeURIComponent(item.sku)}`"
      class="absolute inset-0 z-0 rounded-md"
      :aria-label="`Ver detalhes de ${item.name}`"
    />

    <div class="min-w-0 flex-1 self-center">
      <h3 class="shop-item-title line-clamp-2">{{ item.name }}</h3>
      <p v-if="item.short_description" class="mt-2 line-clamp-2 shop-meta">
        {{ item.short_description }}
      </p>
      <UiBadge v-if="badge && item.availability !== 'unavailable'" :variant="badge.variant" class="mt-2 font-normal">{{ badge.label }}</UiBadge>
      <DietaryWarningBadges :warnings="item.dietary_warnings" class="mt-2" />
      <p class="mt-2 flex flex-wrap items-baseline gap-x-2">
        <span v-if="item.original_price_display" class="shop-meta line-through">{{ item.original_price_display }}</span>
        <span class="shop-price">{{ item.price_display }}</span>
        <span v-if="item.unit_weight_label" class="shop-meta">{{ compactUnitWeightLabel(item.unit_weight_label) }}</span>
      </p>
    </div>

    <div class="pointer-events-none relative shrink-0 self-start">
      <div :class="framed ? 'shop-photo-frame shop-photo-frame-sm drop-shadow-md' : ''">
        <div
          class="size-28 overflow-hidden bg-muted"
          :class="[framed ? 'shop-photo-mat-sm' : 'rounded-lg', item.availability === 'unavailable' ? 'shop-photo-unavailable' : '']"
        >
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
      </div>
      <!-- Indisponível: etiqueta de VIDRO translúcida em tokens da marca (cream + marrom),
           harmonizando com a foto em sépia. Centralizada no topo, descolada da borda. -->
      <div v-if="item.availability === 'unavailable'" class="absolute inset-x-0 top-3 z-10 flex justify-center">
        <UiBadge class="max-w-full border-transparent bg-background/75 font-normal text-foreground shadow-sm backdrop-blur-sm">Indisponível</UiBadge>
      </div>
      <!-- Notificável: pill "Me avise"/"Anotado" ocupa TODA a largura da foto (centrado),
           no rodapé — sem extravasar. -->
      <div v-if="item.is_notifiable" class="pointer-events-auto absolute inset-x-1 bottom-1 z-10">
        <StockNotifyButton
          :sku="item.sku"
          :name="item.name"
          :subscribed="item.is_notify_subscribed"
          pill
        />
      </div>
      <!-- Disponível: "+"/pílula de quantidade na quina. -->
      <div v-else-if="item.availability !== 'unavailable'" class="pointer-events-auto absolute bottom-1 right-1 z-10">
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
