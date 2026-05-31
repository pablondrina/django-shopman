<script setup lang="ts">
import type { POSProductProjection } from "~/types/pos";

const props = defineProps<{
  product: POSProductProjection;
  qty: number;
  disabled?: boolean;
}>();

defineEmits<{
  add: [POSProductProjection];
}>();

const hasImage = computed(() => Boolean(props.product.image_url?.trim()));

// Deterministic, calm color fallback for products without a photo: hue derived
// from the collection ref so a whole collection shares a family tint (Odoo-style
// color coding), kept low-saturation so the grid stays calm, not marketing.
const fallbackHue = computed(() => {
  const seed = props.product.collection_ref || props.product.sku || props.product.name;
  let hash = 0;
  for (let i = 0; i < seed.length; i += 1) {
    hash = (hash * 31 + seed.charCodeAt(i)) % 360;
  }
  return hash;
});
const fallbackStyle = computed(() => ({
  background: `linear-gradient(135deg, hsl(${fallbackHue.value} 42% 92%), hsl(${(fallbackHue.value + 24) % 360} 38% 85%))`,
}));
const fallbackMonogram = computed(() => (props.product.name?.trim()?.[0] || "·").toUpperCase());
</script>

<template>
  <UiCard
    as="button"
    type="button"
    class="group relative overflow-hidden rounded-xl p-0 text-left shadow-none transition hover:border-primary/40 hover:shadow-sm active:translate-y-px"
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
        class="size-full object-cover transition group-hover:scale-[1.03]"
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
      <p class="truncate text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{{ product.sku }}</p>
      <p class="line-clamp-2 text-sm font-semibold leading-tight">{{ product.name }}</p>
      <strong class="text-base tabular-nums">{{ product.price_display }}</strong>
    </div>
  </UiCard>
</template>
