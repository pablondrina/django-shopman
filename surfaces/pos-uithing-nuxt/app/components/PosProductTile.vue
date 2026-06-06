<script setup lang="ts">
import type { POSProductProjection } from "~/types/pos";
import { productFallbackStyle, productMonogram } from "~/presentation/catalog";

const props = defineProps<{
  product: POSProductProjection;
  qty: number;
  disabled?: boolean;
}>();

defineEmits<{
  add: [POSProductProjection];
}>();

const hasImage = computed(() => Boolean(props.product.image_url?.trim()));

// Calm, deterministic fallback for products without a photo — derived from the
// collection ref so a whole collection shares a family tint (presentation/catalog).
const fallbackStyle = computed(() => productFallbackStyle(props.product));
const fallbackMonogram = computed(() => productMonogram(props.product));
</script>

<template>
  <UiCard
    as="button"
    type="button"
    class="group relative overflow-hidden rounded-lg p-0 text-left shadow-none transition hover:border-primary/50 active:translate-y-px"
    :class="[
      qty > 0 ? 'border-primary/60 ring-1 ring-primary/30' : '',
      disabled ? 'cursor-not-allowed opacity-50 hover:border-border hover:shadow-none active:translate-y-0' : '',
    ]"
    :disabled="disabled"
    @click="$emit('add', product)"
  >
    <div class="relative aspect-[4/3] w-full overflow-hidden">
      <img
        v-if="hasImage"
        :src="product.image_url"
        :alt="product.name"
        loading="lazy"
        class="size-full object-cover"
      />
      <div
        v-else
        class="grid size-full place-items-center"
        :style="fallbackStyle"
        aria-hidden="true"
      >
        <span class="text-4xl font-black tabular-nums text-black/15">{{ fallbackMonogram }}</span>
      </div>

      <UiBadge
        v-if="qty > 0"
        class="absolute right-1.5 top-1.5 tabular-nums shadow-sm"
      >
        {{ qty }}x
      </UiBadge>
      <span
        v-if="product.is_d1"
        class="absolute left-1.5 top-1.5 rounded-full bg-amber-500 px-2 py-0.5 text-[11px] font-semibold text-white shadow-sm"
      >
        D-1
      </span>
    </div>

    <div class="grid gap-0.5 px-2.5 py-1.5">
      <p class="line-clamp-2 text-sm font-semibold leading-tight">{{ product.name }}</p>
      <strong class="text-base tabular-nums">{{ product.price_display }}</strong>
    </div>
  </UiCard>
</template>
