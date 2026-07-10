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
      'app/pages/produto/[sku].vue'
    ]
    for (const file of addSurfaces) {
      expect(read(file)).toContain('<CartQuantityAction')
      expect(read(file)).not.toContain('<QuantityControl')
      expect(read(file)).not.toMatch(/lucide:(plus|minus)/)
    }

    expect(read('app/components/CartQuantityAction.vue')).toContain('<QuantityControl')
    expect(read('app/pages/sacola.vue')).toContain('<QuantityControl')
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
    expect(read('app/pages/index.vue')).toContain('contextualNotices')
    expect(read('app/pages/index.vue')).not.toContain("home.origin_channel === 'whatsapp'")
    expect(read('app/components/ShopHeader.vue')).toContain('statusLabel')
    expect(read('app/composables/useShopSession.ts')).toContain('homeNotices')
    expect(read('app/types/shopman.ts')).toContain('label: string')
    expect(read('app/types/shopman.ts')).toContain('export interface HomeNoticeProjection')
    expect(read('app/types/shopman.ts')).toContain('notices: HomeNoticeProjection[]')
    expect(read('app/pages/index.vue')).toContain("label: status?.label?.trim() || ''")
    expect(read('app/pages/index.vue')).not.toContain("label: isOpen ? 'Aberto agora' : 'Fechado agora'")
    expect(read('app/pages/index.vue')).not.toContain('v-if="operationalStatus.message"')
    expect(read('app/components/HomeHeroThing.vue')).not.toContain('omo.shop_hint')
    expect(omotenashiType).not.toMatch(/\b(is_open|opens_at|closes_at)\b/)
  })

  it('syncs backend projections with explicit watch sources instead of self-tracking effects', () => {
    const forbidden = /watchEffect\(\s*\(\)\s*=>[\s\S]{0,320}\b(setFromHome|setFromAuthSession|setFromServer)\(/
    const offenders = surfaceVueFiles
      .filter(file => forbidden.test(read(file)))
      .map(file => relative(root, join(root, file)))

    expect(offenders).toEqual([])
  })

  it('keeps search on its own full page, menu only links to it', () => {
    const menu = read('app/pages/menu.vue')
    const busca = read('app/pages/busca.vue')

    // O cardápio não tem campo de busca próprio: a lupa ABRE o overlay de busca
    // (mesma tela → foco/teclado confiável no iOS). A página /busca segue como fallback.
    expect(menu).not.toContain('<UiCommandInput')
    expect(menu).not.toContain('<UiCommand')
    expect(menu).not.toContain('<UiInput')
    expect(menu).not.toContain('searchPanelOpen')
    expect(menu).toContain('openSearch()')
    expect(menu).toContain('class="sr-only" aria-live="polite"')
    expect(menu).toContain('sectionOptions')
    expect(menu).toContain('filteredCount')
    expect(menu).toContain('uniqueItems')
    expect(menu).toContain('uniqueItemsBySku')
    expect(menu).toContain('sectionsBySku')
    expect(menu).toContain("from '~/presentation/menu'")
    // A página de busca é a dona da experiência (a la iFood).
    expect(busca).toContain('placeholder="Buscar no cardápio"')
    expect(busca).toContain('<UiInputGroup')
    expect(busca).toContain('searchPanelView')
    expect(busca).toContain('data-busca-collections')
    expect(busca).toContain('data-busca-filter-chips')
    expect(busca).toContain('data-busca-results')
    expect(busca).toContain('<ProductListItem')
    expect(busca).toContain(":aria-pressed=\"isFilterApplied(chip.key)\"")
    // Overlay de busca (mesma tela) reusa a mesma experiência/projeção da página.
    const overlay = read('app/components/SearchOverlay.vue')
    expect(overlay).toContain('useSearchOverlay')
    expect(overlay).toContain('searchPanelView')
    expect(overlay).toContain('<ProductListItem')
    expect(menu).toContain('filteredSections')
    expect(menu).not.toContain('function collectionSearchScore')
    expect(menu).not.toContain('function productSearchScore')
    expect(menu).not.toContain('function matchesProductAcrossCatalog')
    const menuPresentation = read('app/presentation/menu.ts')
    expect(menuPresentation).toContain('export function collectionSearchScore')
    expect(menuPresentation).toContain('export function productSearchScore')
    expect(menuPresentation).toContain('export function keywordSearchOptions')
    expect(menuPresentation).toContain('export function tileBadge')
    expect(menu).toContain('data-menu-filterbar')
    expect(menu).toContain('<main class="min-w-0">')
    expect(menu).toContain('<h1 class="sr-only">Cardápio</h1>')
    // O cardápio NÃO tem breadcrumb: a pill bar dourada (sticky, flush sob a navbar)
    // já ancora a página — um segundo bar dourado de breadcrumb somaria/duplicaria.
    expect(menu).not.toContain('<UiBreadcrumbs')
    // top-16 = altura da navbar (h-16). A status bar COLAPSA ao rolar (ShopHeader),
    // então o chrome sticky vira só a navbar → a pill bar gruda limpo na sua base.
    expect(menu).toContain('shop-pillbar sticky top-16 z-30 bg-background shadow-sm')
    expect(menu).not.toContain('bg-background/92')
    expect(menu).not.toContain('backdrop-blur supports-[backdrop-filter]:bg-background/78')
    expect(menu).not.toContain('[margin-left:calc(50%_-_50vw)]')
    expect(menu).not.toContain('<h1 class="text-2xl')
    expect(menu).toContain('data-menu-pillrail')
    expect(menu).toContain('data-menu-pill-ref')
    expect(menu).toContain('data-menu-pillrail-tail')
    expect(menu).toContain('pillRailTailWidth')
    expect(menu).toContain('nearDocumentEnd')
    expect(menu).toContain('@update:model-value="selectSection"')
    expect(menu).not.toContain('<UiListbox')
    expect(menu).not.toContain('Aplicar filtro')
    expect(menu).toContain('hasAppliedFilters')
    expect(menu).toContain('FILTERED_SECTION_VALUE')
    expect(menu).toContain('data-menu-clear-filter-pill')
    expect(menu).toContain("route.query.filtro")
    expect(menu).toContain("route.query.secao")
    expect(menuPresentation).toContain('export function itemMatchesAnyFilter')
    expect(menuPresentation).toContain("kind: 'collection'")
    expect(menuPresentation).toContain("kind: 'product'")
    expect(menuPresentation).toContain("kind: 'keyword'")
    expect(menu).toContain('lucide:funnel')
    expect(menu).toContain('<span v-if="hasAppliedFilters"')
    expect(menu).not.toContain('<UiItemGroup')
    expect(menu).not.toContain('hasAppliedProductFilter')
    expect(menu).not.toContain('sectionBySku.get(item.sku)?.label')
    expect(menu).not.toMatch(/return allItems\.value\s+\.filter\(item => matches\(item/)
    expect(menu).not.toContain('const count = allItems.value.filter')
    expect(menu).toContain('scrollToSection')
    expect(menu).toContain('syncActiveSectionFromScroll')
    expect(menu).toContain('data-menu-section-ref')
    expect(menu).not.toContain('sections.value.filter(section => section.ref === activeSection.value)')
  })

  it('renders the menu product grid once instead of duplicating it in hidden tab panels', () => {
    const menu = read('app/pages/menu.vue')

    expect(menu).not.toMatch(/<UiTabsContent[\s\S]*?v-for=/)
    expect((menu.match(/<ProductListItem/g) || [])).toHaveLength(1)
    expect(menu).not.toContain('<ProductTile')
  })

  it('uses canonical Card defaults intentionally for product media cards', () => {
    const productTile = read('app/components/ProductTile.vue')
    const home = read('app/pages/index.vue')

    expect(read('app/components/Ui/Card/Card.vue')).toContain('base: "bg-card text-card-foreground flex flex-col gap-6 rounded-lg border py-6 shadow-sm"')
    expect(read('app/components/Ui/AspectRatio.vue')).toContain('data-slot="aspect-ratio"')
    expect(read('app/components/Ui/AspectRatio.vue')).toContain('import { AspectRatio } from "reka-ui"')
    // ProductTile usa moldura vintage (retrato): paspatur branco recortado, sem UiCard.
    expect(productTile).toContain('data-product-tile')
    expect(productTile).toContain('shop-photo-frame')
    expect(productTile).toContain('shop-photo-mat')
    expect(productTile).toContain('<UiAspectRatio :ratio="4 / 3" class="overflow-hidden bg-muted">')
    expect(productTile).toContain('class="size-full object-cover"')
    expect(productTile).toContain(':to="productRoute(item.sku)"')
    expect(productTile).toContain(':aria-label="`Ver detalhes de ${item.name}`"')
    expect(productTile).toContain("import { tileBadge } from '~/presentation/menu'")
    // Indisponível = etiqueta neutra na foto (P&B); demais estados seguem tileBadge.
    expect(productTile).toContain('v-if="item.availability === \'unavailable\'"')
    expect(productTile).toContain('v-else-if="badge"')
    expect(productTile).not.toContain('<UiPopover')
    expect(productTile).not.toContain('availabilityVariant')
    expect(productTile).not.toContain('item.allergens.length || item.available_qty')
    expect(productTile).not.toContain('Alérgenos:')
    expect(productTile).not.toContain('<UiHoverCard')
    expect(productTile).not.toContain('Detalhes</UiButton>')
    expect(productTile).not.toContain('defineEmits')
    expect(productTile).not.toContain('lucide:info')
    expect(read('app/pages/menu.vue')).not.toContain('@select="openProduct"')
    expect(read('app/pages/menu.vue')).not.toContain('ProductDetailSheet')
    expect(read('app/pages/menu.vue')).not.toContain('detailOpen')
    expect(read('app/pages/menu.vue')).not.toContain('openProduct')
    expect(read('app/types/shopman.ts')).toContain('unit_weight_label: string | null')
    expect(read('app/utils/display.ts')).toContain('compactUnitWeightLabel')
    expect(productTile).toContain('compactUnitWeightLabel(item.unit_weight_label)')
    expect(productTile).toContain('class="flex flex-wrap items-end justify-between gap-x-3 gap-y-2"')
    expect(productTile).toContain('<div class="ml-auto shrink-0">')
    expect(productTile).not.toContain('<UiCardFooter class="mt-auto flex items-center justify-end gap-2')
    expect(read('app/pages/produto/[sku].vue')).toContain('{{ product.unit_weight_label }}')
    expect(read('app/pages/produto/[sku].vue')).toContain('compactUnitWeightLabel(product.unit_weight_label)')
    expect(home).toContain('<ProductTile')
    expect(home).toContain('v-for="item in featuredPreview"')
    expect(home).not.toContain('<UiCard v-for="item in featured')
    expect(home).not.toContain('<CartQuantityAction')
  })

  it('renders the home hero as a canonical carousel without a tabbed landing panel', () => {
    const hero = read('app/components/HomeHeroThing.vue')
    const home = read('app/pages/index.vue')

    expect(hero).not.toContain('<UiTabs')
    expect(hero).not.toContain('<UiTabsTrigger')
    expect(hero).not.toContain('<UiTabsContent')
    expect(hero).toContain('interface HeroSlide')
    expect(hero).toContain('const slides = computed<HeroSlide[]>')
    expect(hero).toContain("ref: 'birthday'")
    expect(hero).toContain("ref: 'order'")
    expect(hero).toContain("ref: 'reorder'")
    expect(hero).toContain("ref: 'handmade'")
    expect(hero).toMatch(/ref: 'greeting',\n\s+titleLines: \[greetingTitle\],\n\s+imageUrl/)
    expect(hero).toMatch(/ref: 'greeting-return',\n\s+titleLines: \[greetingTitle\],\n\s+imageUrl/)
    expect(hero).toContain('copy.reorder_title_prefix')
    expect(hero).toContain('copy.handmade_title_prefix')
    expect(hero).toContain('data-home-hero-carousel')
    expect(hero).toContain('aria-roledescription="carousel"')
    // Altura FIXA (não min-h): todos os slides ocupam o mesmo espaço (uniforme),
    // reservando header+busca+bottom-nav e ciente do safe-area inferior (notch).
    expect(hero).toContain('h-[calc(100svh-15.25rem-env(safe-area-inset-bottom,0px))]')
    expect(hero).toContain('-mx-4 overflow-hidden rounded-none')
    expect(hero).toContain('items-center justify-center')
    expect(hero).toContain('text-center text-white')
    expect(hero).toContain('activateNextSlide')
    expect(hero).toContain('UiButton')
    expect(home).toContain('<main class="bg-background">')
    expect(home).toContain('<section class="shop-section-cta bg-background pb-6 pt-0 sm:py-8 lg:py-10">')
    expect(home).toContain(':reorder-action="reorderAction"')
    expect(home).toContain('@reorder="handleReorder"')
    expect(home).toContain('sectionsCopy.availability_heading.title')
    expect(home).toContain('sectionsCopy.how_it_works_heading.title')
    expect(home).toContain('sectionsCopy.whatsapp_cta.title')
    expect(home).toContain('class="shop-section border-y bg-background pt-8 md:pt-10"')
    expect(home).toContain('id="como-funciona" class="shop-section bg-background scroll-mt-20"')
    expect(home).toContain('class="border-y bg-background py-0 sm:py-8 lg:py-10"')
    expect(home).toContain('class="relative -mx-4 overflow-hidden rounded-none bg-ink text-ink-foreground sm:mx-0 sm:rounded-lg"')
    expect(home).not.toContain('v-if="operationalStatus.message"')
    expect(home).toContain('data-home-reorder-card')
    expect(home).toContain('const quickReorderImageItem = computed')
    expect(home).toContain('<UiCard v-if="reorderAction || quickReorderItems.length" class="gap-0 overflow-hidden py-0" data-home-reorder-card>')
    expect(home).toContain('<div class="grid grid-cols-1 md:grid-cols-2">')
    expect(home).toContain('<UiAspectRatio :ratio="16 / 9" class="overflow-hidden bg-muted md:h-full">')
    expect(home).not.toContain('class="mx-auto max-w-3xl"')
    expect(home).not.toContain('filled')
    expect(home).not.toContain('Voltar ao que funcionou')
  })

  it('keeps checkout authentication driven by the projection contract', () => {
    const checkout = read('app/pages/finalizar.vue')
    const checkoutFlow = read('app/utils/checkoutFlow.ts')
    const types = read('app/types/shopman.ts')

    expect(checkout).toContain('buildCheckoutPayload')
    expect(checkout).toContain("from '~/utils/checkoutFlow'")
    // Gate de auth do checkout = middleware compartilhado (SSR, sem flash da tela gated);
    // a projection ainda dirige o auth_action (rota de login usada no "Trocar número").
    expect(checkout).toContain("definePageMeta({ middleware: 'account' })")
    expect(checkout).toContain('checkout.value?.auth_action')
    expect(checkout).toContain('navigateTo(authRoute)')
    expect(checkoutFlow).toContain("export type CheckoutStep = 'fulfillment' | 'address' | 'when' | 'payment'")
    expect(checkoutFlow).toContain('export function checkoutSteps')
    expect(checkoutFlow).toContain('export function checkoutStepState')
    expect(checkoutFlow).toContain('export function checkoutStepHeaderSummary')
    expect(checkoutFlow).toContain('export function reconciledPickupSlotRef')
    expect(checkout).toContain('validateContact')
    expect(checkout).toContain('contactEditing')
    expect(checkout).toContain('phoneDisplay')
    expect(checkout).toContain('data-checkout-contact-card')
    expect(checkout).not.toContain('id="checkout-phone"')
    expect(checkout).not.toContain('continueFromIdentity')
    expect(checkout).toContain('continueFromFulfillment')
    expect(checkout).toContain('continueFromAddress')
    expect(checkout).toContain('continueFromWhen')
    expect(checkout).toContain('continueFromPayment')

    // ADDRESS-UX-PLAN: o passo de endereço é o AddressPicker canônico —
    // sem input livre de endereço, sem radio duplicado no checkout.
    const addressPicker = read('app/components/AddressPicker.vue')
    expect(checkout).toContain('<AddressPicker')
    expect(checkout).toContain('v-model:selection="addressSelection"')
    expect(checkout).not.toContain('id="checkout-address"')
    expect(checkout).not.toContain('geocodeHere')
    expect(addressPicker).toContain("from '~/presentation/address'")
    expect(addressPicker).toContain('data-address-search')
    expect(addressPicker).toContain('data-address-locate')
    expect(addressPicker).toContain('data-address-geo-candidate')
    expect(addressPicker).toContain('data-address-adjust-map')
    // Etiqueta-depois vive no componente compartilhado AddressLabelSheet,
    // reusado pela conta e pelo checkout (pós-pedido).
    expect(addressPicker).toContain('<AddressLabelSheet')
    const labelSheet = read('app/components/AddressLabelSheet.vue')
    expect(labelSheet).toContain('data-address-label-sheet')
    expect(labelSheet).toContain('Agora não')
    expect(checkout).toContain('<AddressLabelSheet')
    expect(checkout).toContain('findNewlySavedAddress')
    expect(checkout).toContain('fieldErrors.delivery_date')
    // Default = primeira data disponível do backend (nunca dia fechado).
    expect(checkout).toContain('checkout.value?.available_dates?.[0]')
    expect(checkout).toContain('closed_weekdays')
    expect(checkout).not.toContain("type Step = 'identity'")
    expect(checkout).toContain('data-checkout-progress-stack')
    expect(checkout).toContain('data-checkout-step="fulfillment"')
    expect(checkout).toContain('data-checkout-step="address"')
    expect(checkout).toContain('data-checkout-step="when"')
    expect(checkout).toContain('data-checkout-step="payment"')
    expect(checkout).not.toContain('<UiTabsContent value="review">')
    expect(checkout).not.toContain('<UiTabs')
    expect(checkout).not.toContain('<UiStepper')
    // Confirmação do PEDIDO é o bottom-sheet canônico (BottomSheet). UiAlertDialog é
    // permitido para confirmações destrutivas pontuais (trocar telefone).
    expect(checkout).toContain('changePhoneOpen')
    expect(checkout).toContain('confirmOpen')
    expect(checkout).toContain('openConfirmSheet')
    expect(checkout).toContain('<BottomSheet')
    expect(checkout).toContain('v-model:open="confirmOpen"')
    const bottomSheet = read('app/components/BottomSheet.vue')
    expect(bottomSheet).toContain('side="bottom"')
    expect(bottomSheet).toContain('variant="floating"')
    expect(checkout).toContain('<CheckoutProgressSection')
    expect(checkout).toContain('stepState')
    expect(read('app/components/CheckoutProgressSection.vue')).toContain(':data-checkout-section-state="state"')
    expect(checkout).toContain('<UiRadioGroup v-model="state.fulfillment_type" class="grid gap-2 sm:grid-cols-2">')
    expect(checkout).toContain('<UiRadioGroup v-model="state.payment_method" class="grid gap-2 sm:grid-cols-2">')
    expect(checkout).toContain('<UiFieldLabel v-if="availableFulfillment.includes(\'pickup\')" for="checkout-fulfillment-pickup" class="bg-card')
    expect(checkout).toContain('<UiFieldLabel v-for="method in paymentMethods"')
    expect(checkout).toContain('<UiField orientation="horizontal">')
    expect(checkout).toContain('<UiFieldContent class="gap-1">')
    expect(checkout).toContain('paymentIcon(method.ref)')
    expect(checkout).toContain('{{ method.label }}')
    expect(checkout).not.toContain('class="flex gap-3 rounded-lg border p-4"')
    expect(checkout).not.toContain('<label v-for="method in paymentMethods"')
    expect(checkout).toContain('Confirmar pedido')
    expect(checkout).toContain('confirmItemSummary')
    expect(checkout).toContain('paymentMethodLabel')
    expect(checkout).toContain('fulfillmentSummary')
    expect(checkout).toContain('data-checkout-live-summary')
    expect(checkout).toContain('<CartSummaryBreakdown v-if="cart" :cart="cart" compact />')
    expect(checkout).not.toContain('sticky bottom-20')
    expect(checkout).toContain('Total do pedido')
    expect(checkout).toContain('checkoutActionLabel')
    expect(checkout).toContain('Revisar pedido')
    expect(checkout).not.toContain('Enviar pedido')
    expect(checkout).not.toContain('Compra sem senha')
    expect(types).toContain('requires_authentication: boolean')
    expect(types).toContain('auth_action: Action | null')
    // Telefone editorial formatado (não cru/truncado), assumindo o DDD padrão da
    // loja (fim do "(55) …" e do número sem máscara), e poka-yoke fora de área.
    expect(checkout).toContain('displayBrazilianPhone')
    expect(checkout).toContain('default_ddd')
    expect(checkout).toContain('shouldOfferPickupSwap')
    expect(checkout).toContain('data-checkout-pickup-swap')
    expect(checkout).toContain('Mudar para retirada')
  })

  it('keeps checkout entry points visible before authentication', () => {
    const app = read('app/app.vue')
    const bottomNav = read('app/components/AppBottomNav.vue')
    const header = read('app/components/ShopHeader.vue')
    const cartState = read('app/composables/useCartState.ts')
    const cartPage = read('app/pages/sacola.vue')
    const home = read('app/pages/index.vue')
    const types = read('app/types/shopman.ts')
    const reorder = read('app/composables/useReorder.ts')

    expect(types).toContain('actions: Action[]')
    expect(app).not.toContain('<CartDrawer')
    expect(cartState).not.toContain('drawerOpen')
    // Indisponibilidade (409) NÃO navega: o SubstituteSheet global sobe no lugar,
    // no momento exato do problema (menu/PDP/sacola). Reorder ainda navega (sucesso).
    expect(cartState).not.toContain("navigateTo('/sacola')")
    expect(app).toContain('<SubstituteSheet')
    expect(reorder).not.toContain('drawerOpen')
    expect(reorder).toContain("await navigateTo('/sacola')")
    expect(bottomNav).not.toContain("label: 'Finalizar'")
    expect(bottomNav).not.toContain("to: '/finalizar'")
    expect(bottomNav).toContain("to: '/sacola'")
    expect(bottomNav).not.toContain('drawerOpen')
    expect(bottomNav).toContain('cartPulse')
    expect(bottomNav).toContain('scale-125 ring-2 ring-primary/25')
    expect(header).not.toContain("label: 'Finalizar'")
    expect(header).not.toContain("to: '/finalizar'")
    expect(header).toContain('to="/sacola"')
    expect(header).toContain('aria-label="Ver sacola"')
    expect(header).toContain('cartPulse')
    // Logo centralizado: sacola (badge) sempre visível à direita — não mais só no desktop.
    expect(header).toContain('lucide:shopping-bag')
    expect(header).toContain('<header class="shop-header-bar sticky top-0 z-40">')
    // Barra utilitária: horário + ligar em 1 toque (omotenashi).
    expect(header).toContain('lucide:clock')
    expect(header).toContain('lucide:phone')
    // Hambúrguer (esq) abre um menu que BROTA verticalmente sob a navbar — seção
    // full-width em fundo da marca, lista estilo busca (decisão Pablo 2026-06-16).
    // A bottom-nav segue como navegação primária no mobile.
    expect(header).toContain('id="shop-menu-panel"')
    expect(header).toContain('data-shop-menu-panel')
    expect(header).toContain('Transition name="shop-menu-drop"')
    expect(header).toContain('aria-expanded="menuOpen"')
    expect(header).toContain('data-shop-menu-trigger')
    expect(header).toContain("'lucide:x' : 'lucide:menu'") // gatilho alterna menu↔x via <Icon>
    expect(header).toContain('Como funciona')
    expect(header).toContain('Redes sociais')
    expect(bottomNav).toContain("to: '/menu'")
    expect(bottomNav).toContain("to: '/conta'")
    expect(header).not.toContain('shopping-basket')
    expect(header).not.toContain('session.shop.value?.tagline')
    expect(header).not.toContain('Compra rápida e acompanhada')
    expect(home).not.toContain('fixed bottom-20 right-4')
    expect(home).not.toContain('@click="drawerOpen = true"')
    expect(cartPage).toContain("action.ref === 'checkout'")
    expect(cartPage).toContain("checkoutAction?.label || 'Finalizar pedido'")
    expect(cartPage).toContain('<CartSummaryBreakdown :cart="cart" flat />')
    expect(cartPage).toContain('sticky bottom-20')
    expect(cartPage).toContain('rateLimitRecovery')
    // Indisponibilidade + substitutos saíram do banner inline da sacola e viraram
    // o SubstituteSheet global (bottom-sheet canônico, 1 toque, dispensável).
    const substituteSheet = read('app/components/SubstituteSheet.vue')
    expect(substituteSheet).toContain('data-substitute-sheet')
    expect(substituteSheet).toContain('<BottomSheet')
    expect(substituteSheet).toContain('addSubstitute')
    expect(substituteSheet).toContain('acceptAvailableQty')
    expect(substituteSheet).toContain('retryLastMutation')
    expect(substituteSheet).toContain('dismissCartIssue')
    expect(substituteSheet).toContain('Agora não')
    expect(cartPage).not.toContain(':disabled="cart.is_empty || cart.has_unavailable_items"')
  })

  it('keeps mobile product add controls explicit before switching to quantity editing', () => {
    const action = read('app/components/CartQuantityAction.vue')
    const quantity = read('app/components/QuantityControl.vue')
    const productRoute = read('app/pages/produto/[sku].vue')
    const cartState = read('app/composables/useCartState.ts')
    const smoke = read('scripts/ux-smoke.mjs')

    expect(action).toContain('addTargetQty')
    expect(action).toContain("tone?: 'default' | 'inverted'")
    expect(action).toContain("const nextQty = props.addTargetQty ?? 1")
    // tone="inverted" = ação SOBRE o card escuro flutuante (CTA fixo mobile) → botão
    // Faubourg + texto Brass escuro (.shop-action-inverted), em vez do secondary/kraft.
    expect(action).toContain("tone === 'inverted' ? 'shop-action-inverted' : ''")
    // Pílula opaca (padrão iFood): nunca campo de form transparente sobre foto/CTA.
    expect(quantity).toContain('rounded-full border bg-background text-foreground shadow-sm')
    expect(quantity).toContain("tone === 'inverted' ? 'shop-qty-inverted' : ''")
    expect(quantity).not.toContain('<UiNumberField')
    // CTA sticky honesto: pílula com a qty real do carrinho, sem estado fantasma.
    expect(productRoute).not.toContain('mobileCtaTouched')
    // CTA flutuante mobile = card ink (burgundy escuro) + ação invertida (Faubourg/Brass escuro).
    expect(productRoute).toContain('sticky bottom-20 z-30 mt-4 rounded-lg border border-ink bg-ink p-3 text-ink-foreground shadow-lg md:hidden')
    expect(productRoute).toContain(':qty="currentQty"')
    expect(productRoute).toContain('tone="inverted"')
    expect(cartState).not.toContain('drawerOpen')
    expect(smoke).toContain('cart page entry point should remain visible after add')
  })

  it('renders a projection-driven web footer in the shell', () => {
    const app = read('app/app.vue')
    const footer = read('app/components/ShopFooter.vue')
    const session = read('app/composables/useShopSession.ts')

    expect(app).toContain('<ShopFooter')
    expect(app).toContain('id="main-content"')
    expect(app).toContain('Pular para o conteúdo')
    expect(read('app/components/ShopHeader.vue')).toContain('bg-ink text-ink-foreground')
    expect(footer).toContain('session.shop.value')
    expect(footer).toContain('session.openingHours.value')
    expect(footer).not.toContain('openingHours.slice')
    // Rodapé em tom médio-escuro neutro; texto secundário via opacity.
    // O safe-padding do bottom-nav vive NO footer (faixa fica escura, não clara).
    expect(footer).toContain('<footer class="shop-footer shop-bottom-safe">')
    expect(read('app/app.vue')).not.toContain('shop-bottom-safe')
    expect(footer).not.toContain('bg-muted/40')
    expect(footer).not.toContain('text-muted-foreground')
    expect(footer).toContain('Falar no WhatsApp')
    expect(session).toContain('openingHours')
  })

  it('keeps login copy and recovery actions projection-driven', () => {
    const login = read('app/pages/entrar.vue')
    const authPhone = read('app/utils/authPhone.ts')
    const authPresentation = read('app/presentation/auth.ts')

    expect(login).toContain("apiPath('/api/v1/storefront/home/')")
    expect(login).toContain('home.auth_copy')
    expect(login).toContain('home.public_config.whatsapp_url')
    expect(login).toContain('const isCheckoutReturn')
    expect(login).toContain('const stepTitle')
    expect(login).toContain('const stepDescription')
    expect(login).toContain('<UiInputGroup class="bg-background">')
    expect(login).toContain('<UiInputGroupAddon align="inline-start">')
    expect(login).toContain('<UiInputGroupInput')
    expect(login).toContain('name="phone"')
    expect(login).toContain('phoneRegion')
    expect(login).toContain('togglePhoneRegion')
    expect(login).toContain('authPhonePayload')
    expect(authPhone).toContain('phone_region')
    expect(authPhone).toContain('phone_normalized')
    expect(authPhone).toContain('target')
    // WhatsApp = login por access link (deep link pré-aquecido no pai, sem polling/SSE);
    // SMS = fallback OTP push. O CTA é o próprio deep link (<a href>) no painel
    // apresentacional; o pai pré-aquece via waStart no mount (uma tela só).
    expect(login).toContain('useWhatsappVerify()')
    expect(login).toContain('<WhatsappVerifyPanel')
    expect(login).toContain(':deep-link="waDeepLink"')
    expect(login).toContain("requestCode('sms', $event)")
    expect(login).toContain('class="w-full justify-center"')
    expect(login).toContain('<UiFieldLabel for="trusted-device" class="w-full">')
    expect(login).not.toContain('<UiButtonGroup')
    expect(login).not.toContain('max-w-xl')
    expect(login).not.toContain('class="rounded-md border p-3"')
    expect(login).toContain('response.dev_console_hint')
    expect(login).toContain('response.debug_otp_code')
    expect(login).toContain('data-testid="debug-otp-alert"')
    expect(login).toContain('debugOtpCode = ref')
    expect(login).toContain('Código no terminal local')
    // Login editorial: passos direto no background (sem card), h1 semântico,
    // máquina de passos/erros em presentation/auth.ts.
    expect(login).not.toContain('<UiCard')
    expect(login).toContain('<h1 class="shop-title">')
    expect(login).toContain("from '~/presentation/auth'")
    expect(authPresentation).toContain('export function authStep')
    expect(authPresentation).toContain('export function authErrorView')
    expect(authPresentation).toContain('export function resendCooldown')
    expect(authPresentation).toContain('export function welcomeNameValue')
    // Rate limit é recuperação calma (sem banner vermelho); reenviar tem cooldown.
    expect(login).toContain("error.kind === 'rate_limit'")
    expect(login).toContain('data-login-resend')
    expect(login).toContain('Reenviar código')
    expect(login).toContain('Trocar telefone')
    // Polish pass aprovado (2026-06-12): máscara BR no input, telefone legível,
    // TTL do código visível, foco segue o passo, momentos de feedback antes do
    // redirect (copy do servidor), tela sem breadcrumb (foco vence).
    expect(login).toContain('maskPhoneInput')
    expect(login).toContain('requestedPhoneDisplay')
    expect(login).toContain('code_expires_at')
    expect(login).toContain('Vale até')
    expect(login).toContain("watch(step, async next => {")
    expect(login).toContain('data-login-moment')
    expect(login).toContain('device_trust_redirecting')
    expect(login).toContain('device_trust_saved')
    expect(login).toContain('O código não chegou?')
    expect(login).toContain('Falar com a loja')
    expect(login).not.toContain('<UiBreadcrumbs')
    // Visual aprovado (2026-06-12): PIN sem placeholder "0" fantasma; telefone
    // não quebra no meio; CTAs principais ≥40px; confiar-no-aparelho é linha
    // editorial (hairlines) com switch, não caixa com checkbox.
    expect(login).not.toContain('placeholder="0"')
    expect(login).toContain('whitespace-nowrap font-semibold tabular-nums')
    expect(login).toContain('size="lg"')
    expect(login).toContain('data-login-trust')
    expect(login).toContain('<UiSwitch id="trusted-device"')
    expect(login).not.toContain('<UiCheckbox')
    // Welcome gate omotenashi: nome via PATCH profile, com saída discreta.
    expect(login).toContain('requires_welcome')
    expect(login).toContain('welcome_suggested_name')
    expect(login).toContain("apiPath('/api/v1/account/profile/')")
    expect(login).toContain('data-login-welcome')
    expect(login).toContain('Deixar para depois')
    // Device trust e ajuda continuam server-driven/editorial.
    expect(login).toContain('device_trust_prompt')
    expect(login).toContain('data-login-support')
  })

  it('uses scaffolded UI Thing components for OTP, empty states and structured fields', () => {
    const login = read('app/pages/entrar.vue')
    const menu = read('app/pages/menu.vue')
    const productRoute = read('app/pages/produto/[sku].vue')
    const upsellRail = read('app/components/CartUpsellRail.vue')
    const cartPage = read('app/pages/sacola.vue')

    expect(read('app/components/Ui/PinInput/PinInput.vue')).toContain('PinInputRoot')
    expect(read('app/components/Ui/Field/Field.vue')).toContain('data-slot="field"')
    expect(read('app/components/Ui/Empty/Empty.vue')).toContain('data-slot="empty"')
    expect(read('app/components/Ui/DescriptionList/DescriptionList.vue')).toContain('data-slot="description-list"')
    expect(read('app/components/Ui/ScrollArea/ScrollArea.vue')).toContain('ScrollAreaRoot')
    expect(read('app/components/Ui/InputGroup/InputGroup.vue')).toContain('data-slot="input-group"')

    expect(login).toContain('<UiPinInput')
    expect(login).toContain('<UiField')
    expect(login).toContain('<UiInputGroup')
    expect(login).not.toContain('id="login-code" v-model="code"')
    expect(cartPage).toContain('<UiEmpty')
    expect(menu).toContain('<UiEmpty')
    // PDP editorial: informação direto no background, sem card branco.
    expect(productRoute).not.toContain('<UiCard')
    // Acordeão full-width no mobile: hairlines ponta a ponta; trigger alinhado
    // ao título e interior aberto com recuo extra (+16px sobre o trigger).
    expect(productRoute).toContain('class="-mx-4 mt-6 border-t sm:-mx-6 lg:mx-0 [&_[data-slot=accordion-trigger]]:font-semibold sm:[&_[data-slot=accordion-trigger]]:px-6 lg:[&_[data-slot=accordion-trigger]]:px-0 [&_[data-slot=accordion-content]>div]:px-8 sm:[&_[data-slot=accordion-content]>div]:px-10 lg:[&_[data-slot=accordion-content]>div]:px-4"')
    expect(productRoute).toContain('data-product-cross-sell')
    expect(productRoute).toContain('Talvez você também goste')
    expect(productRoute).toContain('<ProductListItem')
    expect(productRoute).toContain('% VD')
    expect(upsellRail).toContain('<UiItem variant="outline" size="sm" class="w-full items-stretch gap-3 rounded-none border-0 bg-card p-3">')
    expect(upsellRail).toContain('<UiItemHeader>')
    expect(upsellRail).toContain('function productRoute (sku: string)')
    expect(upsellRail).toContain(':to="productRoute(upsell.sku)"')
    expect(upsellRail).toContain('class="block w-full rounded-md"')
    expect(upsellRail).toContain(':aria-label="`Ver detalhes de ${upsell.name}`"')
    expect(upsellRail).toContain('<UiItemMedia v-if="upsell.image_url" variant="image"')
    expect(upsellRail).toContain('aspect-[4/3]')
    expect(upsellRail).toContain('<UiItemFooter class="w-full">')
    expect(upsellRail).toContain('<div class="w-full [&>button]:w-full">')
    expect(upsellRail).toContain('<CartQuantityAction')
  })

  it('keeps cart lines editable with explicit remove instead of hidden decrement removal', () => {
    const cartPage = read('app/pages/sacola.vue')
    const quantity = read('app/components/QuantityControl.vue')

    expect(quantity).toContain('minQty')
    expect(cartPage).toContain(':min-qty="1"')
    expect(cartPage).toContain('removeLine(line)')
    // Carrinho editorial: linhas com hairline direto no background, sem cards.
    expect(cartPage).toContain('data-cart-line-item')
    expect(cartPage).not.toContain('<UiCard')
    expect(cartPage).toContain('icon="lucide:trash-2"')
    expect(cartPage).toContain(':aria-label="`Remover ${line.name}`"')
    // Lixeira sempre viva: mutações otimistas não bloqueiam remoção.
    expect(cartPage).not.toContain(':disabled="cart.summary_pending"')
    expect(cartPage).toContain('{{ line.qty }} × {{ line.price_display }} cada')
    expect(cartPage).toContain('{{ line.total_display }}')
    expect(cartPage).toContain('<CartUpsellRail v-if="cart.upsell"')
    // Planned-hold transparente: badges por linha + banner com countdown.
    expect(cartPage).toContain('data-cart-line-awaiting')
    expect(cartPage).toContain('data-cart-line-ready')
    expect(cartPage).toContain('data-cart-hold-banner')
    expect(cartPage).toContain('Aguardando confirmação')
    expect(cartPage).toContain('Tudo pronto! Confirme')
    expect(cartPage).toContain('Tempo restante:')
  })

  it('shows coupon savings as signed discounts without losing the original subtotal', () => {
    const summary = read('app/components/CartSummaryBreakdown.vue')
    const cartPage = read('app/pages/sacola.vue')
    const checkout = read('app/pages/finalizar.vue')

    expect(summary).toContain("import type { CartProjection } from '~/types/shopman'")
    expect(summary).toContain('cart.has_discount')
    // KISS: Subtotal = valor CHEIO (pré-desconto), sem risco. Descontos vêm depois
    // como linhas assinadas; a conta fecha (Subtotal − Descontos = Total). Nada de
    // strikethrough nem subtotal duplicado (confundia: desconto aparecia 2x).
    expect(summary).toContain('cart.original_subtotal_display')
    expect(summary).not.toContain('line-through')
    expect(summary).toContain('discountDisplay(discount.amount_display)')
    expect(summary).toContain("return value.startsWith('-') ? value : `- ${value}`")
    expect(cartPage).not.toContain('{{ cart.subtotal_display }}</span>')
    // Cupom mora no CHECKOUT (decisão Pablo 2026-06-16), não mais no carrinho —
    // aplicar/remover via cart state + refresh() do payload do checkout.
    expect(cartPage).not.toContain('data-cart-coupon')
    expect(checkout).toContain('data-checkout-coupon')
    // Cupom = toggle-card único: aplicado vira "Cupom XYZ aplicado" (toggle ON);
    // desligar o toggle remove (onCouponToggle → dropCoupon).
    expect(checkout).toContain('{{ cart.coupon_code }}')
    expect(checkout).toContain('onCouponToggle')
    expect(checkout).toContain('await applyCoupon(coupon.value.trim())')
    expect(checkout).toContain('await refresh()')
  })

  it('keeps account logic in the pure presentation layer and guards every sub-page', () => {
    // Arc 9: conta deixa de ser monólito de tabs; vira hub + sub-páginas, com a
    // lógica pura (fidelidade, navegação, ícone de aparelho) em presentation/account.ts.
    const presentation = read('app/presentation/account.ts')
    expect(presentation).toContain('export function loyaltyView')
    expect(presentation).toContain('export function loyaltyStampSlots')
    expect(presentation).toContain('export function accountNavCards')
    expect(presentation).toContain('export function deviceIcon')
    expect(presentation).toContain('export function reorderActionFrom')
    expect(presentation).toContain('export function ordersEmptyCopy')

    // Guarda de auth compartilhada — sem fetch de sessão duplicado por página.
    const guard = read('app/middleware/account.ts')
    expect(guard).toContain('defineNuxtRouteMiddleware')
    expect(guard).toContain("apiPath('/api/auth/session/')")
    expect(guard).toContain('navigateTo(`/entrar?next=')
    for (const page of ['index', 'pedidos', 'enderecos', 'perfil', 'preferencias', 'seguranca']) {
      expect(read(`app/pages/conta/${page}.vue`)).toContain("definePageMeta({ middleware: 'account' })")
    }
  })

  it('uses Field + reka modelValue switches for preferences and Item for trusted devices', () => {
    const prefs = read('app/pages/conta/preferencias.vue')
    expect(prefs).toContain('<UiFieldLegend>Preferências alimentares</UiFieldLegend>')
    expect(prefs).toContain('orientation="horizontal"')
    expect(prefs).toContain('<UiSwitch')
    // reka 2.x: modelValue/update:model-value, NUNCA :checked/@update:checked.
    expect(prefs).toContain(':model-value="pref.is_active"')
    expect(prefs).toContain('@update:model-value="toggleFood(pref)"')
    expect(prefs).toContain(':model-value="pref.enabled"')
    expect(prefs).toContain('@update:model-value="toggleNotification(pref)"')
    expect(prefs).toContain('v-for="pref in summary?.food_preferences || []"')
    expect(prefs).toContain('v-for="pref in summary?.notification_preferences || []"')
    expect(prefs).not.toContain(':checked')
    expect(prefs).not.toContain('@update:checked')

    const security = read('app/pages/conta/seguranca.vue')
    expect(security).toContain("apiPath('/api/v1/account/devices/')")
    expect(security).toContain("apiPath('/api/v1/account/export/')")
    expect(security).toContain("apiPath('/api/v1/account/delete/')")
    expect(security).toContain('deleteAccountAcknowledged')
    expect(security).toContain('Exportar meus dados')
    expect(security).toContain('Excluir minha conta')
    expect(security).toContain('<UiItem v-for="device in accountDevices" :key="device.id" variant="outline" class="bg-card">')
    expect(security).toContain('<UiItemMedia variant="icon"')
    expect(security).toContain(':name="deviceIcon(device.label)"')
    expect(security).toContain('askRevokeDevice(device)')
    expect(security).toContain('confirmRevokeDevice')

    const profile = read('app/pages/conta/perfil.vue')
    expect(profile).toContain("apiPath('/api/v1/account/profile/')")
    expect(profile).toContain('saveProfile')
    expect(profile).toContain('Salvar perfil')
  })

  it('lets authenticated customers manage addresses through the canonical AddressPicker', () => {
    const account = read('app/pages/conta/enderecos.vue')

    expect(account).toContain("apiPath('/api/v1/account/addresses/')")
    expect(account).toContain('refresh: refreshAddresses')
    expect(account).toContain('openCreateAddress')
    expect(account).toContain('openEditAddress(address)')
    expect(account).toContain('setDefaultAddress(address)')
    expect(account).toContain('askDeleteAddress(address)')
    expect(account).toContain('deleteAddress')
    expect(account).toContain("method: 'DELETE'")
    expect(account).toContain('<BottomSheet')
    expect(account).toContain('v-model:open="addressSheetOpen"')
    expect(account).toContain('<UiAlertDialog v-model:open="addressDeleteOpen">')
    // ADDRESS-UX-PLAN: componente único — a conta não duplica formulário.
    expect(account).toContain('<AddressPicker')
    expect(account).toContain('context="account"')
    expect(account).toContain(':editing-address="addressEditing"')
    expect(account).not.toContain('addressForm')
    expect(account).not.toContain('saveAddress')
    expect(account).toContain('Adicionar endereço')
    // Títulos do sheet (Adicionar/Editar) vêm da presentation pura.
    expect(account).toContain('addressSheetTitle(addressMode.value)')
    expect(read('app/presentation/account.ts')).toContain("return mode === 'create' ? 'Adicionar endereço' : 'Editar endereço'")
    expect(account).not.toMatch(/<(button|input|select|textarea)\b/)
  })

  it('drives SEO from the pure presentation layer (JSON-LD + canonical server-side)', () => {
    // SEO técnico mora em presentation/seo.ts (puro, testado), consumido por
    // PDP/home no SSR — canonical via useRequestURL, JSON-LD schema.org.
    const seo = read('app/presentation/seo.ts')
    expect(seo).toContain('export function productJsonLd')
    expect(seo).toContain('export function bakeryJsonLd')
    expect(seo).toContain('export function breadcrumbJsonLd')
    expect(seo).toContain("'@type': 'Product'")
    expect(seo).toContain("'@type': 'Bakery'")

    const pdp = read('app/pages/produto/[sku].vue')
    expect(pdp).toContain("from '~/presentation/seo'")
    expect(pdp).toContain('useRequestURL()')
    expect(pdp).toContain("rel: 'canonical'")
    expect(pdp).toContain('productJsonLd(')
    expect(pdp).toContain('breadcrumbJsonLd(')
    expect(pdp).toContain('application/ld+json')

    const home = read('app/pages/index.vue')
    expect(home).toContain('bakeryJsonLd(')
    expect(home).toContain("rel: 'canonical'")
  })

  it('keeps badges discreet and reserves success tone for explicit alerts', () => {
    const offenders = surfaceVueFiles
      .filter(file => /<UiBadge[^>]*variant="success"/.test(read(file)))
      .map(file => relative(root, join(root, file)))

    expect(offenders).toEqual([])
    expect(read('app/utils/display.ts')).toContain("availability === 'available') return 'secondary'")
    expect(read('app/utils/display.ts')).not.toContain("availability === 'available') return 'success'")
  })

  it('keeps destructive promise alerts readable instead of full red banners', () => {
    const tracking = read('app/pages/pedido/[ref]/index.vue')
    const payment = read('app/pages/pedido/[ref]/pagamento.vue')
    const css = read('app/assets/css/tailwind.css')

    expect(css).toContain('--destructive-foreground: oklch(0.985 0 0)')
    expect(tracking).toContain('variant="default"')
    expect(tracking).toContain(':class="statusPanelClass"')
    // Ícone do painel pulsa (animate-pulse) em pedido ativo — sinal "ao vivo" sem
    // bolinha extra; a classe base vem do tom (statusPanelIconClass) via a live.
    expect(tracking).toContain(':icon-class="statusPanelIconClassLive"')
    expect(tracking).toContain('animate-pulse')
    // Tracking: tom→classe/ícone do painel agora vive em presentation/orderTracking.ts;
    // o acento na borda esquerda (não banner cheio) permanece a regra.
    const trackingPresentation = read('app/presentation/orderTracking.ts')
    expect(trackingPresentation).toContain('border-l-4 border-border border-l-destructive bg-card text-foreground shadow-sm')
    expect(trackingPresentation).toContain("if (tone === 'danger') return 'lucide:triangle-alert'")
    // Pagamento: tom→variante/preenchimento agora vive em presentation/payment.ts.
    // O contorno (não preenchido) para danger permanece a regra.
    expect(payment).toContain(':filled="paymentAlertFilled(payment.promise.tone)"')
    expect(payment).toContain(':icon="paymentAlertIcon(payment.promise.tone)"')
    const paymentPresentation = read('app/presentation/payment.ts')
    expect(paymentPresentation).toContain("return tone !== 'danger'")
    expect(paymentPresentation).toContain("if (tone === 'danger') return 'lucide:triangle-alert'")
  })

  it('does not submit projected sensitive actions without idempotency when declared', () => {
    const tracking = read('app/pages/pedido/[ref]/index.vue')
    const payment = read('app/pages/pedido/[ref]/pagamento.vue')

    for (const source of [tracking, payment]) {
      expect(source).toContain("action.idempotency === 'required' || action.idempotency === 'recommended'")
      expect(source).toContain("headers['x-idempotency-key'] = newRemoteMutationKey(action.ref)")
    }
  })

  it('keeps tracking recovery actionable and avoids repeated promise copy', () => {
    const tracking = read('app/pages/pedido/[ref]/index.vue')

    expect(tracking).toContain('const { performAction: performReorderAction, conflict, pending: reorderPending } = useReorder()')
    expect(tracking).toContain('const reorderAction = computed')
    expect(tracking).toContain('const statusPanelActions = computed')
    expect(tracking).toContain('const hasStatusPanelActions = computed')
    expect(tracking).toContain('const visiblePromiseRows = computed')
    // Ordenação das ações e filtro das rows agora vivem em presentation/orderTracking.ts.
    const trackingPresentation = read('app/presentation/orderTracking.ts')
    expect(trackingPresentation).toContain("tone === 'danger' && reorderAction")
    expect(trackingPresentation).toContain('actions.unshift(reorderAction)')
    expect(trackingPresentation).toContain("'última atualização'")
    expect(trackingPresentation).toContain("'sua ação'")
    // Frescor vivo do dado (WP-S3): "Atualizado há X" que vira aviso ao perder um
    // poll — SÓ em pedido ativo (finalizado não mostra "Atualizado agora" mentiroso).
    expect(tracking).toContain('trackingFreshness(')
    expect(tracking).toContain('v-if="tracking.is_active"')
    expect(tracking).toContain('Ações disponíveis')
    expect(tracking).toContain('handleStatusPanelAction')
    expect(tracking).toContain('showSupportInStatusPanel')
    expect(tracking).toContain('const showDeliveryTab = computed')
    // Rótulo da aba entrega/retirada vem do registro omotenashi (copy-burndown):
    // TRACKING_DELIVERY_HEADING via copy.delivery_heading, com fallback textual.
    expect(tracking).toContain('const deliveryTabLabel = computed')
    expect(tracking).toContain('copy.delivery_heading')
    expect(tracking).toContain('const trackingTabsListClass =')
    expect(tracking).toContain('relative flex h-auto w-full justify-start gap-6 overflow-x-auto border-b bg-transparent p-0')
    expect(tracking).toContain('const trackingTabsTriggerClass =')
    expect(tracking).toContain('rounded-none border-b-2 border-transparent bg-transparent px-1 py-2 text-muted-foreground shadow-none data-[state=active]:border-primary')
    expect(tracking).toContain('<UiTabs default-value="history"')
    expect(tracking).toContain('<UiTabsList :pill="false" :class="trackingTabsListClass">')
    expect(tracking).toContain('<UiTabsTrigger :pill="false" value="history" :class="trackingTabsTriggerClass">Histórico</UiTabsTrigger>')
    expect(tracking).toContain('<UiTabsTrigger :pill="false" value="summary" :class="trackingTabsTriggerClass">Resumo</UiTabsTrigger>')
    expect(tracking).toContain('<UiTabsTrigger v-if="showDeliveryTab" :pill="false" value="delivery" :class="trackingTabsTriggerClass">{{ deliveryTabLabel }}</UiTabsTrigger>')
    expect(tracking).toContain('<UiTabsContent value="history">')
    expect(tracking).toContain('<UiTabsContent value="summary">')
    expect(tracking).toContain('<UiTabsContent v-if="showDeliveryTab" value="delivery">')
    // Aba Resumo = mesma diagramação do overlay de revisão: itens qty×nome +
    // linhas ícone/valor (OrderSummaryRows compartilhado) + Total.
    expect(tracking).toContain('<OrderSummaryRows :rows="summaryRows" />')
    expect(tracking).toContain('{{ tracking.copy.total_label }}')
    expect(tracking).toContain('{{ tracking.total_display }}')
    expect(tracking).toContain('<UiAlertTitle>Endereço</UiAlertTitle>')
    expect(tracking).not.toContain("tracking.payment_status || 'Não informado'")
    expect(tracking).not.toContain('<UiAlertTitle>{{ tracking.pickup_info.heading }}</UiAlertTitle>')
    expect(tracking).not.toContain('Próximas ações')
    expect(tracking).not.toContain('<UiCardTitle>{{ tracking.copy.progress_heading }}</UiCardTitle>')
    expect(tracking).not.toContain('<UiTabsTrigger value="items">Itens</UiTabsTrigger>')
    expect(tracking).not.toContain('<UiTabsTrigger value="timeline">Timeline</UiTabsTrigger>')
    expect(tracking).not.toContain('value="timeline"')
    expect(tracking).not.toContain('<UiBadge')
    expect(tracking).not.toContain('<UiProgress :model-value="progressPercent"')
    expect(tracking).not.toContain('tracking.promise.next_event || tracking.last_updated_display')
    expect(tracking).not.toContain('<UiCardTitle>Próxima ação</UiCardTitle>')
    expect(tracking).toContain('<UiCardTitle>Ações</UiCardTitle>')
    expect(tracking).toContain('performReorderSafely')
  })

  it('submits coupon payload using the backend contract key', () => {
    const cartState = read('app/composables/useCartState.ts')

    expect(cartState).toContain('{ code: coupon_code }')
    expect(cartState).not.toContain('{ coupon_code }')
  })

  it('keeps the UI Thing neutral base (stone) intact as the brand-off fallback', () => {
    // O base neutro é o fallback quando a marca está desligada — não é reescrito
    // pela camada de marca, só sobrescrito por ela em runtime. Pinos do neutro:
    const css = read('app/assets/css/tailwind.css')
    const config = read('ui-thing.config.ts')

    expect(config).toContain('"theme": "stone"')
    expect(css).toContain('--radius: 0.5rem')
    expect(css).toContain('--radius-xl: var(--radius)')
    expect(css).toContain('--primary: oklch(0.374 0.010 67.558)')
    expect(css).toContain('--sidebar-primary: oklch(0.374 0.010 67.558)')
    expect(css).toContain('--destructive-foreground: oklch(0.985 0 0)')
    // Tipografia canônica do tema: corpo = Instrument Sans (self-hospedada), com o
    // stack do sistema como fallback. Não é "Inter" (fonte do theming rejeitado).
    expect(css).toContain('--font-sans: "Instrument Sans", ui-sans-serif, system-ui')
    expect(css).not.toContain('"Inter"')
    // O body NÃO pinta bg-background (fica transparente p/ o overscroll revelar o
    // <html> bicolor do plugin); a base neutra vem do .shop-shell (min-h-dvh).
    expect(css).toMatch(/body \{[\s\S]*?@apply text-foreground;/)
    expect(css).toContain('@apply min-h-dvh min-w-0 bg-background text-foreground')
  })

  it('dresses the brand as a reversible override of the neutral base', () => {
    // A marca é uma CAMADA DE OVERRIDE: design_tokens → as variáveis reais que os
    // componentes consomem (`--primary`, `--background`, …), num bloco :root{}/.dark{}.
    const theme = read('app/utils/shopTheme.ts')

    expect(theme).toContain('TOKEN_TO_CSS_VAR')
    expect(theme).toContain("primary: '--primary'")
    expect(theme).toContain("background: '--background'")
    expect(theme).toContain(':root:root {')
    expect(theme).toContain(':root.dark {')
    // Interruptor de reversibilidade: ausência de tokens / preview neutro ⇒ sem override.
    expect(theme).toContain("options.preview === 'neutral'")
    expect(theme).toContain('if (!tokens) return')
    // O override NÃO usa os resíduos do theming rejeitado anterior.
    expect(theme).not.toContain('--shop-brand-color')
  })

  it('keeps cart counters on canonical UiBadge without extending the component API', () => {
    const badge = read('app/components/Ui/Badge.vue')
    const header = read('app/components/ShopHeader.vue')
    const bottomNav = read('app/components/AppBottomNav.vue')

    expect(badge).not.toContain('counter:')
    // Header usa o UiBadge canônico (contador no ícone do carrinho + chip no menu) — sem hacks.
    expect(header).toContain('<UiBadge')
    expect(header).toContain('{{ cart.items_count }}')
    expect(bottomNav).toContain('<UiBadge')
    expect(bottomNav).toContain('size="sm"')
    expect(bottomNav).toContain('rounded-full')
    expect(header).not.toContain('-ml-3 -mt-7')
    expect(bottomNav).not.toContain('class="absolute right-2 top-1 px-1"')
  })

  it('uses canonical guide-line subcomponents for tracking timeline and keeps checkout as progressive sections', () => {
    const tracking = read('app/pages/pedido/[ref]/index.vue')
    const checkout = read('app/pages/finalizar.vue')
    const checkoutFlow = read('app/utils/checkoutFlow.ts')

    expect(tracking).toContain('<UiTimeline :model-value="progressTimelineStep"')
    expect(tracking).toContain(':step="index + 1"')
    expect(tracking).toContain('group-data-[orientation=vertical]/timeline:ms-10')
    expect(tracking).toContain('group-data-[orientation=vertical]/timeline:-left-7 group-data-[orientation=vertical]/timeline:h-[calc(100%-1.5rem-0.25rem)] group-data-[orientation=vertical]/timeline:translate-y-6.5')
    expect(tracking).toContain('group-data-completed/timeline-item:bg-primary group-data-completed/timeline-item:text-primary-foreground flex size-6 items-center justify-center group-data-completed/timeline-item:border-none')
    expect(tracking).toContain('name="lucide:check"')
    expect(tracking).toContain('class="group-not-data-completed/timeline-item:hidden"')
    expect(tracking).not.toContain("step.state === 'completed' ? 'bg-primary' : ''")
    expect(checkout).toContain('data-checkout-progress-stack')
    expect(checkout).toContain('stepIcon')
    expect(checkoutFlow).toContain('isCheckoutStepDone')
    expect(checkoutFlow).toContain('isCheckoutStepUpcoming')
    expect(checkout).not.toContain('<UiStepper')
    expect(checkout).not.toContain('hidden flex-1 sm:block')
  })

  it('does not shadow Vue refs in tracking after checkout navigation', () => {
    const tracking = read('app/pages/pedido/[ref]/index.vue')

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

  it('serves the storefront locally on its reserved dev port at the root path', () => {
    const pkg = JSON.parse(read('package.json'))
    const smoke = read('scripts/ux-smoke.mjs')

    expect(pkg.scripts.dev).toContain('--port 3000')
    expect(smoke).toContain('http://127.0.0.1:3000')
  })

  it('formats simple Portuguese counts without placeholder copy', () => {
    expect(formatCount(1, 'item', 'itens')).toBe('1 item')
    expect(formatCount(2, 'item', 'itens')).toBe('2 itens')
  })

  it('keeps typography on the single-source grammar (papéis, degraus sancionados, sem deriva)', () => {
    // Espelha o que .shop-stack-* fez pelo espaço: a TIPOGRAFIA é uma gramática
    // única. Papéis semânticos no tailwind.css amarram size+weight+leading+tracking;
    // as telas consomem o papel. Escala FECHADA: 12/14/16/20/30 + display do hero;
    // lg(18) e 2xl(24) abolidos; pesos 400/600 nas telas (500 só no chrome Ui).
    const css = read('app/assets/css/tailwind.css')

    // 1) Fonte única: os papéis existem como primitivas reais.
    for (const role of [
      '.shop-display', '.shop-title', '.shop-heading', '.shop-item-title',
      '.shop-body', '.shop-meta', '.shop-price', '.shop-price-strong',
      '.shop-kicker', '.shop-muted'
    ]) {
      expect(css).toContain(role)
    }
    // Display serif (Fraunces) declarada e usada SÓ nos títulos.
    expect(css).toContain('--font-display: "Fraunces"')
    expect(css).toMatch(/\.shop-display\s*\{[\s\S]*?font-family: var\(--font-display\)/)
    expect(css).toMatch(/\.shop-title\s*\{[\s\S]*?font-family: var\(--font-display\)/)
    // Preços carregam tabular-nums (ritmo de valor).
    expect(css).toMatch(/\.shop-price\s*\{[\s\S]*?tabular-nums/)
    expect(css).toMatch(/\.shop-price-strong\s*\{[\s\S]*?tabular-nums/)
    // Kicker é uppercase tracking-wide muted (regra corrigida, não tracking-normal/primary).
    expect(css).toMatch(/\.shop-kicker\s*\{[\s\S]*?uppercase[\s\S]*?tracking-wide/)

    // 2) Os títulos das telas consomem os papéis de título (não voltam a text-* avulso).
    const greedyTemplate = (source: string) => source.match(/<template>([\s\S]*)<\/template>/)?.[1] || ''
    expect(greedyTemplate(read('app/components/HomeHeroThing.vue'))).toContain('shop-display')
    for (const page of ['sacola', 'finalizar', 'entrar', 'produto/[sku]', 'pedido/[ref]/index', 'conta/index']) {
      expect(greedyTemplate(read(`app/pages/${page}.vue`))).toContain('shop-title')
    }

    // 3) Sem deriva nas telas autorais (template inteiro; Ui/ excluído pelo coletor).
    const weight = []      // 500/700+ autoral — só 400/600 permitidos nas telas
    const abolished = []   // lg(18)/2xl(24) abolidos da escala
    const magicLead = []   // leading-[..]/leading-4/leading-none avulsos
    const magicSize = []   // text-[..px/rem/em] mágico (corpo nunca < 14)
    for (const file of surfaceVueFiles) {
      const t = greedyTemplate(read(file))
      if (/\bfont-(thin|extralight|light|medium|bold|extrabold|black)\b/.test(t)) weight.push(file)
      if (/\btext-(lg|2xl|4xl|5xl)\b/.test(t)) abolished.push(file)
      if (/\bleading-\[[^\]]+\]|\bleading-(?:4|none)\b/.test(t)) magicLead.push(file)
      if (/\btext-\[[0-9.]+(px|rem|em)/.test(t)) magicSize.push(file)
    }
    expect(weight).toEqual([])
    expect(abolished).toEqual([])
    expect(magicLead).toEqual([])
    expect(magicSize).toEqual([])
  })

  // Sistema de layout (LAYOUT-SYSTEM-PLAN): o ritmo vertical é a fonte única.
  // Telas consomem a escala de stack de 4 degraus; números mágicos avulsos somem.
  it('keeps vertical rhythm on the 4-step stack scale (fonte única de layout)', () => {
    const css = read('app/assets/css/tailwind.css')
    // As primitivas de composição existem e a largura de leitura é única.
    for (const primitive of ['.shop-container', '.shop-section', '.shop-stack-micro', '.shop-stack-tight', '.shop-stack-block', '.shop-stack-section']) {
      expect(css).toContain(primitive)
    }
    expect(css).toContain('max-w-6xl')

    // Pilhas verticais usam só a régua {1,2,4,8}; off-scale (3/5/6/7 e meio-degraus) é deriva.
    const offScaleStack = /\bspace-y-(0\.5|1\.5|2\.5|3|5|6|7)\b/
    const stackOffenders = surfaceVueFiles
      .filter(file => offScaleStack.test(read(file)))
      .map(file => relative(root, join(root, file)))
    expect(stackOffenders).toEqual([])

    // Gutters/paddings/margens autorais sem meio-degraus nem 5/7/9 (working set {1,2,3,4,6,8}).
    const offScaleGutter = /\bgap-(0\.5|1\.5|2\.5|5|7)\b|\b[pm][trblxy]?-(2\.5|3\.5|5|7|9)\b|\brounded-(xl|2xl)\b/
    const gutterOffenders = surfaceVueFiles
      .filter(file => offScaleGutter.test(read(file)))
      .map(file => relative(root, join(root, file)))
    expect(gutterOffenders).toEqual([])
  })
})
