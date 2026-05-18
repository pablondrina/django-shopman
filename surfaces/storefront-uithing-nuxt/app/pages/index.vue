<script setup lang="ts">
import type { HomeResponse, ProductMutationMeta, SurfaceActionProjection } from '~/types/shopman'

const apiPath = useShopmanApiPath()
const session = useShopSession()
const { setFromServer, qtyForSku, drawerOpen } = useCartState()
const { performAction, pending: reorderPending } = useReorder()

const { data, pending, error, refresh } = await useFetch<HomeResponse>(apiPath('/api/v1/storefront/home/'), {
  credentials: 'include'
})

watchEffect(() => {
  session.setFromHome(data.value?.home)
  setFromServer(data.value?.cart)
})

const home = computed(() => data.value?.home || null)
const featured = computed(() => home.value?.featured_items || [])
const primaryAction = computed(() => home.value?.actions.find(action => action.priority === 'primary' && action.enabled) || null)
const reorderAction = computed(() => home.value?.actions.find(action => action.ref.includes('reorder') && action.enabled) || null)
const menuAction = computed(() => primaryAction.value?.href || '/menu')

function metaFor (item: HomeResponse['home']['featured_items'][number]): ProductMutationMeta {
  return {
    sku: item.sku,
    name: item.name,
    price_q: item.base_price_q,
    price_display: item.price_display,
    image_url: item.image_url
  }
}

async function handleReorder (action: SurfaceActionProjection | null) {
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

useSeoMeta({
  title: () => home.value?.shop.brand_name || 'Shopman',
  description: () => home.value?.shop.description || 'Storefront Shopman'
})
</script>

<template>
  <main>
    <section class="shop-section">
      <div class="shop-container">
        <div v-if="pending" class="grid grid-cols-1 gap-4 md:grid-cols-[1.2fr_0.8fr]">
          <UiSkeleton class="h-80 rounded-lg" />
          <UiSkeleton class="h-80 rounded-lg" />
        </div>

        <UiAlert v-else-if="error" variant="destructive">
          <UiAlertTitle>Nao foi possivel carregar a loja</UiAlertTitle>
          <UiAlertDescription>
            <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <span>Atualize a vitrine ou fale pelo WhatsApp se precisar fechar um pedido agora.</span>
              <UiButton size="sm" variant="outline" @click="refresh">Tentar novamente</UiButton>
            </div>
          </UiAlertDescription>
        </UiAlert>

        <div v-else-if="home" class="grid grid-cols-1 gap-4 lg:grid-cols-[1.25fr_0.75fr]">
          <div class="shop-panel overflow-hidden">
            <div class="relative min-h-[420px]">
              <img
                v-if="featured[0]?.image_url"
                :src="featured[0].image_url"
                :alt="featured[0].name"
                fetchpriority="high"
                class="absolute inset-0 size-full object-cover"
              >
              <div v-else class="absolute inset-0 bg-muted" />
              <div class="absolute inset-0 bg-[linear-gradient(180deg,rgba(5,20,16,.16),rgba(5,20,16,.82))]" />
              <div class="absolute inset-x-0 bottom-0 p-5 text-white sm:p-7">
                <UiBadge :variant="home.shop_status.is_open ? 'success' : 'warning'">
                  {{ home.shop_status.message || (home.shop_status.is_open ? 'Loja aberta' : 'Loja fechada') }}
                </UiBadge>
                <p class="mt-4 text-sm font-medium text-white/80">{{ home.omotenashi.greeting_with_name }}</p>
                <h1 class="mt-2 max-w-2xl text-4xl font-semibold leading-tight sm:text-5xl">
                  {{ home.hero_copy.order_title_prefix.title || home.shop.brand_name }}
                  <span class="block">{{ home.hero_copy.order_title_suffix.title || home.shop.tagline }}</span>
                </h1>
                <p class="mt-4 max-w-xl text-sm leading-6 text-white/82 sm:text-base">
                  {{ home.omotenashi.shop_hint || home.hero_copy.order_subtitle.message || home.shop.description }}
                </p>
                <div class="mt-6 flex flex-wrap gap-3">
                  <UiButton :to="localRouteFromBackend(menuAction)" size="lg" icon="lucide:utensils">
                    {{ primaryAction?.label || home.hero_copy.menu_cta.title || 'Ver cardapio' }}
                  </UiButton>
                  <UiButton
                    v-if="home.public_config.whatsapp_url"
                    :href="home.public_config.whatsapp_url"
                    target="_blank"
                    variant="outline"
                    size="lg"
                    icon="lucide:message-circle"
                    class="border-white/40 bg-white/8 text-white hover:bg-white/16"
                  >
                    WhatsApp
                  </UiButton>
                </div>
              </div>
            </div>
          </div>

          <aside class="space-y-4">
            <UiAlert :variant="home.omotenashi.is_open ? 'success' : 'warning'" filled>
              <UiAlertTitle>{{ home.omotenashi.is_open ? 'Proxima melhor acao' : 'Loja em pausa' }}</UiAlertTitle>
              <UiAlertDescription>
                {{ home.omotenashi.shop_hint || home.shop_status.message || 'Confira o cardapio publicado pela loja.' }}
              </UiAlertDescription>
            </UiAlert>

            <UiCard v-if="reorderAction || home.last_order_items.length">
              <UiCardHeader>
                <UiCardTitle>Voltar ao que funcionou</UiCardTitle>
                <UiCardDescription v-if="home.last_order_ref">Pedido {{ home.last_order_ref }}</UiCardDescription>
              </UiCardHeader>
              <UiCardContent class="space-y-2">
                <UiItem v-for="item in home.last_order_items.slice(0, 3)" :key="item.sku" class="p-0">
                  <UiItemContent>
                    <UiItemTitle>{{ item.name }}</UiItemTitle>
                    <UiItemDescription>{{ item.qty }} unidade(s)</UiItemDescription>
                  </UiItemContent>
                </UiItem>
              </UiCardContent>
              <UiCardFooter>
                <UiButton
                  variant="secondary"
                  icon="lucide:rotate-ccw"
                  :loading="home.last_order_ref ? !!reorderPending[home.last_order_ref] : false"
                  @click="handleReorder(reorderAction)"
                >
                  {{ reorderAction?.label || 'Ver historico' }}
                </UiButton>
              </UiCardFooter>
            </UiCard>

            <UiCard>
              <UiCardHeader>
                <UiCardTitle>Horario e atendimento</UiCardTitle>
                <UiCardDescription>{{ home.shop.phone_display || home.shop.email }}</UiCardDescription>
              </UiCardHeader>
              <UiCardContent class="space-y-2">
                <div v-for="entry in home.opening_hours.slice(0, 4)" :key="entry.label" class="flex justify-between gap-3 text-sm">
                  <span class="text-muted-foreground">{{ entry.label }}</span>
                  <span class="text-right font-medium">{{ entry.hours }}</span>
                </div>
              </UiCardContent>
            </UiCard>
          </aside>
        </div>
      </div>
    </section>

    <section v-if="home && featured.length" class="shop-section pt-0">
      <div class="shop-container space-y-4">
        <div class="flex items-end justify-between gap-4">
          <div>
            <p class="shop-kicker">Disponiveis agora</p>
            <h2 class="mt-1 text-2xl font-semibold">Destaques de agora</h2>
          </div>
          <UiButton to="/menu" variant="ghost" icon="lucide:arrow-right" icon-placement="right">Cardapio completo</UiButton>
        </div>
        <div class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <UiCard v-for="item in featured.slice(0, 4)" :key="item.sku" class="overflow-hidden">
            <NuxtLink :to="`/product/${encodeURIComponent(item.sku)}`">
              <img
                v-if="item.image_url"
                :src="item.image_url"
                :alt="item.name"
                class="aspect-[4/3] w-full object-cover"
                loading="lazy"
              >
              <div v-else class="flex aspect-[4/3] items-center justify-center bg-muted">
                <Icon name="lucide:image" class="size-6 text-muted-foreground" />
              </div>
            </NuxtLink>
            <UiCardContent class="space-y-3 p-4">
              <div class="flex items-start justify-between gap-2">
                <div class="min-w-0">
                  <p class="line-clamp-2 text-sm font-semibold">{{ item.name }}</p>
                  <p class="mt-1 text-sm text-muted-foreground">{{ item.price_display }}</p>
                </div>
                <UiBadge :variant="availabilityVariant(item.availability)">{{ item.availability_label }}</UiBadge>
              </div>
              <QuantityControl :meta="metaFor(item)" :qty="qtyForSku(item.sku)" :disabled="!item.can_add_to_cart" :max-qty="item.available_qty" compact />
            </UiCardContent>
          </UiCard>
        </div>
      </div>
    </section>

    <div class="fixed bottom-20 right-4 z-30 md:bottom-6">
      <UiButton
        variant="default"
        size="lg"
        icon="lucide:shopping-cart"
        class="shadow-lg"
        @click="drawerOpen = true"
      >
        Carrinho
      </UiButton>
    </div>
  </main>
</template>
