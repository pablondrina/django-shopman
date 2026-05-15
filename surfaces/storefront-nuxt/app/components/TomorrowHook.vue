<script setup lang="ts">
import type { OmotenashiProjection } from '~/types/shopman'

const props = defineProps<{ omotenashi: OmotenashiProjection }>()

const show = computed(() => ['tarde', 'fechando', 'fechado'].includes(props.omotenashi.moment))

const message = computed(() => {
  switch (props.omotenashi.moment) {
    case 'tarde':
      return 'Alguns itens podem ficar para outro horário. Consulte o cardápio e escolha uma opção disponível.'
    case 'fechando':
      return 'A casa encerra em breve. Você ainda pode consultar opções disponíveis ou programar para outro horário.'
    case 'fechado':
      return 'A casa está fechada agora. Consulte o cardápio para ver opções de encomenda quando a agenda permitir.'
    default:
      return ''
  }
})
</script>

<template>
  <UContainer v-if="show" class="pb-4">
    <UPageCard
      title="Próximo horário"
      :description="message"
      orientation="horizontal"
      variant="subtle"
      :ui="{ container: 'p-6 sm:p-8 items-center', title: 'text-lg sm:text-xl' }"
    >
      <div class="flex justify-end">
        <UButton label="Ver cardápio" to="/menu" />
      </div>
    </UPageCard>
  </UContainer>
</template>
