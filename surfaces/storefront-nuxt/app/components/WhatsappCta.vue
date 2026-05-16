<script setup lang="ts">
import type { HomeSectionsCopyProjection, ShopProjection } from '~/types/shopman'

const props = defineProps<{
  shop: ShopProjection
  copy: HomeSectionsCopyProjection
}>()

const show = computed(() => !!props.shop.whatsapp_url)
</script>

<template>
  <UPageSection v-if="show">
    <UPageCard
      orientation="horizontal"
      variant="solid"
    >
      <template #header>
        <UBadge color="success" variant="subtle">
          WhatsApp
        </UBadge>
      </template>

      <template #title>
        {{ copy.whatsapp_cta.title }}
      </template>

      <template #description>
        {{ copy.whatsapp_cta.message }}
      </template>

      <div class="flex justify-end">
        <UButton
          :to="shop.whatsapp_url"
          target="_blank"
          rel="noopener"
          :label="copy.whatsapp_cta_label.title"
          color="success"
          variant="solid"
          size="lg"
        />
      </div>
    </UPageCard>
  </UPageSection>
</template>
