import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { formatCount } from '../app/utils/display'

const root = fileURLToPath(new URL('..', import.meta.url))
const surfaceRoots = ['app/pages', 'app/components']

function collectVueFiles (dir: string): string[] {
  const absolute = join(root, dir)
  const files: string[] = []
  for (const entry of readdirSync(absolute)) {
    const path = join(absolute, entry)
    const rel = relative(root, path)
    if (rel.startsWith('app/components/Ui')) continue
    if (statSync(path).isDirectory()) {
      files.push(...collectVueFiles(rel))
    } else if (path.endsWith('.vue')) {
      files.push(rel)
    }
  }
  return files
}

function read (path: string) {
  return readFileSync(join(root, path), 'utf8')
}

function templateOnly (source: string) {
  return source.match(/<template>([\s\S]*?)<\/template>/)?.[1] || ''
}

const surfaceVueFiles = surfaceRoots.flatMap(collectVueFiles)

describe('surface UX guardrails', () => {
  it('keeps native controls wrapped behind UI Thing components', () => {
    const offenders = surfaceVueFiles
      .filter(file => /<(button|input|select|textarea)\b/.test(read(file)))
      .map(file => relative(root, join(root, file)))

    expect(offenders).toEqual([])
  })

  it('does not expose architecture vocabulary or placeholder plurals in templates', () => {
    const forbidden = /\b(backend|projection|mutation|canonic|ChannelConfig|payload|idempotente|servidor)\b|item\(ns\)|pedido\(s\)|salvo\(s\)|Disponibilidade projetada|Total projetado|Busca, secoes/i
    const offenders = surfaceVueFiles
      .filter(file => forbidden.test(templateOnly(read(file))))
      .map(file => relative(root, join(root, file)))

    expect(offenders).toEqual([])
  })

  it('uses a single add-or-quantity action instead of zero-value steppers', () => {
    const addSurfaces = [
      'app/components/ProductTile.vue',
      'app/components/ProductDetailSheet.vue',
      'app/pages/index.vue',
      'app/pages/product/[sku].vue'
    ]
    for (const file of addSurfaces) {
      expect(read(file)).toContain('<CartQuantityAction')
      expect(read(file)).not.toContain('<QuantityControl')
      expect(read(file)).not.toMatch(/lucide:(plus|minus)/)
    }

    expect(read('app/components/CartQuantityAction.vue')).toContain('<QuantityControl')
    expect(read('app/components/CartDrawer.vue')).toContain('<QuantityControl')
  })

  it('does not revive stale projected quantities after cart removal', () => {
    const joined = surfaceVueFiles.map(read).join('\n')
    expect(joined).not.toMatch(/qtyForSku\([^)]*\)\s*\|\|\s*[^\n]*qty_in_cart/)
  })

  it('keeps storefront operational status sourced from shop_status', () => {
    const typeSource = read('app/types/shopman.ts')
    const omotenashiType = typeSource.match(/export interface OmotenashiProjection \{([\s\S]*?)\n\}/)?.[1] || ''

    expect(read('app/pages/index.vue')).not.toContain('home.omotenashi.is_open')
    expect(read('app/pages/index.vue')).toContain('home.value?.shop_status')
    expect(omotenashiType).not.toMatch(/\b(is_open|opens_at|closes_at)\b/)
  })

  it('syncs backend projections with explicit watch sources instead of self-tracking effects', () => {
    const forbidden = /watchEffect\(\s*\(\)\s*=>[\s\S]{0,320}\b(setFromHome|setFromAuthSession|setFromServer)\(/
    const offenders = surfaceVueFiles
      .filter(file => forbidden.test(read(file)))
      .map(file => relative(root, join(root, file)))

    expect(offenders).toEqual([])
  })

  it('does not render a second command search field in the menu', () => {
    expect(read('app/pages/menu.vue')).not.toContain('<UiCommandInput')
  })

  it('renders the menu product grid once instead of duplicating it in hidden tab panels', () => {
    const menu = read('app/pages/menu.vue')

    expect(menu).not.toMatch(/<UiTabsContent[\s\S]*?v-for=/)
    expect((menu.match(/<ProductTile/g) || [])).toHaveLength(1)
  })

  it('renders one active home hero panel instead of duplicating heavy hidden panels', () => {
    const hero = read('app/components/HomeHeroThing.vue')

    expect(hero).not.toMatch(/<UiTabsContent(?=[^>]*\bv-for=)/)
    expect(hero).toContain('activeSlide')
    expect(hero).toContain('v-if="activeSlide"')
  })

  it('keeps checkout authentication driven by the projection contract', () => {
    const checkout = read('app/pages/checkout.vue')
    const types = read('app/types/shopman.ts')

    expect(checkout).toContain('buildCheckoutPayload')
    expect(checkout).toContain('checkout.value.requires_authentication')
    expect(checkout).toContain('checkout.value?.auth_action')
    expect(checkout).toContain('navigateTo(authRoute.value)')
    expect(checkout).toContain('continueFromIdentity')
    expect(checkout).toContain('continueFromFulfillment')
    expect(checkout).toContain('fieldErrors.delivery_date')
    expect(checkout).toContain('state.delivery_date = localDateValue(today)')
    expect(checkout).toContain("activeStep === 'review'")
    expect(checkout).toContain('sticky bottom-20')
    expect(checkout).toContain('Total do pedido')
    expect(checkout).toContain('checkoutActionLabel')
    expect(checkout).toContain('Finalizar pedido')
    expect(checkout).not.toContain('Enviar pedido')
    expect(checkout).not.toContain('Compra sem senha')
    expect(types).toContain('requires_authentication: boolean')
    expect(types).toContain('auth_action: SurfaceActionProjection | null')
  })

  it('keeps checkout entry points visible before authentication', () => {
    const drawer = read('app/components/CartDrawer.vue')
    const bottomNav = read('app/components/AppBottomNav.vue')
    const header = read('app/components/ShopHeader.vue')
    const cartState = read('app/composables/useCartState.ts')
    const cartPage = read('app/pages/cart.vue')

    expect(cartState).toContain('if (qty > 0) drawerOpen.value = true')
    expect(drawer).toContain('Finalizar compra')
    expect(drawer).toContain('Total')
    expect(drawer).toContain('flex-1')
    expect(drawer).not.toContain('Continuar para checkout')
    expect(bottomNav).not.toContain("label: 'Finalizar'")
    expect(bottomNav).not.toContain("to: '/checkout'")
    expect(header).not.toContain("label: 'Finalizar'")
    expect(header).not.toContain("to: '/checkout'")
    expect(cartPage).toContain('Finalizar compra')
    expect(cartPage).toContain('sticky bottom-20')
  })

  it('keeps login copy and recovery actions projection-driven', () => {
    const login = read('app/pages/login.vue')

    expect(login).toContain("apiPath('/api/v1/storefront/home/')")
    expect(login).toContain('home.auth_copy')
    expect(login).toContain('home.public_config.whatsapp_url')
    expect(login).toContain('response.dev_console_hint')
    expect(login).toContain('response.debug_otp_code')
    expect(login).toContain('data-testid="debug-otp-alert"')
    expect(login).toContain('debugOtpCode = ref')
    expect(login).toContain('Codigo no terminal local')
    expect(login).toContain('as="h1"')
  })

  it('uses scaffolded UI Thing components for OTP, empty states and structured fields', () => {
    const login = read('app/pages/login.vue')
    const cartDrawer = read('app/components/CartDrawer.vue')
    const menu = read('app/pages/menu.vue')
    const productSheet = read('app/components/ProductDetailSheet.vue')
    const productRoute = read('app/pages/product/[sku].vue')

    expect(read('app/components/Ui/PinInput/PinInput.vue')).toContain('PinInputRoot')
    expect(read('app/components/Ui/Field/Field.vue')).toContain('data-slot="field"')
    expect(read('app/components/Ui/Empty/Empty.vue')).toContain('data-slot="empty"')
    expect(read('app/components/Ui/DescriptionList/DescriptionList.vue')).toContain('data-slot="description-list"')
    expect(read('app/components/Ui/ScrollArea/ScrollArea.vue')).toContain('ScrollAreaRoot')
    expect(read('app/components/Ui/ButtonGroup/ButtonGroup.vue')).toContain('data-slot="button-group"')

    expect(login).toContain('<UiPinInput')
    expect(login).toContain('<UiField')
    expect(login).toContain('<UiButtonGroup')
    expect(login).not.toContain('id="login-code" v-model="code"')
    expect(cartDrawer).toContain('<UiScrollArea')
    expect(cartDrawer).toContain('<UiEmpty')
    expect(menu).toContain('<UiEmpty')
    expect(productSheet).toContain('<UiDescriptionList')
    expect(productRoute).toContain('<UiDescriptionList')
  })

  it('keeps badges discreet and reserves success tone for explicit alerts', () => {
    const offenders = surfaceVueFiles
      .filter(file => /<UiBadge[^>]*variant="success"/.test(read(file)))
      .map(file => relative(root, join(root, file)))

    expect(offenders).toEqual([])
    expect(read('app/utils/display.ts')).toContain("availability === 'available') return 'secondary'")
    expect(read('app/utils/display.ts')).not.toContain("availability === 'available') return 'success'")
  })

  it('keeps the UI Thing theme surface-owned with taupe primary and compact radius', () => {
    const css = read('app/assets/css/tailwind.css')
    const config = read('ui-thing.config.ts')
    const theme = read('app/utils/shopTheme.ts')

    expect(config).toContain('"theme": "stone"')
    expect(css).toContain('--radius: 0.25rem')
    expect(css).toContain('--radius-xl: var(--radius)')
    expect(css).toContain('--primary: oklch(0.535 0.028 64.5)')
    expect(css).toContain('--font-sans: ui-sans-serif')
    expect(css).not.toContain('"Inter"')
    expect(css).toContain('@apply min-h-dvh min-w-0 bg-background text-foreground')
    expect(theme).toContain('--shop-brand-color')
    expect(theme).not.toContain('TOKEN_TO_CSS_VAR')
    expect(theme).not.toContain("style['--primary']")
  })

  it('does not shadow Vue refs in tracking after checkout navigation', () => {
    const tracking = read('app/pages/tracking/[ref].vue')

    expect(tracking).toContain('const orderRef = computed')
    expect(tracking).not.toContain('const ref = computed')
    expect(tracking).toContain('const rating = ref(5)')
  })

  it('prevents dead add-to-cart taps before client hydration', () => {
    const action = read('app/components/CartQuantityAction.vue')

    expect(action).toContain('const hydrated = ref(false)')
    expect(action).toContain('onMounted')
    expect(action).toContain('!hydrated.value')
    expect(action).toContain(':disabled="!hydrated || disabled || pending"')
  })

  it('serves the Thing surface locally under the same prefix used in staging', () => {
    const pkg = JSON.parse(read('package.json'))
    const smoke = read('scripts/ux-smoke.mjs')

    expect(pkg.scripts.dev).toContain('NUXT_APP_BASE_URL=/thing/')
    expect(smoke).toContain('http://127.0.0.1:3003/thing')
  })

  it('formats simple Portuguese counts without placeholder copy', () => {
    expect(formatCount(1, 'item', 'itens')).toBe('1 item')
    expect(formatCount(2, 'item', 'itens')).toBe('2 itens')
  })
})
