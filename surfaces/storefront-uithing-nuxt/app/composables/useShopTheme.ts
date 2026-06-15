import type { ShopProjection } from '~/types/shopman'
import type { Ref } from 'vue'

/**
 * Aplica a marca como camada de override sobre o base neutro, no SSR e no client
 * (sem FOUC): bloco `<style id="shop-theme">` (cores + `--font-sans`) e `<link>` das
 * fontes da marca. Reversibilidade:
 *   - sem `design_tokens` ⇒ bloco vazio + sem fontes ⇒ neutro pixel-idêntico;
 *   - `?theme=neutral` na URL ⇒ neutro ao vivo (A/B), sem tocar em dado.
 */
export function useShopTheme (shop: Ref<ShopProjection | null>) {
  const route = useRoute()
  const preview = computed(() => {
    const value = route.query.theme
    return Array.isArray(value) ? value[0] : value
  })

  useHead(() => ({
    style: [{ id: 'shop-theme', innerHTML: shopThemeCss(shop.value, { preview: preview.value }) }],
    link: shopFontLinks(shop.value, { preview: preview.value })
  }))
}
