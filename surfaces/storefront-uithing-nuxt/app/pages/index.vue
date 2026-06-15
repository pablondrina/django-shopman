<script setup lang="ts">
import { absoluteImage, bakeryJsonLd } from '~/presentation/seo'
import type { HomeResponse, Action } from '~/types/shopman'

const apiPath = useShopmanApiPath()
const session = useShopSession()
const requestUrl = useRequestURL()
const { setFromServer } = useCartState()
const { performAction, pending: reorderPending } = useReorder()

const { data, pending, error, refresh } = await useFetch<HomeResponse>(apiPath('/api/v1/storefront/home/'), {
  credentials: 'include'
})

watch(() => data.value, value => {
  session.setFromHome(value?.home)
  setFromServer(value?.cart)
}, { immediate: true })

const home = computed(() => data.value?.home || null)
const featured = computed(() => home.value?.featured_items || [])
const sectionsCopy = computed(() => home.value?.sections_copy || null)
const primaryAction = computed(() => home.value?.actions.find(action => action.priority === 'primary' && action.enabled && !action.ref.includes('reorder')) || null)
const reorderAction = computed(() => home.value?.actions.find(action => action.ref.includes('reorder') && action.enabled) || null)
const contextualNotices = computed(() => home.value?.notices.filter(notice => notice.priority !== 'global') || [])
const operationalStatus = computed(() => {
  const status = home.value?.shop_status
  return {
    isOpen: !!status?.is_open,
    label: status?.label?.trim() || ''
  } as const
})
const quickReorderItems = computed(() => home.value?.last_order_items.slice(0, 3) || [])
const quickReorderTitle = computed(() => {
  const name = home.value?.omotenashi.customer_name
  return `Quer repetir seu último pedido${name ? `, ${name}` : ''}?`
})
const featuredPreview = computed(() => featured.value.slice(0, 6))
const quickReorderImageItem = computed(() => {
  const reorderSkus = new Set(quickReorderItems.value.map(item => item.sku))
  return featured.value.find(item => reorderSkus.has(item.sku) && item.image_url) || featured.value.find(item => item.image_url) || null
})
const visitAddressLines = computed(() => addressLines(home.value?.shop.full_address))
const whatsappUrl = computed(() => home.value?.public_config.whatsapp_url || '')
const whatsappImage = computed(() => featured.value[1]?.image_url || featured.value[0]?.image_url || null)

// A home mais útil para quem voltou com pedido em andamento é o próprio
// pedido: banner com prioridade sobre o hero (silencioso para anônimos).
const activeOrder = ref<{ ref: string, status_label: string } | null>(null)
onMounted(async () => {
  try {
    const active = await $fetch<{ count: number }>(apiPath('/api/v1/account/orders/active/'), { credentials: 'include' })
    if (!active?.count) return
    const response = await $fetch<unknown>(apiPath('/api/v1/account/orders/?filter=ativos'), { credentials: 'include' })
    const orders = Array.isArray(response) ? response : (response as { orders?: unknown[] })?.orders
    const first = Array.isArray(orders) ? orders[0] as { ref?: string, status_label?: string } : null
    if (first?.ref) activeOrder.value = { ref: first.ref, status_label: first.status_label || 'Pedido em andamento' }
  } catch {
    // Sessão anônima ou indisponível: a home segue sem o banner.
  }
})

async function handleReorder (action: Action | null) {
  if (!action) {
    await navigateTo('/account')
    return
  }
  try {
    await performAction(action)
  } catch {
    // The reorder composable already exposes the failure in cart/toast state.
  }
}

function noticeVariant (tone: string) {
  if (tone === 'danger') return 'destructive'
  if (tone === 'warning') return 'warning'
  if (tone === 'info') return 'info'
  return 'default'
}

const canonicalUrl = computed(() => `${requestUrl.origin}/`)
const homeDescription = computed(() => home.value?.shop.description || home.value?.shop.tagline || 'Storefront Shopman')
const homeOgImage = computed(() => absoluteImage(
  requestUrl.origin,
  featured.value[0]?.image_url || home.value?.shop.logo_url
))

useSeoMeta({
  title: () => home.value?.shop.brand_name || 'Shopman',
  description: () => homeDescription.value,
  ogTitle: () => home.value?.shop.brand_name || 'Shopman',
  ogDescription: () => homeDescription.value,
  ogType: 'website',
  ogUrl: () => canonicalUrl.value,
  ogImage: () => homeOgImage.value || undefined,
  twitterCard: 'summary_large_image',
  twitterTitle: () => home.value?.shop.brand_name || 'Shopman',
  twitterDescription: () => homeDescription.value,
  twitterImage: () => homeOgImage.value || undefined
})

// JSON-LD Bakery (LocalBusiness) — endereço, geo, contato server-driven.
useHead({
  link: [{ rel: 'canonical', href: () => canonicalUrl.value }],
  script: () => home.value
    ? [{
        type: 'application/ld+json',
        innerHTML: JSON.stringify(bakeryJsonLd({
          shop: home.value.shop,
          origin: requestUrl.origin,
          url: canonicalUrl.value,
          latitude: home.value.public_config.shop_latitude,
          longitude: home.value.public_config.shop_longitude
        }))
      }]
    : []
})
</script>

<template>
  <main class="bg-muted">
    <section class="bg-muted pb-5 pt-0 sm:py-8 lg:py-10">
      <div class="shop-container">
        <div v-if="pending" class="space-y-5">
          <UiSkeleton class="-mx-4 h-[calc(100svh-12.5rem)] rounded-none sm:mx-0 sm:h-[440px] sm:rounded-lg" />
          <UiSkeleton class="h-72 rounded-lg" />
        </div>

        <UiAlert v-else-if="error" variant="destructive">
          <UiAlertTitle>Não foi possível carregar a loja</UiAlertTitle>
          <UiAlertDescription>
            <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <span>Atualize a vitrine ou fale pelo WhatsApp se precisar fechar um pedido agora.</span>
              <UiButton size="sm" variant="outline" @click="refresh">Tentar novamente</UiButton>
            </div>
          </UiAlertDescription>
        </UiAlert>

        <div v-else-if="home" class="space-y-5">
          <div>
            <NuxtLink
              v-if="activeOrder"
              :to="`/tracking/${encodeURIComponent(activeOrder.ref)}`"
              class="-mx-4 block bg-primary p-4 text-primary-foreground sm:mx-0 sm:mb-3 sm:rounded-lg sm:shadow-sm"
              data-home-active-order
            >
              <div class="flex items-center gap-3">
                <Icon name="lucide:chef-hat" class="size-5 shrink-0" />
                <div class="min-w-0 flex-1">
                  <p class="text-sm font-semibold">{{ activeOrder.status_label }}</p>
                  <p class="text-xs opacity-80">Pedido {{ activeOrder.ref }}</p>
                </div>
                <span class="inline-flex shrink-0 items-center gap-1 text-sm font-semibold">
                  Acompanhar
                  <Icon name="lucide:chevron-right" class="size-4" />
                </span>
              </div>
            </NuxtLink>

            <HomeHeroThing
              :home="home"
              :primary-action="primaryAction"
              :reorder-action="reorderAction"
              :reorder-loading="home.last_order_ref ? !!reorderPending[home.last_order_ref] : false"
              :status-open="operationalStatus.isOpen"
              closed-cta-label="Monte seu pedido para amanhã"
              @reorder="handleReorder"
            />

            <UiButton
              variant="outline"
              to="/busca"
              class="mt-3 h-11 w-full justify-start gap-2 rounded-full bg-background font-normal text-muted-foreground shadow-sm"
              data-home-search-shortcut
            >
              <Icon name="lucide:search" class="size-4" />
              Buscar no cardápio
            </UiButton>
          </div>

          <UiAlert v-for="notice in contextualNotices" :key="notice.ref" :variant="noticeVariant(notice.tone)">
            <UiAlertTitle>{{ notice.title }}</UiAlertTitle>
            <UiAlertDescription>
              <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <span>{{ notice.message }}</span>
                <div v-if="notice.actions.length" class="flex flex-wrap gap-2">
                  <UiButton
                    v-for="action in notice.actions"
                    :key="action.ref"
                    size="sm"
                    :variant="action.priority === 'primary' ? 'default' : 'outline'"
                    :to="action.kind === 'link' ? localRouteFromBackend(action.href) : undefined"
                    :href="action.kind === 'external' ? action.href : undefined"
                    :target="action.kind === 'external' ? '_blank' : undefined"
                    rel="noopener"
                  >
                    {{ action.label }}
                  </UiButton>
                </div>
              </div>
            </UiAlertDescription>
          </UiAlert>

          <UiCard v-if="reorderAction || quickReorderItems.length" class="gap-0 overflow-hidden py-0" data-home-reorder-card>
            <div class="grid grid-cols-1 md:grid-cols-2">
              <UiAspectRatio :ratio="16 / 9" class="overflow-hidden bg-muted md:h-full">
                <img
                  v-if="quickReorderImageItem?.image_url"
                  :src="quickReorderImageItem.image_url"
                  :alt="quickReorderImageItem.name"
                  loading="lazy"
                  decoding="async"
                  class="size-full object-cover"
                >
                <div v-else class="flex size-full items-center justify-center text-muted-foreground">
                  <Icon name="lucide:croissant" class="size-10" />
                </div>
              </UiAspectRatio>

              <UiCardContent class="flex flex-col justify-center gap-4 p-5 sm:p-7 lg:p-8">
                <UiItemMedia variant="icon" class="size-12 rounded-full">
                  <Icon name="lucide:rotate-ccw" />
                </UiItemMedia>
                <div class="space-y-2">
                  <h2 class="text-xl font-semibold leading-tight">{{ quickReorderTitle }}</h2>
                  <ul v-if="quickReorderItems.length" class="flex flex-wrap gap-x-3 gap-y-1 text-sm text-muted-foreground" aria-label="Itens do último pedido">
                    <li v-for="item in quickReorderItems" :key="item.sku" class="inline-flex items-center gap-1">
                      <span class="font-semibold text-foreground">{{ item.qty }}×</span>
                      <span>{{ item.name }}</span>
                    </li>
                  </ul>
                  <p v-else class="text-sm text-muted-foreground">Seu pedido anterior volta ao carrinho para revisão.</p>
                </div>
                <UiButton
                  icon="lucide:shopping-bag"
                  :loading="home.last_order_ref ? !!reorderPending[home.last_order_ref] : false"
                  class="w-full sm:w-fit"
                  @click="handleReorder(reorderAction)"
                >
                  {{ reorderAction?.label || 'Ver histórico' }}
                </UiButton>
              </UiCardContent>
            </div>
          </UiCard>
        </div>
      </div>
    </section>

    <section v-if="home && featuredPreview.length && sectionsCopy" class="shop-section border-y bg-background pt-8 md:pt-10">
      <div class="shop-container space-y-6">
        <div class="mx-auto max-w-2xl text-center">
          <h2 class="text-xl font-semibold">{{ sectionsCopy.availability_heading.title }}</h2>
          <p class="mt-2 text-sm text-muted-foreground">{{ sectionsCopy.availability_heading.message }}</p>
        </div>
        <div class="no-scrollbar -mx-4 flex snap-x snap-mandatory gap-4 overflow-x-auto px-4 pb-2 sm:mx-0 sm:grid sm:grid-cols-2 sm:overflow-visible sm:p-0 lg:grid-cols-3" data-home-featured-rail>
          <ProductTile
            v-for="item in featuredPreview"
            :key="item.sku"
            :item="item"
            class="w-[72%] shrink-0 snap-start sm:w-auto"
          />
        </div>
        <div class="text-center">
          <UiButton to="/menu" variant="ghost" icon="lucide:arrow-right" icon-placement="right">
            {{ sectionsCopy.full_menu_cta.title || 'Ver cardápio completo' }}
          </UiButton>
        </div>
      </div>
    </section>

    <section v-if="home && sectionsCopy" id="como-funciona" class="shop-section bg-muted scroll-mt-20">
      <div class="shop-container space-y-8">
        <div class="mx-auto max-w-2xl text-center">
          <h2 class="text-xl font-semibold">{{ sectionsCopy.how_it_works_heading.title }}</h2>
          <p v-if="sectionsCopy.how_it_works_intro.message" class="mt-2 text-sm text-muted-foreground">
            {{ sectionsCopy.how_it_works_intro.message }}
          </p>
        </div>

        <div class="mx-auto grid max-w-4xl grid-cols-1 gap-4 md:grid-cols-2">
          <div class="flex flex-col gap-3 rounded-lg border bg-background p-5" data-home-path-online>
            <UiItemMedia variant="icon" class="size-10 rounded-full">
              <Icon name="lucide:shopping-bag" />
            </UiItemMedia>
            <h3 class="text-base font-semibold">Peça online</h3>
            <p class="text-sm text-muted-foreground">Escolha, pague e acompanhe — entregamos ou você retira.</p>
            <UiButton :to="'/menu'" icon="lucide:utensils" class="mt-auto w-fit">
              {{ sectionsCopy.full_menu_cta.title || 'Ver cardápio' }}
            </UiButton>
          </div>

          <div class="flex flex-col gap-3 rounded-lg border bg-background p-5" data-home-path-visit>
            <UiItemMedia variant="icon" class="size-10 rounded-full">
              <Icon name="lucide:store" />
            </UiItemMedia>
            <div class="flex flex-wrap items-center gap-2">
              <h3 class="text-base font-semibold">Visite a loja</h3>
              <UiBadge v-if="operationalStatus.label" variant="secondary">{{ operationalStatus.label }}</UiBadge>
            </div>
            <p v-if="visitAddressLines.length" class="text-sm text-muted-foreground">
              <span v-for="line in visitAddressLines" :key="line" class="block">{{ line }}</span>
            </p>
            <div class="mt-auto flex flex-wrap gap-2">
              <UiButton
                v-if="home.shop.maps_url"
                :href="home.shop.maps_url"
                target="_blank"
                rel="noopener"
                variant="outline"
                icon="lucide:map-pin"
              >
                Como chegar
              </UiButton>
              <UiButton
                v-if="operationalStatus.isOpen && home.shop.phone_url"
                :href="home.shop.phone_url"
                variant="ghost"
                icon="lucide:phone"
              >
                Ligar
              </UiButton>
            </div>
          </div>
        </div>
      </div>
    </section>

    <section v-if="home && whatsappUrl && sectionsCopy" class="border-y bg-background py-0 sm:py-8 lg:py-10">
      <div class="shop-container">
        <div class="relative -mx-4 overflow-hidden rounded-none bg-foreground text-background sm:mx-0 sm:rounded-lg">
          <img
            v-if="whatsappImage"
            :src="whatsappImage"
            alt=""
            loading="lazy"
            decoding="async"
            class="absolute inset-0 size-full object-cover opacity-35"
          >
          <div class="relative mx-auto max-w-2xl px-6 py-14 text-center md:py-16">
            <h2 class="text-xl font-semibold md:text-2xl">{{ sectionsCopy.whatsapp_cta.title }}</h2>
            <p class="mt-3 text-sm leading-6 text-background/80 md:text-base">
              {{ sectionsCopy.whatsapp_cta.message }}
            </p>
            <UiButton
              :href="whatsappUrl"
              target="_blank"
              rel="noopener"
              size="lg"
              variant="secondary"
              icon="lucide:message-circle"
              class="mt-6"
            >
              {{ sectionsCopy.whatsapp_cta_label.title || 'Falar no WhatsApp' }}
            </UiButton>
          </div>
        </div>
      </div>
    </section>
  </main>
</template>
