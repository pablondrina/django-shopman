<script setup lang="ts">
import type { HomeResponse } from '~/types/shopman'

const { setFromServer } = useCartState()
const { setFromHome } = useShopSession()
const apiPath = useShopmanApiPath()
const { data, pending, error, refresh } = await useFetch<HomeResponse>(apiPath('/api/v1/storefront/home/'), {
  credentials: 'include'
})

watchEffect(() => {
  setFromServer(data.value?.cart)
  setFromHome(data.value?.home)
})

const home = computed(() => data.value?.home)

if (import.meta.client) {
  const refreshTimer = setInterval(() => {
    refresh()
  }, 60_000)
  onBeforeUnmount(() => clearInterval(refreshTimer))
}

useHead({
  title: () => home.value?.shop.brand_name || 'Shopman'
})

useSeoMeta({
  title: () => home.value ? `${home.value.shop.brand_name} — ${home.value.shop.tagline}` : 'Shopman',
  description: () => home.value?.shop.description || ''
})
</script>

<template>
  <div>
    <UContainer v-if="pending" class="py-16">
      <USkeleton class="h-96 w-full" />
    </UContainer>

    <UContainer v-else-if="error" class="py-16">
      <UAlert color="error" variant="soft" title="Não foi possível carregar a casa" description="Tenta de novo em um instante." />
    </UContainer>

    <template v-else-if="home">
      <HeroCarousel :home="home" />
      <ContextualBanners :home="home" />
      <HotFromOven :items="home.featured_items" />
      <TomorrowHook :omotenashi="home.omotenashi" />
      <HowItWorks :opening-hours="home.opening_hours" />
      <WhatsappCta :shop="home.shop" />
    </template>
  </div>
</template>
