<script setup lang="ts">
// Avisos de preferência alimentar (WP-5). Omotenashi: informar, nunca esconder
// sem avisar nem alarmar. Badge âmbar discreto com ícone, só quando há conflito
// CLARO com uma preferência ATIVA do cliente logado (vazio p/ anônimo/sem conflito).
defineProps<{
  warnings: string[]
}>()
</script>

<template>
  <div v-if="warnings.length" class="flex flex-wrap gap-1">
    <UiBadge
      v-for="warning in warnings"
      :key="warning"
      variant="warning"
      class="gap-1 font-normal"
    >
      <Icon name="lucide:triangle-alert" class="size-3" />
      {{ warning }}
    </UiBadge>
  </div>
</template>
