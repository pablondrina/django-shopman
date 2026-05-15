<script setup lang="ts">
import type { HomeProjection } from '~/types/shopman'

const props = defineProps<{ home: HomeProjection }>()
const { performReorder, pending: reorderPending } = useReorder()

interface HeroSlide {
  eyebrow?: string
  title: string
  description: string
  cta: { label: string, to?: string, action?: 'reorder' }
  secondaryCta?: { label: string, to: string }
  image: string
}

const slides = computed<HeroSlide[]>(() => {
  const omo = props.home.omotenashi
  const list: HeroSlide[] = []

  if (omo.is_birthday) {
    list.push({
      eyebrow: 'Feliz aniversário',
      title: `Olá, ${omo.customer_name || 'cliente'}.`,
      description: 'Seu cadastro indica aniversário hoje. Confira as opções disponíveis no cardápio.',
      cta: { label: 'Ver cardápio', to: '/menu' },
      image: 'https://images.unsplash.com/photo-1488477181946-6428a0291777?auto=format&fit=crop&w=1600&q=80'
    })
  }

  list.push({
    eyebrow: omo.shop_hint || 'Cardápio online',
    title: omo.greeting_with_name || 'Feito à mão, todo dia.',
    description: props.home.shop_status.message || 'Consulte a disponibilidade, peça e acompanhe.',
    cta: { label: 'Ver cardápio', to: '/menu' },
    image: 'https://images.unsplash.com/photo-1509440159596-0249088772ff?auto=format&fit=crop&w=1600&q=80'
  })

  list.push({
    eyebrow: 'Pedido online',
    title: 'Peça e acompanhe.',
    description: 'Acompanhe o pedido do pagamento à retirada ou entrega.',
    cta: { label: 'Começar pedido', to: '/menu' },
    image: 'https://images.unsplash.com/photo-1555507036-ab1f4038808a?auto=format&fit=crop&w=1600&q=80'
  })

  if (props.home.last_order_ref) {
    list.push({
      eyebrow: `De volta, ${omo.customer_name || ''}?`.trim(),
      title: 'Pedir de novo.',
      description: 'Revise os itens antes de adicionar ao carrinho.',
      cta: { label: 'Repetir pedido', action: 'reorder' },
      secondaryCta: { label: 'Ver cardápio', to: '/menu' },
      image: 'https://images.unsplash.com/photo-1517686469429-8bdb88b9f907?auto=format&fit=crop&w=1600&q=80'
    })
  }

  list.push({
    eyebrow: 'Cardápio publicado',
    title: 'Escolhas da casa.',
    description: 'Itens publicados aparecem com a disponibilidade informada pela loja.',
    cta: { label: 'Conhecer cardápio', to: '/menu' },
    image: 'https://images.unsplash.com/photo-1549931319-a545dcf3bc73?auto=format&fit=crop&w=1600&q=80'
  })

  return list
})

async function activateSlideCta (item: HeroSlide) {
  if (item.cta.action === 'reorder' && props.home.last_order_ref) {
    await performReorder(props.home.last_order_ref)
  }
}
</script>

<template>
  <section class="relative bg-default text-default sm:py-4">
    <UContainer class="px-0 sm:px-4">
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
      class="w-full overflow-hidden sm:rounded-lg"
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
        <div class="relative flex min-h-[calc(82svh-var(--ui-header-height))] items-center justify-center px-6 py-16 text-center sm:min-h-[520px] sm:px-10 lg:min-h-[560px]">
          <div class="mx-auto max-w-3xl">
            <p v-if="item.eyebrow" class="shop-section-kicker justify-center text-white/85">
              {{ item.eyebrow }}
            </p>
            <h1 class="shop-hero-copy mt-4 text-4xl font-bold leading-tight text-white sm:text-5xl lg:text-6xl">
              {{ item.title }}
            </h1>
            <p class="mx-auto mt-5 max-w-xl text-base leading-relaxed text-white/78 sm:text-lg">
              {{ item.description }}
            </p>
            <div class="mt-7 flex flex-wrap justify-center gap-3">
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
  </UContainer>
  </section>
</template>
