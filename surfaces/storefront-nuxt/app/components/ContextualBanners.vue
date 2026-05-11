<script setup lang="ts">
import type { HomeProjection } from '~/types/shopman'

const props = defineProps<{ home: HomeProjection }>()

const { performReorder, pending: reorderPending } = useReorder()

const showBirthday = computed(() => props.home.omotenashi.is_birthday)
const showQuickReorder = computed(() => !!props.home.last_order_ref && !!props.home.omotenashi.customer_name)
const showClosing = computed(() => props.home.omotenashi.moment === 'fechando')
const showWhatsappWelcome = computed(() => props.home.origin_channel === 'whatsapp')

async function reorder () {
  if (props.home.last_order_ref) await performReorder(props.home.last_order_ref)
}

const closingHint = computed(() => {
  const closes = props.home.omotenashi.closes_at
  if (!closes) return 'Fechamos em breve'
  const [h, m] = closes.split(':')
  return m && m !== '00' ? `Fechamos às ${h}h${m}` : `Fechamos às ${h}h`
})
</script>

<template>
  <UContainer
    v-if="showBirthday || showQuickReorder || showClosing || showWhatsappWelcome"
    class="grid gap-3 pb-2"
  >
    <UAlert
      v-if="showBirthday"
      icon="i-lucide-gift"
      color="primary"
      variant="subtle"
      title="Feliz aniversário! 🎉"
      :description="`${home.omotenashi.customer_name || 'Você'}, hoje a casa quer celebrar com você. Aproveite seu mimo no carrinho.`"
    >
      <template #actions>
        <UButton label="Ver cardápio" to="/menu" color="primary" variant="solid" size="sm" trailing-icon="i-lucide-arrow-right" />
      </template>
    </UAlert>

    <UAlert
      v-if="showQuickReorder"
      icon="i-lucide-rotate-ccw"
      color="info"
      variant="subtle"
      title="Bem-vindo de volta!"
      :description="`Quer repetir seu último pedido, ${home.omotenashi.customer_name}? A gente prepara igualzinho.`"
    >
      <template #actions>
        <UButton
          label="Repetir pedido"
          color="info"
          variant="solid"
          size="sm"
          icon="i-lucide-rotate-ccw"
          :loading="reorderPending"
          @click="reorder"
        />
      </template>
    </UAlert>

    <UAlert
      v-if="showClosing"
      icon="i-lucide-clock"
      color="warning"
      variant="subtle"
      title="Últimos pedidos do dia"
      :description="`${closingHint}. Aproveita pra garantir o seu antes de fechar.`"
    />

    <UAlert
      v-if="showWhatsappWelcome"
      icon="i-lucide-message-circle"
      color="success"
      variant="subtle"
      title="Que bom te receber por aqui"
      description="Você chegou pelo WhatsApp! Continue navegando, e qualquer dúvida é só chamar."
    >
      <template v-if="home.shop.whatsapp_url" #actions>
        <UButton
          :to="home.shop.whatsapp_url"
          target="_blank"
          rel="noopener"
          label="Abrir WhatsApp"
          color="success"
          variant="solid"
          size="sm"
          icon="i-lucide-message-circle"
        />
      </template>
    </UAlert>
  </UContainer>
</template>
