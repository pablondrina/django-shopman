import type { ShopProjection } from '~/types/shopman'
import type { Ref } from 'vue'

export function useShopTheme (shop: Ref<ShopProjection | null>) {
  watchEffect(() => {
    if (!import.meta.client) return
    const root = document.documentElement
    for (const [name, value] of Object.entries(shopThemeStyle(shop.value))) {
      root.style.setProperty(name, value)
    }
  })
}
