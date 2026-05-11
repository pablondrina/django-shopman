<script setup lang="ts">
import type { OmotenashiProjection } from '~/types/shopman'

const props = defineProps<{ omotenashi: OmotenashiProjection }>()

const show = computed(() => ['tarde', 'fechando', 'fechado'].includes(props.omotenashi.moment))

const message = computed(() => {
  switch (props.omotenashi.moment) {
    case 'tarde':
      return 'Hoje a fornada já tá indo embora. Mas amanhã, bem cedinho, sai outra. Que tal já deixar seu pedido encomendado?'
    case 'fechando':
      return 'A casa tá fechando. Mas amanhã, bem cedinho, tem fornada nova. Pedido encomendado garante o melhor lugar.'
    case 'fechado':
      return 'A casa fechou por hoje. Mas amanhã, bem cedinho, tem pão saindo do forno. Já deixa seu pedido encomendado.'
    default:
      return ''
  }
})
</script>

<template>
  <UContainer v-if="show" class="pb-4">
    <UPageCard
      icon="i-lucide-sunrise"
      title="Amanhã, bem cedinho"
      :description="message"
      orientation="horizontal"
      variant="subtle"
      :ui="{ container: 'p-6 sm:p-8 items-center', title: 'text-lg sm:text-xl' }"
    >
      <div class="flex justify-end">
        <UButton label="Encomendar pra amanhã" to="/menu" trailing icon="i-lucide-arrow-right" />
      </div>
    </UPageCard>
  </UContainer>
</template>
