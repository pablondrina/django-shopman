<script setup lang="ts">
import type { OpeningHoursEntry } from '~/types/shopman'

defineProps<{ openingHours: OpeningHoursEntry[] }>()

const onlineSteps = [
  {
    icon: 'i-lucide-utensils',
    title: 'Escolha o que apetece',
    description: 'Navegue pelo cardápio e monte seu pedido sem pressa. Pode salvar pra finalizar depois.'
  },
  {
    icon: 'i-lucide-credit-card',
    title: 'Pague do seu jeito',
    description: 'Pix, cartão ou na retirada. A confirmação é otimista — se algo der errado, a gente te avisa antes.'
  },
  {
    icon: 'i-lucide-package-check',
    title: 'Acompanhe e retire',
    description: 'A gente te avisa quando estiver pronto. Você passa, retira e volta pra rotina.'
  }
] as const

const storeFeatures = [
  {
    icon: 'i-lucide-store',
    title: 'Vitrine completa',
    description: 'Pão fresquinho, doces da casa e o cheirinho de café que abre o dia.'
  },
  {
    icon: 'i-lucide-coffee',
    title: 'Cafezinho na casa',
    description: 'Aquele espresso bem tirado, ou um café com leite pra acompanhar a fornada.'
  }
] as const
</script>

<template>
  <UPageSection
    headline="Como funciona"
    title="Dois jeitos de aproveitar"
    description="Se preferir resolver tudo daqui, segue um caminho. Se quiser passar e dar uma olhadinha, segue outro. Tanto faz, a casa te recebe igual."
    :ui="{ container: 'py-12 sm:py-16', headline: 'text-primary uppercase tracking-wide text-xs font-semibold' }"
  >
    <div class="grid lg:grid-cols-2 gap-6">
      <UPageCard
        title="Pelo site"
        description="Pedido pronto pra retirar, sem fila."
        icon="i-lucide-smartphone"
        variant="subtle"
        :ui="{ container: 'p-6 sm:p-8' }"
      >
        <ol class="grid gap-5 mt-6">
          <li
            v-for="(step, idx) in onlineSteps"
            :key="step.title"
            class="flex items-start gap-4"
          >
            <span class="flex size-9 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary font-semibold tabular-nums">
              {{ idx + 1 }}
            </span>
            <div>
              <p class="font-semibold text-highlighted flex items-center gap-2">
                <UIcon :name="step.icon" class="size-4 text-muted" />
                {{ step.title }}
              </p>
              <p class="text-sm text-muted leading-relaxed mt-1">{{ step.description }}</p>
            </div>
          </li>
        </ol>
      </UPageCard>

      <UPageCard
        title="Na casa"
        description="Passa, escolhe e leva. Igual padaria de bairro deve ser."
        icon="i-lucide-store"
        variant="subtle"
        :ui="{ container: 'p-6 sm:p-8' }"
      >
        <div class="grid gap-5 mt-6">
          <div
            v-for="feature in storeFeatures"
            :key="feature.title"
            class="flex items-start gap-4"
          >
            <span class="flex size-9 shrink-0 items-center justify-center rounded-full bg-elevated text-muted">
              <UIcon :name="feature.icon" class="size-5" />
            </span>
            <div>
              <p class="font-semibold text-highlighted">{{ feature.title }}</p>
              <p class="text-sm text-muted leading-relaxed mt-1">{{ feature.description }}</p>
            </div>
          </div>

          <USeparator v-if="openingHours.length" />

          <div v-if="openingHours.length">
            <p class="text-xs uppercase tracking-wide font-semibold text-muted mb-3 flex items-center gap-2">
              <UIcon name="i-lucide-clock" class="size-3.5" />
              Horário de funcionamento
            </p>
            <dl class="grid gap-1.5 text-sm">
              <div
                v-for="entry in openingHours"
                :key="entry.label"
                class="flex justify-between gap-4 tabular-nums"
              >
                <dt class="text-muted">{{ entry.label }}</dt>
                <dd class="font-medium text-highlighted">{{ entry.hours }}</dd>
              </div>
            </dl>
          </div>
        </div>
      </UPageCard>
    </div>
  </UPageSection>
</template>
