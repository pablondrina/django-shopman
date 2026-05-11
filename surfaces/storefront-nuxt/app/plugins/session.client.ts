import type { HomeResponse } from '~/types/shopman'

export default defineNuxtPlugin(async () => {
  const { setFromHome } = useShopSession()
  const { setFromServer } = useCartState()
  const apiPath = useShopmanApiPath()

  try {
    const data = await $fetch<HomeResponse>(apiPath('/api/v1/storefront/home/'), {
      credentials: 'include'
    })
    setFromHome(data?.home)
    setFromServer(data?.cart)
  } catch {
    // session bootstrap is best-effort; fallbacks are anonymous
  }
})
