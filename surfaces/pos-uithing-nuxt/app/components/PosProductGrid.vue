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
  <section class="flex min-h-0 flex-col gap-3 md:order-2">
    <div class="relative shrink-0">
      <Icon name="lucide:search" class="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
      <UiInput ref="searchInputRef" v-model="search" class="h-11 pl-9 text-base" type="search" placeholder="Buscar produto por nome ou SKU" autofocus />
    </div>

    <div class="-mx-1 flex shrink-0 gap-1.5 overflow-x-auto px-1 pb-1 no-scrollbar">
      <button
        type="button"
        class="shrink-0 whitespace-nowrap rounded-md border px-3 py-1.5 text-sm font-medium transition"
        :class="activeCollection === '' ? 'border-primary bg-primary text-primary-foreground' : 'hover:border-primary/50 hover:bg-accent'"
        @click="activeCollection = ''"
      >
        Tudo
      </button>
      <button
        v-for="collection in orderedCollections"
        :key="collection.ref"
        type="button"
        class="shrink-0 whitespace-nowrap rounded-md border px-3 py-1.5 text-sm font-medium transition"
        :class="activeCollection === collection.ref ? 'border-primary bg-primary text-primary-foreground' : 'hover:border-primary/50 hover:bg-accent'"
        @click="activeCollection = collection.ref"
      >
        {{ collection.name }}
      </button>
    </div>

    <div class="-mx-1 px-1 md:min-h-0 md:flex-1 md:overflow-y-auto">
      <div v-if="pending" class="grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6">
        <div v-for="idx in 12" :key="idx" class="aspect-[4/3] animate-pulse rounded-xl border bg-muted" />
      </div>
      <div v-else-if="!filteredProducts.length" class="rounded-lg border border-dashed p-8 text-center text-muted-foreground">
        Nenhum produto encontrado.
      </div>
      <div v-else class="grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6">
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
