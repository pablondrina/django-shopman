<script setup lang="ts">
import type { CopyEntryProjection, HomeProjection, SurfaceActionProjection } from '~/types/shopman'

type HeroKey = 'now' | 'order' | 'reorder' | 'handmade'

interface HeroSlide {
  key: HeroKey
  tabLabel: string
  icon: string
  eyebrow: string
  titleLines: string[]
  description: string
  imageUrl: string | null
  imageAlt: string
  primaryLabel: string
  primaryIcon: string
  primaryTo?: string
  action?: 'reorder'
  secondaryLabel?: string
  secondaryIcon?: string
  secondaryTo?: string
  secondaryHref?: string
  external?: boolean
}

const props = defineProps<{
  home: HomeProjection
  primaryAction: SurfaceActionProjection | null
  reorderAction: SurfaceActionProjection | null
  reorderLoading?: boolean
  statusLabel: string
  statusOpen: boolean
}>()

const emit = defineEmits<{
  reorder: [action: SurfaceActionProjection | null]
}>()

const activeHero = ref<HeroKey>('now')
const featured = computed(() => props.home.featured_items || [])
const menuTo = computed(() => localRouteFromBackend(props.primaryAction?.href || '/menu'))

function titleOf (entry: CopyEntryProjection, fallback: string) {
  return entry.title?.trim() || fallback
}

function messageOf (entry: CopyEntryProjection, fallback: string) {
  return entry.message?.trim() || fallback
}

function imageAt (index: number) {
  return featured.value[index]?.image_url || featured.value[0]?.image_url || null
}

function imageAltAt (index: number, fallback: string) {
  return featured.value[index]?.name || fallback
}

const slides = computed<HeroSlide[]>(() => {
  const copy = props.home.hero_copy
  const shop = props.home.shop
  const next: HeroSlide[] = []

  next.push({
    key: 'now',
    tabLabel: props.home.omotenashi.is_birthday ? 'Hoje' : 'Agora',
    icon: props.home.omotenashi.is_birthday ? 'lucide:sparkles' : 'lucide:store',
    eyebrow: props.home.omotenashi.greeting_with_name,
    titleLines: props.home.omotenashi.is_birthday
      ? [titleOf(copy.birthday_heading, 'Um cuidado especial hoje')]
      : [shop.brand_name, shop.tagline],
    description: props.home.omotenashi.is_birthday
      ? messageOf(copy.birthday_sub, shop.description)
      : (props.home.omotenashi.shop_hint || shop.description),
    imageUrl: imageAt(0),
    imageAlt: imageAltAt(0, shop.brand_name),
    primaryLabel: props.home.omotenashi.is_birthday
      ? titleOf(copy.birthday_cta, titleOf(copy.menu_cta, 'Ver cardapio'))
      : titleOf(copy.menu_cta, 'Ver cardapio'),
    primaryIcon: props.home.omotenashi.is_birthday ? 'lucide:gift' : 'lucide:arrow-right',
    primaryTo: menuTo.value,
    secondaryLabel: props.home.public_config.whatsapp_url ? 'WhatsApp' : undefined,
    secondaryIcon: 'lucide:message-circle',
    secondaryHref: props.home.public_config.whatsapp_url || undefined,
    external: true
  })

  next.push({
    key: 'order',
    tabLabel: 'Pedir',
    icon: 'lucide:shopping-bag',
    eyebrow: props.home.omotenashi.greeting_with_name,
    titleLines: [
      titleOf(copy.order_title_prefix, shop.brand_name),
      titleOf(copy.order_title_suffix, shop.tagline)
    ],
    description: messageOf(copy.order_subtitle, shop.description),
    imageUrl: imageAt(0),
    imageAlt: imageAltAt(0, shop.brand_name),
    primaryLabel: props.primaryAction?.label || titleOf(copy.menu_cta, 'Ver cardapio'),
    primaryIcon: 'lucide:utensils',
    primaryTo: menuTo.value,
    secondaryLabel: props.home.public_config.whatsapp_url ? 'WhatsApp' : undefined,
    secondaryIcon: 'lucide:message-circle',
    secondaryHref: props.home.public_config.whatsapp_url || undefined,
    external: true
  })

  if (props.reorderAction || props.home.last_order_items.length) {
    next.push({
      key: 'reorder',
      tabLabel: 'Repetir',
      icon: 'lucide:rotate-ccw',
      eyebrow: props.home.last_order_ref ? `Pedido ${props.home.last_order_ref}` : 'Historico',
      titleLines: [
        titleOf(copy.reorder_title_prefix, 'Seu pedido favorito'),
        titleOf(copy.reorder_title_suffix, 'de volta')
      ],
      description: messageOf(copy.reorder_subtitle, 'Revise o pedido anterior antes de confirmar.'),
      imageUrl: imageAt(1),
      imageAlt: imageAltAt(1, shop.brand_name),
      primaryLabel: props.reorderAction?.label || 'Ver historico',
      primaryIcon: 'lucide:rotate-ccw',
      action: 'reorder',
      secondaryLabel: titleOf(copy.menu_cta, 'Cardapio'),
      secondaryIcon: 'lucide:utensils',
      secondaryTo: menuTo.value
    })
  }

  next.push({
    key: 'handmade',
    tabLabel: 'Forno',
    icon: 'lucide:wheat',
    eyebrow: 'Producao artesanal',
    titleLines: [
      titleOf(copy.handmade_title_prefix, 'Feito aqui'),
      titleOf(copy.handmade_title_suffix, 'para hoje')
    ],
    description: messageOf(copy.handmade_subtitle, shop.description),
    imageUrl: imageAt(2),
    imageAlt: imageAltAt(2, shop.brand_name),
    primaryLabel: titleOf(copy.menu_cta, 'Ver cardapio'),
    primaryIcon: 'lucide:arrow-right',
    primaryTo: menuTo.value,
    secondaryLabel: props.home.public_config.whatsapp_url ? 'WhatsApp' : undefined,
    secondaryIcon: 'lucide:message-circle',
    secondaryHref: props.home.public_config.whatsapp_url || undefined,
    external: true
  })

  return next
})

const activeSlide = computed<HeroSlide | null>(() =>
  slides.value.find(slide => slide.key === activeHero.value) || slides.value[0] || null
)

watchEffect(() => {
  if (!slides.value.some(slide => slide.key === activeHero.value)) {
    activeHero.value = slides.value[0]?.key || 'order'
  }
})
</script>

<template>
  <UiTabs v-model="activeHero" class="shop-panel gap-0 overflow-hidden">
    <div class="relative">
      <div class="absolute inset-x-0 top-0 z-20 flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between sm:p-5">
        <UiBadge :variant="statusOpen ? 'success' : 'warning'" class="w-fit shadow-sm">
          {{ statusLabel }}
        </UiBadge>
        <div class="no-scrollbar max-w-full overflow-x-auto rounded-md bg-black/35 p-1 shadow-sm backdrop-blur">
          <UiTabsList class="bg-transparent text-white/80">
            <UiTabsTrigger
              v-for="slide in slides"
              :key="slide.key"
              :value="slide.key"
              class="gap-1.5 text-white/80 data-[state=active]:bg-white data-[state=active]:text-foreground hover:text-white"
              @click="activeHero = slide.key"
            >
              <Icon :name="slide.icon" class="size-3.5" />
              {{ slide.tabLabel }}
            </UiTabsTrigger>
          </UiTabsList>
        </div>
      </div>

      <UiTabsContent v-if="activeSlide" :key="activeSlide.key" :value="activeSlide.key" class="m-0">
        <div class="relative min-h-[500px] sm:min-h-[560px]">
          <img
            v-if="activeSlide.imageUrl"
            :src="activeSlide.imageUrl"
            :alt="activeSlide.imageAlt"
            fetchpriority="high"
            decoding="async"
            class="absolute inset-0 size-full object-cover"
          >
          <div v-else class="absolute inset-0 bg-muted" />
          <div class="absolute inset-0 bg-[linear-gradient(180deg,rgba(5,18,14,.22),rgba(5,18,14,.86))]" />
          <div class="absolute inset-x-0 bottom-0 z-10 p-5 pt-24 text-white sm:p-7 lg:p-9">
            <p class="text-sm font-medium text-white/80">{{ activeSlide.eyebrow }}</p>
            <h1 class="mt-2 max-w-3xl text-4xl font-semibold leading-tight sm:text-5xl">
              <span v-for="line in activeSlide.titleLines" :key="line" class="block">{{ line }}</span>
            </h1>
            <p class="mt-4 max-w-xl text-sm leading-6 text-white/84 sm:text-base">
              {{ activeSlide.description }}
            </p>
            <div class="mt-6 flex flex-wrap gap-3">
              <UiButton
                v-if="activeSlide.action === 'reorder'"
                size="lg"
                :icon="activeSlide.primaryIcon"
                :loading="reorderLoading"
                @click="emit('reorder', reorderAction)"
              >
                {{ activeSlide.primaryLabel }}
              </UiButton>
              <UiButton v-else :to="activeSlide.primaryTo" size="lg" :icon="activeSlide.primaryIcon">
                {{ activeSlide.primaryLabel }}
              </UiButton>
              <UiButton
                v-if="activeSlide.secondaryTo || activeSlide.secondaryHref"
                :to="activeSlide.secondaryTo"
                :href="activeSlide.secondaryHref"
                :target="activeSlide.external ? '_blank' : undefined"
                variant="outline"
                size="lg"
                :icon="activeSlide.secondaryIcon"
                class="border-white/40 bg-white/8 text-white hover:bg-white/16"
              >
                {{ activeSlide.secondaryLabel }}
              </UiButton>
            </div>
          </div>
        </div>
      </UiTabsContent>
    </div>
  </UiTabs>
</template>
