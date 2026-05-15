<script setup lang="ts">
import type { HomeSectionsCopyProjection, ShopProjection } from '~/types/shopman'

const props = defineProps<{
  shop: ShopProjection
  copy: HomeSectionsCopyProjection
}>()

const show = computed(() => !!props.shop.whatsapp_url)
</script>

<template>
  <UPageSection
    v-if="show"
    :ui="{ container: 'py-12 sm:py-16' }"
  >
    <UPageCard
      orientation="horizontal"
      variant="solid"
      :ui="{ container: 'p-8 sm:p-10 lg:p-12 items-center', title: 'text-2xl sm:text-3xl font-bold' }"
    >
      <template #header>
        <UBadge color="success" variant="subtle" class="rounded-full">
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
          size="xl"
        />
      </div>
    </UPageCard>
  </UPageSection>
</template>
