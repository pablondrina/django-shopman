<script setup lang="ts">
import type { CatalogItemProjection, ProductMutationMeta } from '~/types/shopman'

const props = defineProps<{
  item: CatalogItemProjection
  sectionLabel?: string
}>()

const emit = defineEmits<{
  select: [sku: string]
}>()

const { qtyForSku } = useCartState()
const meta = computed<ProductMutationMeta>(() => ({
  sku: props.item.sku,
  name: props.item.name,
  price_q: props.item.base_price_q,
  price_display: props.item.price_display,
  image_url: props.item.image_url
}))
const currentQty = computed(() => qtyForSku(props.item.sku) || props.item.qty_in_cart || 0)
</script>

<template>
  <UiCard class="overflow-hidden">
    <div class="relative aspect-[4/3] bg-muted">
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
      <div class="absolute left-3 top-3">
        <UiBadge :variant="availabilityVariant(item.availability)">
          {{ item.availability_label }}
        </UiBadge>
      </div>
    </div>

    <UiCardContent class="space-y-3 p-4">
      <div class="min-w-0">
        <h3 class="line-clamp-2 text-sm font-semibold leading-5">{{ item.name }}</h3>
        <p class="mt-1 line-clamp-2 min-h-10 text-xs leading-5 text-muted-foreground">
          {{ item.short_description || sectionLabel }}
        </p>
      </div>

      <div class="flex flex-wrap gap-1">
        <UiBadge v-if="item.promotion_label" variant="warning">{{ item.promotion_label }}</UiBadge>
        <UiBadge v-if="item.is_new" variant="info">Novo</UiBadge>
        <UiBadge v-if="item.is_featured" variant="secondary">Destaque</UiBadge>
        <UiBadge v-for="tag in item.dietary_info.slice(0, 2)" :key="tag" variant="outline">{{ tag }}</UiBadge>
      </div>

      <div class="flex items-end justify-between gap-3">
        <div>
          <p v-if="item.original_price_display" class="text-xs text-muted-foreground line-through">
            {{ item.original_price_display }}
          </p>
          <p class="text-base font-semibold">{{ item.price_display }}</p>
        </div>

        <UiHoverCard v-if="item.allergens.length || item.available_qty != null">
          <UiHoverCardTrigger as-child>
            <UiButton variant="ghost" size="icon-sm" icon="lucide:info" aria-label="Detalhes rapidos" />
          </UiHoverCardTrigger>
          <UiHoverCardContent class="w-72">
            <p class="text-sm font-medium">{{ item.name }}</p>
            <p class="mt-1 text-sm text-muted-foreground">{{ item.availability_label }}</p>
            <p v-if="item.available_qty != null" class="mt-2 text-xs text-muted-foreground">
              Disponivel agora: {{ item.available_qty }}
            </p>
            <p v-if="item.allergens.length" class="mt-2 text-xs text-muted-foreground">
              Alergenos: {{ item.allergens.join(', ') }}
            </p>
          </UiHoverCardContent>
        </UiHoverCard>
      </div>

    </UiCardContent>

    <UiCardFooter class="flex items-center justify-between gap-3 p-4 pt-0">
      <QuantityControl
        :meta="meta"
        :qty="currentQty"
        :disabled="!item.can_add_to_cart"
        :max-qty="item.available_qty"
        compact
      />
      <UiButton variant="outline" size="sm" icon="lucide:info" @click="emit('select', item.sku)">
        Detalhes
      </UiButton>
    </UiCardFooter>
  </UiCard>
</template>
