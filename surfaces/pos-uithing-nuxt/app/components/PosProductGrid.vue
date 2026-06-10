<script setup lang="ts">
// Sale Workspace · product grid (spec §2.2) — image-forward grade + rail de
// categorias. Consumes the catalog Projection through `presentation/catalog`
// (favourite-ordered categories, name/SKU filter); price and availability are
// sealed in the Projection (price_display, is_d1) and only rendered. Search and
// the active collection are grid-local presentation state. Emits `add`; the
// shell resolves the session command.
import type { POSCartItem, POSCollectionProjection, POSProductProjection } from "~/types/pos";
import { filterProducts, orderCollections } from "~/presentation/catalog";

const props = defineProps<{
  products: POSProductProjection[];
  collections: POSCollectionProjection[];
  favoriteRefs: string[];
  cartItems: POSCartItem[];
  pending: boolean;
}>();

const emit = defineEmits<{ add: [POSProductProjection] }>();

const search = ref("");
const activeCollection = ref("");

// Grid density is a grid-local presentation preference (not data, not policy).
// Persisted per terminal in localStorage; defaults to "cozy" on the server so
// hydration stays stable, then the stored choice is applied after mount.
type Density = "compact" | "cozy" | "roomy";
const DENSITIES: { key: Density; label: string; icon: string; cols: string }[] = [
  { key: "compact", label: "Compacta", icon: "lucide:grid-3x3", cols: "grid-cols-3 sm:grid-cols-4 lg:grid-cols-6 xl:grid-cols-7 2xl:grid-cols-8" },
  { key: "cozy", label: "Padrão", icon: "lucide:layout-grid", cols: "grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6" },
  { key: "roomy", label: "Ampla", icon: "lucide:square", cols: "grid-cols-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-4" },
];
const DENSITY_STORAGE_KEY = "pos.productDensity";
const density = ref<Density>("cozy");
const densityCols = computed(() => DENSITIES.find((d) => d.key === density.value)?.cols ?? DENSITIES[1]!.cols);
const densityIcon = computed(() => DENSITIES.find((d) => d.key === density.value)?.icon ?? DENSITIES[1]!.icon);

onMounted(() => {
  const stored = localStorage.getItem(DENSITY_STORAGE_KEY);
  if (stored === "compact" || stored === "cozy" || stored === "roomy") density.value = stored;
});

function setDensity(value: Density) {
  density.value = value;
  if (import.meta.client) localStorage.setItem(DENSITY_STORAGE_KEY, value);
}

const orderedCollections = computed(() => orderCollections(props.collections, props.favoriteRefs));
const filteredProducts = computed(() =>
  filterProducts(props.products, { collectionRef: activeCollection.value, query: search.value }),
);

function productQty(sku: string): number {
  return props.cartItems.find((item) => item.sku === sku)?.qty || 0;
}

// F3 focuses the search field (the shell owns the shortcut, the grid the field).
const searchInputRef = ref<{ inputRef?: HTMLInputElement } | null>(null);
defineExpose({ focusSearch: () => searchInputRef.value?.inputRef?.focus() });
</script>

<template>
  <section class="flex h-full min-h-0 flex-col gap-3">
    <div class="flex shrink-0 items-center gap-2">
      <div class="relative flex-1">
        <Icon name="lucide:search" class="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <UiInput ref="searchInputRef" v-model="search" class="h-11 pl-9 text-base" type="search" placeholder="Buscar produto por nome ou SKU" autofocus />
      </div>
      <UiPopover>
        <UiPopoverTrigger as-child>
          <UiButton variant="outline" size="icon" class="size-11 shrink-0" aria-label="Densidade da grade" title="Densidade da grade">
            <Icon :name="densityIcon" class="size-5" />
          </UiButton>
        </UiPopoverTrigger>
        <UiPopoverContent align="end" class="w-44 p-1">
          <p class="px-2 py-1.5 text-xs font-medium text-muted-foreground">Densidade da grade</p>
          <button
            v-for="opt in DENSITIES"
            :key="opt.key"
            type="button"
            class="flex w-full items-center gap-2 rounded-md px-2 py-2 text-left text-sm transition hover:bg-accent"
            :class="density === opt.key ? 'bg-accent font-medium text-accent-foreground' : ''"
            @click="setDensity(opt.key)"
          >
            <Icon :name="opt.icon" class="size-4 shrink-0" />
            <span class="flex-1">{{ opt.label }}</span>
            <Icon v-if="density === opt.key" name="lucide:check" class="size-4 shrink-0 text-primary" />
          </button>
        </UiPopoverContent>
      </UiPopover>
    </div>

    <div class="-mx-1 flex shrink-0 gap-1.5 overflow-x-auto px-1 pb-1 no-scrollbar">
      <button
        type="button"
        class="flex h-9 shrink-0 items-center whitespace-nowrap rounded-full border px-3 text-sm font-medium transition"
        :class="activeCollection === '' ? 'border-primary bg-primary/5' : 'hover:border-primary/50 hover:bg-accent'"
        @click="activeCollection = ''"
      >
        Tudo
      </button>
      <button
        v-for="collection in orderedCollections"
        :key="collection.ref"
        type="button"
        class="flex h-9 shrink-0 items-center whitespace-nowrap rounded-full border px-3 text-sm font-medium transition"
        :class="activeCollection === collection.ref ? 'border-primary bg-primary/5' : 'hover:border-primary/50 hover:bg-accent'"
        @click="activeCollection = collection.ref"
      >
        {{ collection.name }}
      </button>
    </div>

    <div class="-mx-1 px-1 md:min-h-0 md:flex-1 md:overflow-y-auto">
      <div v-if="pending" class="grid gap-2.5" :class="densityCols">
        <div v-for="idx in 12" :key="idx" class="aspect-[4/3] animate-pulse rounded-lg border bg-muted" />
      </div>
      <div v-else-if="!filteredProducts.length" class="rounded-lg border border-dashed p-8 text-center text-muted-foreground">
        Nenhum produto encontrado.
      </div>
      <div v-else class="grid gap-2.5" :class="densityCols">
        <PosProductTile
          v-for="product in filteredProducts"
          :key="product.sku"
          :product="product"
          :qty="productQty(product.sku)"
          @add="emit('add', $event)"
        />
      </div>
    </div>
  </section>
</template>
