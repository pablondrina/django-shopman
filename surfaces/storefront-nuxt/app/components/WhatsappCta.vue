<script setup lang="ts">
import type { ShopProjection } from '~/types/shopman'

const props = defineProps<{ shop: ShopProjection }>()

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
        Prefere conversar?
      </template>

      <template #description>
        Canal direto com a casa para dúvidas, encomendas e atendimento do pedido.
      </template>

      <div class="flex justify-end">
        <UButton
          :to="shop.whatsapp_url"
          target="_blank"
          rel="noopener"
          label="Chamar no WhatsApp"
          color="success"
          variant="solid"
          size="xl"
        />
      </div>
    </UPageCard>
  </UPageSection>
</template>
