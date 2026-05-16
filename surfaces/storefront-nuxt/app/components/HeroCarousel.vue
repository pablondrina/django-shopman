<script setup lang="ts">
import type { HomeProjection } from '~/types/shopman'

const props = defineProps<{ home: HomeProjection }>()
const { performReorderAction, pending: reorderPending } = useReorder()

interface HeroSlide {
  eyebrow?: string
  titleLines: string[]
  description?: string
  cta: { label: string, to?: string, action?: 'reorder' }
  secondaryCta?: { label: string, to: string }
  image: string
}

function copyTitle (entry: { title: string }, fallback: string): string {
  return entry.title || fallback
}

function copyMessage (entry: { message: string }, fallback = ''): string {
  return entry.message || fallback
}

function sentence (value: string): string {
  const trimmed = value.trim()
  if (!trimmed) return ''
  return /[.!?]$/.test(trimmed) ? trimmed : `${trimmed}.`
}

const reorderAction = computed(() =>
  (props.home.actions || []).find(action => action.ref === 'reorder' && action.enabled !== false) || null
)

const slides = computed<HeroSlide[]>(() => {
  const omo = props.home.omotenashi
  const copy = props.home.hero_copy
  const customerName = omo.customer_name?.trim()
  const menuCta = copyTitle(copy.menu_cta, 'Ver Cardápio')
  const handmadeTitle = `${copyTitle(copy.handmade_title_prefix, 'Feito à mão,')} ${copyTitle(copy.handmade_title_suffix, 'todo dia')}`
  const greetingTitle = sentence(omo.greeting_with_name || handmadeTitle)
  const list: HeroSlide[] = []

  if (omo.is_birthday) {
    const birthdayTitle = copyTitle(copy.birthday_heading, 'Feliz aniversário')
    list.push({
      titleLines: [`${birthdayTitle}${customerName ? `, ${customerName}` : ''}!`],
      description: copyMessage(copy.birthday_sub, 'Seu desconto especial de aniversário já está ativo.'),
      cta: { label: copyTitle(copy.birthday_cta, menuCta), to: '/menu' },
      image: 'https://images.unsplash.com/photo-1488477181946-6428a0291777?auto=format&fit=crop&w=1600&q=80'
    })
  } else {
    list.push({
      titleLines: [greetingTitle],
      description: omo.shop_hint || undefined,
      cta: { label: menuCta, to: '/menu' },
      image: 'https://images.unsplash.com/photo-1509440159596-0249088772ff?auto=format&fit=crop&w=1600&q=80'
    })
  }

  list.push({
    titleLines: [
      copyTitle(copy.order_title_prefix, 'Peça. Acompanhe.'),
      copyTitle(copy.order_title_suffix, 'Aproveite.')
    ],
    description: copyMessage(copy.order_subtitle, 'Retire na loja ou receba em casa.'),
    cta: { label: menuCta, to: '/menu' },
    image: 'https://images.unsplash.com/photo-1517433670267-08bbd4be890f?auto=format&fit=crop&w=1600&q=80'
  })

  if (props.home.last_order_ref && reorderAction.value) {
    list.push({
      titleLines: [
        copyTitle(copy.reorder_title_prefix, 'Quer repetir seu'),
        `${copyTitle(copy.reorder_title_suffix, 'último pedido')}${customerName ? `, ${customerName}` : ''}?`
      ],
      description: copyMessage(copy.reorder_subtitle, 'Com um toque, seu favorito volta ao carrinho.'),
      cta: { label: 'Repetir pedido', action: 'reorder' },
      secondaryCta: { label: menuCta, to: '/menu' },
      image: 'https://images.unsplash.com/photo-1568254183919-78a4f43a2877?auto=format&fit=crop&w=1600&q=80'
    })
  } else {
    list.push({
      titleLines: [greetingTitle],
      description: omo.shop_hint || undefined,
      cta: { label: menuCta, to: '/menu' },
      image: 'https://images.unsplash.com/photo-1568254183919-78a4f43a2877?auto=format&fit=crop&w=1600&q=80'
    })
  }

  list.push({
    titleLines: [
      copyTitle(copy.handmade_title_prefix, 'Feito à mão,'),
      copyTitle(copy.handmade_title_suffix, 'todo dia')
    ],
    description: copyMessage(copy.handmade_subtitle, 'Do forno para a sua mesa.'),
    cta: { label: menuCta, to: '/menu' },
    image: 'https://images.unsplash.com/photo-1608198093002-ad4e005484ec?auto=format&fit=crop&w=1600&q=80'
  })

  return list
})

async function activateSlideCta (item: HeroSlide) {
  if (item.cta.action === 'reorder' && props.home.last_order_ref && reorderAction.value) {
    await performReorderAction(reorderAction.value, props.home.last_order_ref)
  }
}
</script>

<template>
  <section class="relative isolate overflow-hidden border-b border-default bg-default text-white">
    <UCarousel
      v-slot="{ item }"
      :items="slides"
      :autoplay="{ delay: 6000 }"
      :ui="{
        viewport: 'overflow-hidden',
        container: 'flex items-stretch',
        item: 'min-w-0 shrink-0 basis-full ps-0',
        dots: 'absolute inset-x-0 bottom-4 z-20 flex items-center justify-center gap-2',
        dot: 'size-2 rounded-full bg-white/45 transition data-[state=active]:w-6 data-[state=active]:bg-white'
      }"
      loop
      dots
      fade
      class="w-full overflow-hidden"
    >
      <article class="relative isolate overflow-hidden bg-neutral-950">
        <img
          :src="item.image"
          alt=""
          loading="eager"
          fetchpriority="high"
          decoding="async"
          sizes="100vw"
          class="absolute inset-0 size-full object-cover"
        >
        <div class="absolute inset-0 bg-gradient-to-t from-black/82 via-black/48 to-black/18" />
        <div class="relative mx-auto flex min-h-[560px] w-full max-w-(--ui-container) items-center px-4 py-20 sm:min-h-[640px] sm:px-6 lg:px-8 lg:py-24">
          <div class="w-full max-w-3xl">
            <p v-if="item.eyebrow" class="shop-section-kicker text-white/85">
              {{ item.eyebrow }}
            </p>
            <h1 class="shop-hero-copy text-4xl font-bold leading-tight text-white sm:text-5xl lg:text-6xl">
              <span v-for="line in item.titleLines" :key="line" class="block">
                {{ line }}
              </span>
            </h1>
            <p v-if="item.description" class="mt-5 max-w-xl text-base leading-relaxed text-white/78 sm:text-lg">
              {{ item.description }}
            </p>
            <div class="mt-7 flex flex-wrap gap-3">
              <UButton
                v-if="item.cta.to"
                :label="item.cta.label"
                :to="item.cta.to"
                size="xl"
                color="neutral"
                variant="solid"
              />
              <UButton
                v-else
                :label="item.cta.label"
                size="xl"
                color="neutral"
                variant="solid"
                :loading="reorderPending"
                @click="activateSlideCta(item)"
              />
              <UButton
                v-if="item.secondaryCta"
                :label="item.secondaryCta.label"
                :to="item.secondaryCta.to"
                size="xl"
                color="neutral"
                variant="outline"
                class="bg-white/5 text-white ring-white/30 hover:bg-white/10"
              />
            </div>
          </div>
        </div>
      </article>
    </UCarousel>
  </section>
</template>
