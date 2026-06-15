import type { ShopProjection } from '~/types/shopman'
import type { Ref } from 'vue'

/**
 * Aplica a marca como camada de override sobre o base neutro, no SSR e no client
 * (sem FOUC), via um único bloco `<style id="shop-theme">`. Reversibilidade:
 *   - sem `design_tokens` ⇒ bloco vazio ⇒ neutro pixel-idêntico;
 *   - `?theme=neutral` na URL ⇒ neutro ao vivo (A/B), sem tocar em dado.
 */
export function useShopTheme (shop: Ref<ShopProjection | null>) {
  const route = useRoute()
  const preview = computed(() => {
    const value = route.query.theme
    return Array.isArray(value) ? value[0] : value
  })

  const css = computed(() => shopThemeCss(shop.value, { preview: preview.value }))

  useHead({
    style: [{ id: 'shop-theme', innerHTML: () => css.value }]
  })
}
