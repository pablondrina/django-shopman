<script setup lang="ts">
import type { HomeSectionsCopyProjection, OmotenashiProjection } from '~/types/shopman'

const props = defineProps<{
  omotenashi: OmotenashiProjection
  copy: HomeSectionsCopyProjection
}>()

const show = computed(() => ['tarde', 'fechando', 'fechado'].includes(props.omotenashi.moment))

const message = computed(() => {
  if (props.copy.tomorrow_hook.message) return props.copy.tomorrow_hook.message
  switch (props.omotenashi.moment) {
    case 'tarde':
      return 'Alguns itens podem ficar para outro horário. Consulte o cardápio e escolha uma opção disponível.'
    case 'fechando':
      return 'Estamos encerrando em breve. Você ainda pode consultar opções disponíveis ou programar para outro horário.'
    case 'fechado':
      return 'Estamos fechados agora. Consulte o cardápio para ver opções de encomenda quando a agenda permitir.'
    default:
      return ''
  }
})
</script>

<template>
  <UContainer v-if="show" class="pb-4">
    <UPageCard
      :title="copy.tomorrow_label.title"
      :description="message"
      orientation="horizontal"
      variant="subtle"
    >
      <div class="flex justify-end">
        <UButton label="Ver cardápio" to="/menu" />
      </div>
    </UPageCard>
  </UContainer>
</template>
