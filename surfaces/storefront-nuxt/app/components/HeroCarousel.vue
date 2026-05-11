<script setup lang="ts">
import type { HomeProjection } from '~/types/shopman'

const props = defineProps<{ home: HomeProjection }>()

interface HeroSlide {
  eyebrow?: string
  title: string
  description: string
  cta: { label: string, to: string }
  secondaryCta?: { label: string, to: string }
  image: string
}

const slides = computed<HeroSlide[]>(() => {
  const omo = props.home.omotenashi
  const list: HeroSlide[] = []

  if (omo.is_birthday) {
    list.push({
      eyebrow: 'Feliz aniversário',
      title: `Hoje o dia é seu, ${omo.customer_name || 'querido'}.`,
      description: 'Tem um docinho separado pra você. A casa quer celebrar contigo.',
      cta: { label: 'Ver cardápio', to: '/menu' },
      image: 'https://images.unsplash.com/photo-1488477181946-6428a0291777?auto=format&fit=crop&w=1600&q=80'
    })
  }

  list.push({
    eyebrow: omo.shop_hint || 'Fresquinho do forno',
    title: 'Feito à mão, todo dia.',
    description: 'Do forno para a sua mesa. Escolha, peça e acompanhe — tudo no seu tempo.',
    cta: { label: 'Ver cardápio', to: '/menu' },
    image: 'https://images.unsplash.com/photo-1509440159596-0249088772ff?auto=format&fit=crop&w=1600&q=80'
  })

  list.push({
    eyebrow: 'Acompanhamos cada pedido',
    title: 'Peça. Acompanhe. Aproveite.',
    description: 'Pedido pronto na hora certa, do jeitinho que você gosta.',
    cta: { label: 'Começar pedido', to: '/menu' },
    image: 'https://images.unsplash.com/photo-1555507036-ab1f4038808a?auto=format&fit=crop&w=1600&q=80'
  })

  if (props.home.last_order_ref) {
    list.push({
      eyebrow: `De volta, ${omo.customer_name || ''}?`.trim(),
      title: 'Repita seu último pedido.',
      description: 'Em dois cliques, do mesmo jeito que você gosta.',
      cta: { label: 'Repetir pedido', to: '/menu' },
      secondaryCta: { label: 'Ver cardápio', to: '/menu' },
      image: 'https://images.unsplash.com/photo-1517686469429-8bdb88b9f907?auto=format&fit=crop&w=1600&q=80'
    })
  }

  list.push({
    eyebrow: 'Cuidado em cada detalhe',
    title: 'Receitas que demoram, sabores que ficam.',
    description: 'Fermentação lenta, ingredientes selecionados, mãos atentas.',
    cta: { label: 'Conhecer cardápio', to: '/menu' },
    image: 'https://images.unsplash.com/photo-1549931319-a545dcf3bc73?auto=format&fit=crop&w=1600&q=80'
  })

  return list
})
</script>

<template>
  <section class="dark relative isolate overflow-hidden bg-default text-default">
    <UCarousel
      v-slot="{ item }"
      :items="slides"
      :autoplay="{ delay: 6000 }"
      :ui="{ item: 'basis-full min-w-0' }"
      loop
      dots
      class="w-full"
    >
      <article class="relative isolate overflow-hidden">
        <img
          :src="item.image"
          alt=""
          loading="eager"
          class="absolute inset-0 size-full object-cover"
        >
        <div class="absolute inset-0 bg-gradient-to-t from-black/85 via-black/55 to-black/25" />
        <UContainer class="relative py-20 sm:py-28 lg:py-36">
          <div class="max-w-2xl">
            <p v-if="item.eyebrow" class="text-sm uppercase tracking-wider font-medium text-muted">
              {{ item.eyebrow }}
            </p>
            <h1 class="mt-3 text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight leading-[1.1] text-highlighted">
              {{ item.title }}
            </h1>
            <p class="mt-5 text-base sm:text-lg leading-relaxed text-muted max-w-xl">
              {{ item.description }}
            </p>
            <div class="mt-8 flex flex-wrap gap-3">
              <UButton
                :label="item.cta.label"
                :to="item.cta.to"
                size="xl"
                color="neutral"
                variant="solid"
                icon="i-lucide-arrow-right"
                trailing
              />
              <UButton
                v-if="item.secondaryCta"
                :label="item.secondaryCta.label"
                :to="item.secondaryCta.to"
                size="xl"
                color="neutral"
                variant="outline"
              />
            </div>
          </div>
        </UContainer>
      </article>
    </UCarousel>
  </section>
</template>
