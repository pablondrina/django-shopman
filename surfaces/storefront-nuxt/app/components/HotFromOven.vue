<script setup lang="ts">
import type { CatalogItemProjection, HomeSectionsCopyProjection } from '~/types/shopman'

const props = defineProps<{
  items: CatalogItemProjection[]
  copy: HomeSectionsCopyProjection
}>()

const heading = computed(() => props.copy.availability_heading)
</script>

<template>
  <UPageSection
    v-if="items.length"
    headline="Destaques"
    :title="heading.title"
    :description="heading.message"
  >
    <template #body>
      <UPageGrid>
        <ProductCard v-for="item in items" :key="item.sku" :item="item" />
      </UPageGrid>
    </template>
  </UPageSection>
</template>
