<script setup lang="ts">
import type { CatalogItemProjection } from '~/types/shopman'

defineProps<{ items: CatalogItemProjection[] }>()
</script>

<template>
  <UPageSection
    v-if="items.length"
    headline="Destaques"
    title="Selecionados pela casa"
    description="Escolhas disponíveis no cardápio."
  >
    <UPageGrid>
      <ProductCard v-for="item in items" :key="item.sku" :item="item" />
    </UPageGrid>
  </UPageSection>
</template>
