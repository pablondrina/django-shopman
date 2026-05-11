<script setup lang="ts">
import type { CatalogItemProjection } from '~/types/shopman'

defineProps<{ items: CatalogItemProjection[] }>()
</script>

<template>
  <UPageSection
    v-if="items.length"
    headline="Direto do forno"
    title="Ainda quentinho"
    description="Selecionado pela casa neste exato momento. Disponível agora — sem promessa, é o que tem fresquinho."
  >
    <UPageGrid>
      <ProductCard v-for="item in items" :key="item.sku" :item="item" />
    </UPageGrid>
  </UPageSection>
</template>
