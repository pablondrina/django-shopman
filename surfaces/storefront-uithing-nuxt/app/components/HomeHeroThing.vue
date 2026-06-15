<script setup lang="ts">
import type { CopyEntryProjection, HomeProjection, Action } from '~/types/shopman'

interface HeroSlide {
  ref: string
  eyebrow?: string
  titleLines: string[]
  description?: string
  imageUrl: string | null
  imageAlt: string
  primaryLabel: string
  primaryIcon: string
  primaryTo?: string
  primaryAction?: Action | null
  secondaryLabel?: string
  secondaryTo?: string
}

const props = defineProps<{
  home: HomeProjection
  primaryAction: Action | null
  reorderAction: Action | null
  reorderLoading?: boolean
  statusOpen: boolean
  closedCtaLabel?: string
}>()

const emit = defineEmits<{
  reorder: [action: Action | null]
}>()

// Mesmas fotos do hero da home Django (shopman/storefront/templates/storefront/
// home.html) — pareadas por slide para comparação direta de composição.
// Não é theming/marca: é o conjunto neutro de referência da padaria.
const HERO_IMAGE_URLS = {
  greeting: 'https://images.unsplash.com/photo-1509440159596-0249088772ff?auto=format&fit=crop&w=1600&q=80',
  order: 'https://images.unsplash.com/photo-1517433670267-08bbd4be890f?auto=format&fit=crop&w=1600&q=80',
  reorder: 'https://images.unsplash.com/photo-1568254183919-78a4f43a2877?auto=format&fit=crop&w=1600&q=80',
  handmade: 'https://images.unsplash.com/photo-1608198093002-ad4e005484ec?auto=format&fit=crop&w=1600&q=80'
} as const

const menuTo = computed(() => localRouteFromBackend(props.primaryAction?.href || '/menu'))
const activeIndex = ref(0)
const paused = ref(false)
const touchStartX = ref(0)
let autoplayTimer: ReturnType<typeof setInterval> | null = null

function titleOf (entry: CopyEntryProjection, fallback: string) {
  return entry.title?.trim() || fallback
}

function messageOf (entry: CopyEntryProjection, fallback: string) {
  return entry.message?.trim() || fallback
}

function shopDescription () {
  const shop = props.home.shop
  return shop.description?.trim() || shop.tagline?.trim() || shop.brand_name
}

function sentence (value: string) {
  const trimmed = value.trim()
  if (!trimmed) return ''
  return /[.!?]$/.test(trimmed) ? trimmed : `${trimmed}.`
}

function activatePreviousSlide () {
  const total = slides.value.length
  if (!total) return
  activeIndex.value = activeIndex.value === 0 ? total - 1 : activeIndex.value - 1
}

function activateNextSlide () {
  const total = slides.value.length
  if (!total) return
  activeIndex.value = activeIndex.value === total - 1 ? 0 : activeIndex.value + 1
}

function activateSlide (index: number) {
  activeIndex.value = index
}

// Toda navegação manual reinicia o autoplay, senão o avanço automático (8s)
// pode trocar o slide logo após o toque do usuário — parecendo que a seta
// "não funcionou".
function restartAutoplay () {
  if (autoplayTimer) {
    clearInterval(autoplayTimer)
    autoplayTimer = null
  }
  if (!paused.value && slides.value.length > 1) {
    autoplayTimer = setInterval(activateNextSlide, 8000)
  }
}

function goToPreviousSlide () {
  activatePreviousSlide()
  restartAutoplay()
}

function goToNextSlide () {
  activateNextSlide()
  restartAutoplay()
}

function goToSlide (index: number) {
  activateSlide(index)
  restartAutoplay()
}

function handleTouchEnd (event: TouchEvent) {
  const dx = event.changedTouches[0]?.screenX - touchStartX.value
  if (Math.abs(dx) < 50) return
  if (dx < 0) goToNextSlide()
  else goToPreviousSlide()
}

function handlePrimaryAction (slide: HeroSlide) {
  if (slide.primaryAction) emit('reorder', slide.primaryAction)
}

const slides = computed<HeroSlide[]>(() => {
  const copy = props.home.hero_copy
  const shop = props.home.shop
  const omo = props.home.omotenashi
  const customerName = omo.customer_name?.trim()
  const description = shopDescription()
  const menuLabel = (!props.statusOpen && props.closedCtaLabel) || titleOf(copy.menu_cta, 'Ver cardápio')
  const handmadeTitle = `${titleOf(copy.handmade_title_prefix, 'Feito à mão,')} ${titleOf(copy.handmade_title_suffix, 'todo dia')}`
  const greetingTitle = sentence(omo.greeting_with_name || handmadeTitle)
  const list: HeroSlide[] = []

  if (omo.is_birthday) {
    list.push({
      ref: 'birthday',
      titleLines: [`${titleOf(copy.birthday_heading, 'Um cuidado especial hoje')}${customerName ? `, ${customerName}` : ''}!`],
      description: messageOf(copy.birthday_sub, description),
      imageUrl: HERO_IMAGE_URLS.greeting,
      imageAlt: shop.brand_name,
      primaryLabel: titleOf(copy.birthday_cta, titleOf(copy.menu_cta, 'Ver cardápio')),
      primaryIcon: 'lucide:gift',
      primaryTo: menuTo.value
    })
  } else {
    list.push({
      ref: 'greeting',
      titleLines: [greetingTitle],
      imageUrl: HERO_IMAGE_URLS.greeting,
      imageAlt: shop.brand_name,
      primaryLabel: menuLabel,
      primaryIcon: 'lucide:utensils',
      primaryTo: menuTo.value
    })
  }

  list.push({
    ref: 'order',
    titleLines: [
      titleOf(copy.order_title_prefix, shop.brand_name),
      titleOf(copy.order_title_suffix, shop.tagline)
    ],
    description: messageOf(copy.order_subtitle, description),
    imageUrl: HERO_IMAGE_URLS.order,
    imageAlt: shop.brand_name,
    primaryLabel: (!props.statusOpen && props.closedCtaLabel) || props.primaryAction?.label || menuLabel,
    primaryIcon: 'lucide:utensils',
    primaryTo: menuTo.value
  })

  if (props.home.last_order_ref && props.reorderAction) {
    list.push({
      ref: 'reorder',
      titleLines: [
        titleOf(copy.reorder_title_prefix, 'Quer repetir seu'),
        `${titleOf(copy.reorder_title_suffix, 'último pedido')}${customerName ? `, ${customerName}` : ''}?`
      ],
      description: messageOf(copy.reorder_subtitle, 'Com um toque, seu favorito volta ao carrinho.'),
      imageUrl: HERO_IMAGE_URLS.reorder,
      imageAlt: shop.brand_name,
      primaryLabel: props.reorderAction.label || 'Pedir de novo',
      primaryIcon: 'lucide:rotate-ccw',
      primaryAction: props.reorderAction,
      secondaryLabel: menuLabel,
      secondaryTo: menuTo.value
    })
  } else {
    list.push({
      ref: 'greeting-return',
      titleLines: [greetingTitle],
      imageUrl: HERO_IMAGE_URLS.reorder,
      imageAlt: shop.brand_name,
      primaryLabel: menuLabel,
      primaryIcon: 'lucide:utensils',
      primaryTo: menuTo.value
    })
  }

  list.push({
    ref: 'handmade',
    titleLines: [
      titleOf(copy.handmade_title_prefix, 'Feito à mão,'),
      titleOf(copy.handmade_title_suffix, 'todo dia')
    ],
    description: messageOf(copy.handmade_subtitle, 'Do forno para a sua mesa.'),
    imageUrl: HERO_IMAGE_URLS.handmade,
    imageAlt: shop.brand_name,
    primaryLabel: menuLabel,
    primaryIcon: 'lucide:utensils',
    primaryTo: menuTo.value
  })

  return list
})
const activeSlide = computed(() => slides.value[activeIndex.value] || slides.value[0])
const heroTitleLabel = computed(() => activeSlide.value?.titleLines.join(' ') || '')

watch(slides, value => {
  if (activeIndex.value >= value.length) activeIndex.value = 0
})

watch(paused, value => {
  if (value && autoplayTimer) {
    clearInterval(autoplayTimer)
    autoplayTimer = null
  } else if (!value && !autoplayTimer && slides.value.length > 1) {
    autoplayTimer = setInterval(activateNextSlide, 8000)
  }
})

onMounted(() => {
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  if (!reduceMotion && slides.value.length > 1) {
    autoplayTimer = setInterval(activateNextSlide, 8000)
  }
})

onBeforeUnmount(() => {
  if (autoplayTimer) clearInterval(autoplayTimer)
})
</script>

<template>
  <section
    v-if="activeSlide"
    class="-mx-4 overflow-hidden rounded-none border-b bg-card text-card-foreground shadow-sm sm:mx-0 sm:rounded-lg sm:border"
    data-home-hero-carousel
    aria-roledescription="carousel"
    aria-label="Destaques da loja"
    @mouseenter="paused = true"
    @mouseleave="paused = false"
    @focusin="paused = true"
    @focusout="paused = false"
    @touchstart.passive="touchStartX = $event.changedTouches[0]?.screenX || 0"
    @touchend.passive="handleTouchEnd"
  >
    <div class="relative min-h-[calc(100svh-14.25rem)] select-none sm:min-h-[440px] lg:min-h-[480px]">
      <!-- Camada de imagens empilhada: crossfade por opacity (robusto — sem
           enter/leave do Vue a orfanar elementos durante autoplay/HMR). -->
      <div class="absolute inset-0 bg-muted">
        <template v-for="(slide, index) in slides" :key="slide.ref">
          <img
            v-if="slide.imageUrl"
            :src="slide.imageUrl"
            :alt="index === activeIndex ? slide.imageAlt : ''"
            :fetchpriority="index === 0 ? 'high' : undefined"
            :loading="index === 0 ? 'eager' : 'lazy'"
            decoding="async"
            aria-hidden="true"
            class="absolute inset-0 size-full object-cover transition-opacity duration-[900ms] ease-out motion-reduce:transition-none"
            :class="index === activeIndex ? 'opacity-100' : 'opacity-0'"
          >
        </template>
      </div>
      <div class="absolute inset-0 bg-[linear-gradient(0deg,rgba(0,0,0,.78),rgba(0,0,0,.42),rgba(0,0,0,.14))]" />

      <!-- Layout pôster: conteúdo ancorado embaixo (foto respira no topo). Sem
           flex-1 a empurrar — o bloco cresce pelo conteúdo, nunca sobrepõe. -->
      <div class="relative z-10 flex min-h-[calc(100svh-14.25rem)] flex-col justify-end px-5 pb-16 pt-12 text-center text-white sm:min-h-[440px] sm:px-7 sm:pb-20 sm:pt-16 lg:min-h-[480px] lg:px-9">
        <Transition name="hero-text" mode="out-in">
          <div :key="activeSlide.ref" class="mx-auto flex w-full max-w-3xl flex-col items-center justify-center">
            <p v-if="activeSlide.eyebrow" class="text-sm font-semibold uppercase tracking-wide text-white/80">{{ activeSlide.eyebrow }}</p>
            <h1 class="mt-2 text-4xl font-semibold leading-[1.08] tracking-tight [text-shadow:0_2px_18px_rgba(0,0,0,0.45)] sm:text-5xl" :aria-label="heroTitleLabel">
              <span v-for="line in activeSlide.titleLines" :key="line" class="block" aria-hidden="true">
                {{ line }}
              </span>
            </h1>
            <p v-if="activeSlide.description" class="mt-4 max-w-xl text-sm leading-6 text-white/85 [text-shadow:0_1px_10px_rgba(0,0,0,0.4)] sm:text-base">
              {{ activeSlide.description }}
            </p>
            <div class="mt-7 flex flex-wrap justify-center gap-3">
              <UiButton
                v-if="activeSlide.primaryTo"
                :to="activeSlide.primaryTo"
                size="lg"
                :icon="activeSlide.primaryIcon"
                class="shop-hero-cta bg-white text-neutral-900 shadow-lg hover:bg-white/90"
              >
                {{ activeSlide.primaryLabel }}
              </UiButton>
              <UiButton
                v-else
                size="lg"
                :icon="activeSlide.primaryIcon"
                :loading="props.reorderLoading"
                class="shop-hero-cta bg-white text-neutral-900 shadow-lg hover:bg-white/90"
                @click="handlePrimaryAction(activeSlide)"
              >
                {{ activeSlide.primaryLabel }}
              </UiButton>
              <UiButton
                v-if="activeSlide.secondaryTo"
                :to="activeSlide.secondaryTo"
                size="lg"
                variant="outline"
                class="shop-hero-cta-ghost border-white/40 bg-white/10 text-white backdrop-blur-sm hover:bg-white/20 hover:text-white"
              >
                {{ activeSlide.secondaryLabel }}
              </UiButton>
            </div>
          </div>
        </Transition>
      </div>

      <template v-if="slides.length > 1">
        <UiButton
          variant="ghost"
          size="icon-lg"
          icon="lucide:chevron-left"
          class="absolute left-2.5 top-1/2 z-20 size-11 -translate-y-1/2 rounded-full bg-black/35 text-white backdrop-blur-sm hover:bg-black/55 hover:text-white sm:left-3"
          aria-label="Slide anterior"
          @click="goToPreviousSlide"
        />
        <UiButton
          variant="ghost"
          size="icon-lg"
          icon="lucide:chevron-right"
          class="absolute right-2.5 top-1/2 z-20 size-11 -translate-y-1/2 rounded-full bg-black/35 text-white backdrop-blur-sm hover:bg-black/55 hover:text-white sm:right-3"
          aria-label="Próximo slide"
          @click="goToNextSlide"
        />
        <div class="absolute inset-x-0 bottom-3 z-20 flex items-center justify-center gap-1.5 sm:bottom-4" role="tablist" aria-label="Slides">
          <UiButton
            v-for="(slide, index) in slides"
            :key="slide.ref"
            variant="ghost"
            size="icon-xs"
            class="h-2 min-h-0 rounded-full p-0 hover:bg-white/70"
            :class="index === activeIndex ? 'w-6 bg-white' : 'w-2 bg-white/45'"
            :aria-label="`Slide ${index + 1}`"
            :aria-selected="index === activeIndex"
            role="tab"
            @click="goToSlide(index)"
          />
        </div>
      </template>
    </div>
  </section>
</template>
