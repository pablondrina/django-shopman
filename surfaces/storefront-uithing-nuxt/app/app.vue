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

watchEffect(() => {
  session.setFromHome(shellHome.value?.home)
  setFromServer(shellHome.value?.cart)
})

useShopTheme(session.shop)

const shellStyle = computed(() => shopThemeStyle(session.shop.value))
</script>

<template>
  <div class="shop-shell shop-bottom-safe" :style="shellStyle">
    <NuxtRouteAnnouncer />
    <ShopHeader />
    <NuxtPage />
    <CartDrawer />
    <AppBottomNav />
    <UiSonner />
  </div>
</template>
