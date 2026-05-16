<script setup lang="ts">
import type { HomeResponse } from '~/types/shopman'

const apiPath = useShopmanApiPath()
const { data, pending, error } = await useFetch<HomeResponse>(apiPath('/api/v1/storefront/home/'), {
  credentials: 'include'
})

definePageMeta({
  path: '/como-funciona'
})

const openingHours = computed(() => data.value?.home.opening_hours || [])
const copy = computed(() => data.value?.home.sections_copy)

useHead({ title: 'Como funciona' })
useSeoMeta({
  title: 'Como funciona',
  description: 'Como pedir, retirar, acompanhar e pagar pelo storefront.'
})
</script>

<template>
  <UContainer v-if="pending" class="py-16">
    <USkeleton class="h-80 w-full" />
  </UContainer>
  <UContainer v-else-if="error" class="py-16">
    <UAlert
      color="error"
      variant="soft"
      title="Não foi possível carregar as informações"
      description="Atualize a página ou volte ao cardápio."
    />
  </UContainer>
  <HowItWorks v-else-if="copy" :opening-hours="openingHours" :copy="copy" />
</template>
