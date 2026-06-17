<script setup lang="ts">
import type { CartProjection, ProductMutationMeta } from '~/types/shopman'

const props = withDefaults(defineProps<{
  upsell: CartProjection['upsell']
  heading?: string
}>(), {
  heading: 'Veja também'
})

const { qtyForSku } = useCartState()
const meta = computed<ProductMutationMeta | null>(() => props.upsell
  ? {
      sku: props.upsell.sku,
      name: props.upsell.name,
      price_q: props.upsell.unit_price_q,
      price_display: props.upsell.price_display,
      image_url: props.upsell.image_url
    }
  : null)
const qty = computed(() => props.upsell ? qtyForSku(props.upsell.sku) : 0)

function productRoute (sku: string) {
  return `/product/${encodeURIComponent(sku)}`
}
</script>

<template>
  <section v-if="upsell && meta" class="shop-stack-block" data-cart-upsell-rail>
    <div class="flex items-center justify-between gap-3">
      <p class="shop-item-title font-semibold">{{ heading }}</p>
    </div>
    <UiScrollArea>
      <div class="flex w-max min-w-full gap-3 pb-2">
        <UiItem variant="outline" size="sm" class="w-44 items-stretch gap-3 bg-card p-3">
          <UiItemHeader>
            <NuxtLink
              :to="productRoute(upsell.sku)"
              class="block w-full rounded-md"
              :aria-label="`Ver detalhes de ${upsell.name}`"
            >
              <UiItemMedia v-if="upsell.image_url" variant="image" class="aspect-[4/3] h-auto w-full rounded-md">
                <img :src="upsell.image_url" :alt="upsell.name" loading="lazy" decoding="async">
              </UiItemMedia>
              <UiItemMedia v-else variant="icon" class="aspect-[4/3] h-auto w-full rounded-md">
                <Icon name="lucide:image" />
              </UiItemMedia>
            </NuxtLink>
          </UiItemHeader>
          <UiItemContent class="min-w-0">
            <UiItemTitle class="w-full truncate">{{ upsell.name }}</UiItemTitle>
            <UiItemDescription class="line-clamp-1">{{ upsell.price_display }}</UiItemDescription>
          </UiItemContent>
          <UiItemFooter class="w-full">
            <div class="w-full [&>button]:w-full">
              <CartQuantityAction :meta="meta" :qty="qty" compact add-label="Adicionar" />
            </div>
          </UiItemFooter>
        </UiItem>
      </div>
    </UiScrollArea>
  </section>
</template>
