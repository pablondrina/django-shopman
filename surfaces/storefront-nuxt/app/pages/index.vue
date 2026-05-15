<script setup lang="ts">
import type { HomeResponse } from '~/types/shopman'

const { setFromServer } = useCartState()
const { setFromHome } = useShopSession()
const apiPath = useShopmanApiPath()
const requestUrl = useRequestURL()
const { data, pending, error, refresh } = await useFetch<HomeResponse>(apiPath('/api/v1/storefront/home/'), {
  credentials: 'include'
})

watch(data, (next) => {
  setFromServer(next?.cart)
  setFromHome(next?.home)
}, { immediate: true })

const home = computed(() => data.value?.home)
const pageTitle = computed(() => {
  const brand = home.value?.shop.brand_name || 'Shopman'
  const tagline = home.value?.shop.tagline?.trim()
  return tagline ? `${brand} · ${tagline}` : brand
})
const localBusinessJsonLd = computed(() => {
  if (!home.value) return null
  const shop = home.value.shop
  return {
    '@context': 'https://schema.org',
    '@type': 'Bakery',
    name: shop.brand_name,
    description: shop.description,
    url: requestUrl.origin,
    image: shop.logo_url ? [shop.logo_url] : undefined,
    telephone: shop.phone || shop.phone_display || undefined,
    email: shop.email || undefined,
    address: shop.full_address
      ? {
          '@type': 'PostalAddress',
          streetAddress: shop.full_address,
          addressLocality: shop.default_city || undefined,
          addressCountry: 'BR'
        }
      : undefined,
    sameAs: shop.social_links?.map(link => link.url).filter(Boolean) || undefined
  }
})

if (import.meta.client) {
  let eventSource: EventSource | null = null
  const refreshTimer = setInterval(() => {
    refresh()
  }, 60_000)

  onMounted(() => {
    try {
      eventSource = new EventSource(apiPath('/storefront/stock/events/storefront/'), { withCredentials: true })
      eventSource.addEventListener('message', () => { refresh() })
      eventSource.addEventListener('stock-update', () => { refresh() })
    } catch {
      eventSource = null
    }
  })

  onBeforeUnmount(() => {
    clearInterval(refreshTimer)
    eventSource?.close()
  })
}

useHead(() => ({
  link: [
    { rel: 'preconnect', href: 'https://images.unsplash.com' }
  ],
  script: localBusinessJsonLd.value
    ? [{ type: 'application/ld+json', innerHTML: JSON.stringify(localBusinessJsonLd.value) }]
    : []
}))

useSeoMeta({
  title: () => pageTitle.value,
  description: () => home.value?.shop.description || ''
})
</script>

<template>
  <div>
    <UContainer v-if="pending" class="py-16">
      <USkeleton class="h-96 w-full" />
    </UContainer>

    <UContainer v-else-if="error" class="py-16">
      <UAlert
        color="error"
        variant="soft"
        :title="operationalCopy.loadFailure.home.title"
        :description="operationalCopy.loadFailure.home.description"
      />
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
