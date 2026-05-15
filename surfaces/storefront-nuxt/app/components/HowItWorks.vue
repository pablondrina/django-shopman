<script setup lang="ts">
import type { OpeningHoursEntry } from '~/types/shopman'

defineProps<{ openingHours: OpeningHoursEntry[] }>()

const onlineSteps = [
  {
    title: 'Escolha os itens',
    description: 'Navegue pelo cardápio, veja disponibilidade e monte o pedido no seu ritmo.'
  },
  {
    title: 'Revise e pague',
    description: 'Confira retirada, entrega, horário, pagamento e dados de contato antes de enviar.'
  },
  {
    title: 'Acompanhe o pedido',
    description: 'O status fica disponível na página do pedido.'
  }
] as const

const storeFeatures = [
  {
    title: 'Atendimento no balcão',
    description: 'Passe na loja para escolher direto com a equipe.'
  },
  {
    title: 'Disponibilidade informada',
    description: 'O cardápio mostra os itens publicados e os avisos enviados pela loja.'
  }
] as const
</script>

<template>
  <UPageSection
    headline="Como funciona"
    title="Como pedir"
    description="Escolha no cardápio, revise os dados, finalize e acompanhe o pedido."
    :ui="{ container: 'py-12 sm:py-16', headline: 'text-primary uppercase text-xs font-semibold' }"
  >
    <div class="grid lg:grid-cols-2 gap-6">
      <UPageCard
        title="Pelo site"
        description="Escolha, revise e acompanhe."
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
                {{ step.title }}
              </p>
              <p class="text-sm text-muted leading-relaxed mt-1">{{ step.description }}</p>
            </div>
          </li>
        </ol>
      </UPageCard>

      <UPageCard
        title="Na casa"
        description="Escolha direto com a equipe."
        variant="subtle"
        :ui="{ container: 'p-6 sm:p-8' }"
      >
        <div class="grid gap-5 mt-6">
          <div
            v-for="feature in storeFeatures"
            :key="feature.title"
            class="flex items-start gap-4"
          >
            <span class="mt-1.5 size-2 shrink-0 rounded-full bg-primary" aria-hidden="true" />
            <div>
              <p class="font-semibold text-highlighted">{{ feature.title }}</p>
              <p class="text-sm text-muted leading-relaxed mt-1">{{ feature.description }}</p>
            </div>
          </div>

          <USeparator v-if="openingHours.length" />

          <div v-if="openingHours.length">
            <p class="text-xs uppercase font-semibold text-muted mb-3 flex items-center gap-2">
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
