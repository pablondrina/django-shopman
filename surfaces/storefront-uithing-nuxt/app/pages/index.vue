<script setup lang="ts">
import type { HomeResponse, Action } from '~/types/shopman'

const apiPath = useShopmanApiPath()
const session = useShopSession()
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
const featuredPreview = computed(() => featured.value.slice(0, 3))
const quickReorderImageItem = computed(() => {
  const reorderSkus = new Set(quickReorderItems.value.map(item => item.sku))
  return featured.value.find(item => reorderSkus.has(item.sku) && item.image_url) || featured.value.find(item => item.image_url) || null
})
const openingHoursInline = computed(() => {
  const entries = home.value?.opening_hours || []
  if (!entries.length) return sectionsCopy.value?.how_hours_empty.message || 'Consulte nossos horários'
  return entries.slice(0, 3).map(entry => `${entry.label}: ${entry.hours}`).join(' · ')
})
const howOnlineSteps = computed(() => {
  const copy = sectionsCopy.value
  if (!copy) return []
  return [
    { icon: 'lucide:shopping-basket', title: copy.how_step_choose.title, description: copy.how_online_choose_message.message },
    { icon: 'lucide:badge-dollar-sign', title: copy.how_step_pay.title, description: copy.how_online_pay_message.message },
    { icon: 'lucide:route', title: copy.how_step_fulfill.title, description: copy.how_online_track_message.message }
  ]
})
const storeSteps = computed(() => {
  const copy = sectionsCopy.value
  if (!copy) return []
  return [
    { icon: 'lucide:store', title: copy.how_self_service_label.title, description: copy.how_store_self_service_message.message },
    { icon: 'lucide:coffee', title: copy.how_counter_label.title, description: copy.how_store_counter_message.message },
    { icon: 'lucide:clock', title: copy.how_hours_label.title, description: openingHoursInline.value }
  ]
})
const whatsappUrl = computed(() => home.value?.public_config.whatsapp_url || '')
const whatsappImage = computed(() => featured.value[1]?.image_url || featured.value[0]?.image_url || null)

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

useSeoMeta({
  title: () => home.value?.shop.brand_name || 'Shopman',
  description: () => home.value?.shop.description || 'Storefront Shopman'
})
</script>

<template>
  <main class="bg-muted">
    <section class="bg-muted pb-6 pt-0 sm:py-8 lg:py-10">
      <div class="shop-container">
        <div v-if="pending" class="space-y-5">
          <UiSkeleton class="-mx-4 h-[calc(100svh-4rem)] rounded-none sm:mx-0 sm:h-[440px] sm:rounded-lg" />
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
          <HomeHeroThing
            :home="home"
            :primary-action="primaryAction"
            :reorder-action="reorderAction"
            :reorder-loading="home.last_order_ref ? !!reorderPending[home.last_order_ref] : false"
            :status-label="operationalStatus.label"
            :status-open="operationalStatus.isOpen"
            @reorder="handleReorder"
          />

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
                  <h2 class="text-2xl font-semibold leading-tight">{{ quickReorderTitle }}</h2>
                  <ul v-if="quickReorderItems.length" class="flex flex-wrap gap-x-3 gap-y-1 text-sm text-muted-foreground" aria-label="Itens do último pedido">
                    <li v-for="item in quickReorderItems" :key="item.sku" class="inline-flex items-center gap-1">
                      <span class="font-medium text-foreground">{{ item.qty }}×</span>
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

    <section v-if="home && featuredPreview.length && sectionsCopy" class="shop-section border-y bg-background pt-10 md:pt-12">
      <div class="shop-container space-y-6">
        <div class="mx-auto max-w-2xl text-center">
          <h2 class="text-2xl font-semibold">{{ sectionsCopy.availability_heading.title }}</h2>
          <p class="mt-2 text-sm text-muted-foreground">{{ sectionsCopy.availability_heading.message }}</p>
        </div>
        <div class="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <ProductTile v-for="item in featuredPreview" :key="item.sku" :item="item" />
        </div>
        <div class="text-center">
          <UiButton to="/menu" variant="ghost" icon="lucide:arrow-right" icon-placement="right">
            {{ sectionsCopy.full_menu_cta.title || 'Ver cardápio completo' }}
          </UiButton>
        </div>
      </div>
    </section>

    <section v-if="home && sectionsCopy" class="shop-section bg-muted">
      <div class="shop-container space-y-8">
        <div class="mx-auto max-w-2xl text-center">
          <h2 class="text-2xl font-semibold">{{ sectionsCopy.how_it_works_heading.title }}</h2>
          <p v-if="sectionsCopy.how_it_works_intro.message" class="mt-2 text-sm text-muted-foreground">
            {{ sectionsCopy.how_it_works_intro.message }}
          </p>
        </div>

        <div class="mx-auto grid max-w-4xl grid-cols-1 gap-8 md:grid-cols-2 md:gap-12">
          <section class="space-y-4">
            <h3 class="flex items-center gap-2 text-lg font-semibold">
              <UiItemMedia variant="icon" class="size-8 rounded-full">
                <Icon name="lucide:shopping-bag" />
              </UiItemMedia>
              {{ sectionsCopy.how_online_heading.title }}
            </h3>
            <UiItemGroup class="gap-3">
              <UiItem v-for="(step, index) in howOnlineSteps" :key="step.title" size="sm" class="items-start bg-transparent p-0">
                <UiItemMedia variant="icon" class="mt-0.5 size-7 rounded-full text-xs">
                  <span class="font-semibold tabular-nums">{{ index + 1 }}</span>
                </UiItemMedia>
                <UiItemContent>
                  <UiItemTitle>{{ step.title }}</UiItemTitle>
                  <UiItemDescription>{{ step.description }}</UiItemDescription>
                </UiItemContent>
              </UiItem>
            </UiItemGroup>
          </section>

          <section class="space-y-4">
            <h3 class="flex items-center gap-2 text-lg font-semibold">
              <UiItemMedia variant="icon" class="size-8 rounded-full">
                <Icon name="lucide:store" />
              </UiItemMedia>
              {{ sectionsCopy.how_store_heading.title }}
            </h3>
            <UiItemGroup class="gap-3">
              <UiItem v-for="step in storeSteps" :key="step.title" size="sm" class="items-start bg-transparent p-0">
                <UiItemMedia variant="icon" class="mt-0.5 size-7 rounded-full">
                  <Icon :name="step.icon" class="size-4" />
                </UiItemMedia>
                <UiItemContent>
                  <UiItemTitle>{{ step.title }}</UiItemTitle>
                  <UiItemDescription>{{ step.description }}</UiItemDescription>
                </UiItemContent>
              </UiItem>
            </UiItemGroup>
          </section>
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
            <h2 class="text-2xl font-semibold md:text-3xl">{{ sectionsCopy.whatsapp_cta.title }}</h2>
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
