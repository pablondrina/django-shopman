<script setup lang="ts">
import type { CartItemProjection } from '~/types/shopman'

const props = defineProps<{ item: CartItemProjection }>()

const { formatted, expired } = useCountdown(() => props.item.confirmation_deadline_iso)

const showAwaiting = computed(() => props.item.is_awaiting_confirmation && !props.item.is_ready_for_confirmation)
const showReady = computed(() => props.item.is_ready_for_confirmation && !expired.value)
const showExpired = computed(() => props.item.is_ready_for_confirmation && expired.value)
</script>

<template>
  <UAlert
    v-if="showAwaiting"
    icon="i-lucide-hourglass"
    color="warning"
    variant="subtle"
    title="Aguardando confirmação"
    description="Estamos separando seu item. Avisamos assim que estiver pronto."
  />

  <UAlert
    v-else-if="showReady"
    icon="i-lucide-circle-check"
    color="success"
    variant="subtle"
    title="Tudo pronto! Confirme até"
    :description="`Reservamos seu item até ${item.confirmation_deadline_display}. Faltam ${formatted}.`"
  />

  <UAlert
    v-else-if="showExpired"
    icon="i-lucide-clock-alert"
    color="warning"
    variant="subtle"
    title="Tempo de reserva expirou"
    description="A reserva será liberada. Confirme novamente se ainda quer levar."
  />
</template>
