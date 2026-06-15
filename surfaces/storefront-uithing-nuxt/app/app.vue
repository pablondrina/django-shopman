<script setup lang="ts">
import type { HomeResponse } from '~/types/shopman'

const apiPath = useShopmanApiPath()
const session = useShopSession()
const { setFromServer } = useCartState()
const requestHeaders = import.meta.server ? useRequestHeaders(['cookie']) : undefined

const { data: shellHome } = await useFetch<HomeResponse>(apiPath('/api/v1/storefront/home/'), {
  credentials: 'include',
  headers: requestHeaders,
  key: 'shopman-shell-home'
})

watch(() => shellHome.value, value => {
  session.setFromHome(value?.home)
  setFromServer(value?.cart)
}, { immediate: true })

useShopTheme(session.shop)

// theme-color (tint da barra de URL) acompanha a navbar burgundy server-driven, nos
// dois modos. Sem marca / ?theme=neutral ⇒ default neutro (header claro).
const route = useRoute()
const themeColor = computed(() => {
  const value = route.query.theme
  const previewNeutral = (Array.isArray(value) ? value[0] : value) === 'neutral'
  if (previewNeutral) return '#85786c'
  return session.shop.value?.design_tokens?.theme_hex || '#85786c'
})

// SEO global: nome do site = marca server-driven (tenant-neutral, não theming).
// titleTemplate evita duplicar a marca na home (onde o título JÁ é a marca).
const brandName = computed(() => session.shop.value?.brand_name || 'Shopman')
useHead({
  titleTemplate: title => (title && title !== brandName.value ? `${title} | ${brandName.value}` : brandName.value)
})
useSeoMeta({
  ogSiteName: () => brandName.value,
  ogLocale: 'pt_BR',
  themeColor: () => themeColor.value
})

const globalHomeNotice = computed(() => session.homeNotices.value.find(notice => notice.priority === 'global') || null)
const shopStatusMessage = computed(() => globalHomeNotice.value?.message?.trim() || session.shopStatus.value?.message?.trim() || '')
</script>

<template>
  <div class="shop-shell flex min-h-dvh flex-col">
    <NuxtRouteAnnouncer />
    <a
      href="#main-content"
      class="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded-md focus:bg-primary focus:px-3 focus:py-2 focus:text-sm focus:font-medium focus:text-primary-foreground"
    >
      Pular para o conteúdo
    </a>
    <div v-if="shopStatusMessage" class="border-b bg-foreground px-4 py-2 text-center text-xs text-background">
      {{ shopStatusMessage }}
    </div>
    <ShopHeader />
    <div id="main-content" class="flex-1 min-h-[calc(100svh-4rem)]">
      <NuxtPage />
    </div>
    <ShopFooter />
    <AppBottomNav />
    <UiSonner />
  </div>
</template>
