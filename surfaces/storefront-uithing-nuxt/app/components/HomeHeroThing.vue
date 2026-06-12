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

const featured = computed(() => props.home.featured_items || [])
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

function imageAt (index: number) {
  return featured.value[index]?.image_url || featured.value[0]?.image_url || null
}

function imageAltAt (index: number, fallback: string) {
  return featured.value[index]?.name || fallback
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

function handleTouchEnd (event: TouchEvent) {
  const dx = event.changedTouches[0]?.screenX - touchStartX.value
  if (Math.abs(dx) < 50) return
  if (dx < 0) activateNextSlide()
  else activatePreviousSlide()
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
      imageUrl: imageAt(0),
      imageAlt: imageAltAt(0, shop.brand_name),
      primaryLabel: titleOf(copy.birthday_cta, titleOf(copy.menu_cta, 'Ver cardápio')),
      primaryIcon: 'lucide:gift',
      primaryTo: menuTo.value
    })
  } else {
    list.push({
      ref: 'greeting',
      titleLines: [greetingTitle],
      imageUrl: imageAt(0),
      imageAlt: imageAltAt(0, shop.brand_name),
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
    imageUrl: imageAt(1),
    imageAlt: imageAltAt(1, shop.brand_name),
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
      imageUrl: imageAt(2),
      imageAlt: imageAltAt(2, shop.brand_name),
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
      imageUrl: imageAt(2),
      imageAlt: imageAltAt(2, shop.brand_name),
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
    imageUrl: imageAt(3),
    imageAlt: imageAltAt(3, shop.brand_name),
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
    class="-mx-4 overflow-hidden rounded-none border-y bg-card text-card-foreground shadow-sm sm:mx-0 sm:rounded-lg sm:border"
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
      <Transition name="hero-fade">
        <img
          v-if="activeSlide.imageUrl"
          :key="activeSlide.ref"
          :src="activeSlide.imageUrl"
          :alt="activeSlide.imageAlt"
          fetchpriority="high"
          decoding="async"
          class="absolute inset-0 size-full object-cover"
        >
        <div v-else class="absolute inset-0 bg-muted" />
      </Transition>
      <div class="absolute inset-0 bg-[linear-gradient(0deg,rgba(0,0,0,.74),rgba(0,0,0,.34),rgba(0,0,0,.18))]" />

      <div class="relative z-10 flex min-h-[calc(100svh-14.25rem)] items-center justify-center px-5 pb-12 pt-12 text-center text-white sm:min-h-[440px] sm:px-7 sm:py-20 lg:min-h-[480px] lg:px-9">
        <Transition name="hero-text" mode="out-in">
          <div :key="activeSlide.ref" class="mx-auto flex max-w-3xl flex-col items-center">
          <p v-if="activeSlide.eyebrow" class="text-sm font-medium text-white/80">{{ activeSlide.eyebrow }}</p>
          <h1 class="mt-2 text-4xl font-semibold leading-tight sm:text-5xl" :aria-label="heroTitleLabel">
            <span v-for="line in activeSlide.titleLines" :key="line" class="block" aria-hidden="true">
              {{ line }}
            </span>
          </h1>
          <p v-if="activeSlide.description" class="mt-4 max-w-xl text-sm leading-6 text-white/84 sm:text-base">
            {{ activeSlide.description }}
          </p>
          <div class="mt-6 flex flex-wrap justify-center gap-3">
            <UiButton
              v-if="activeSlide.primaryTo"
              :to="activeSlide.primaryTo"
              size="lg"
              :icon="activeSlide.primaryIcon"
            >
              {{ activeSlide.primaryLabel }}
            </UiButton>
            <UiButton
              v-else
              size="lg"
              :icon="activeSlide.primaryIcon"
              :loading="props.reorderLoading"
              @click="handlePrimaryAction(activeSlide)"
            >
              {{ activeSlide.primaryLabel }}
            </UiButton>
            <UiButton
              v-if="activeSlide.secondaryTo"
              :to="activeSlide.secondaryTo"
              size="lg"
              variant="outline"
              class="border-white/30 bg-white/5 text-white hover:bg-white/10 hover:text-white"
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
          size="icon-sm"
          icon="lucide:chevron-left"
          class="absolute left-3 top-1/2 z-20 -translate-y-1/2 rounded-full bg-white/15 text-white hover:bg-white/25 hover:text-white"
          aria-label="Slide anterior"
          @click="activatePreviousSlide"
        />
        <UiButton
          variant="ghost"
          size="icon-sm"
          icon="lucide:chevron-right"
          class="absolute right-3 top-1/2 z-20 -translate-y-1/2 rounded-full bg-white/15 text-white hover:bg-white/25 hover:text-white"
          aria-label="Próximo slide"
          @click="activateNextSlide"
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
            @click="activateSlide(index)"
          />
        </div>
      </template>
    </div>
  </section>
</template>
