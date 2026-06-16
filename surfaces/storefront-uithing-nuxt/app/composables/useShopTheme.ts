import type { ShopProjection } from '~/types/shopman'
import type { Ref } from 'vue'

/**
 * Aplica a marca como camada de override sobre o base neutro, no SSR e no client
 * (sem FOUC): bloco `<style id="shop-theme">` (cores + `--font-sans`) e `<link>` das
 * fontes da marca. Reversibilidade:
 *   - sem `design_tokens` ⇒ bloco vazio + sem fontes ⇒ neutro pixel-idêntico;
 *   - `?theme=neutral` na URL ⇒ neutro ao vivo (A/B), sem tocar em dado.
 *   - `?action=brass` na URL ⇒ A/B da cor de AÇÃO: `--primary` vira deep brass (Modelo B);
 *     sem o param, a ação é burgundy (Modelo A). Só preview, não toca em dado.
 */
export function useShopTheme (shop: Ref<ShopProjection | null>) {
  const route = useRoute()
  const firstQuery = (value: unknown) => (Array.isArray(value) ? value[0] : value) as string | undefined
  const preview = computed(() => firstQuery(route.query.theme))
  const action = computed(() => firstQuery(route.query.action))

  useHead(() => ({
    style: [{ id: 'shop-theme', innerHTML: shopThemeCss(shop.value, { preview: preview.value, action: action.value }) }],
    link: shopFontLinks(shop.value, { preview: preview.value })
  }))
}
