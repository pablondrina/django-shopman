<script setup lang="ts">
import type { HomeProjection } from '~/types/shopman'

const props = defineProps<{ home: HomeProjection }>()

const { performReorderAction, pending: reorderPending } = useReorder()

const showBirthday = computed(() => props.home.omotenashi.is_birthday)
const reorderAction = computed(() =>
  (props.home.actions || []).find(action => action.ref === 'reorder' && action.enabled !== false) || null
)
const showQuickReorder = computed(() => !!props.home.last_order_ref && !!props.home.omotenashi.customer_name && !!reorderAction.value)
const showClosing = computed(() => props.home.omotenashi.moment === 'fechando')
const showWhatsappWelcome = computed(() => props.home.origin_channel === 'whatsapp')
const quickReorderItems = computed(() => props.home.last_order_items.slice(0, 4))

async function reorder () {
  if (props.home.last_order_ref && reorderAction.value) await performReorderAction(reorderAction.value, props.home.last_order_ref)
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
    class="relative z-10 grid gap-3 py-4 sm:py-5 lg:grid-cols-2"
  >
    <UCard
      v-if="showBirthday"
      class="shop-soft-panel"
      :ui="{ body: 'p-4 sm:p-5' }"
    >
      <div class="flex items-center gap-4">
        <div class="min-w-0 flex-1">
          <p class="font-semibold text-highlighted">Feliz aniversário!</p>
          <p class="text-sm text-muted">{{ home.omotenashi.customer_name || 'Você' }}, confira as opções disponíveis hoje.</p>
        </div>
        <UButton label="Ver" to="/menu" color="primary" variant="solid" size="sm" />
      </div>
    </UCard>

    <UCard
      v-if="showQuickReorder"
      class="shop-soft-panel"
      :ui="{ body: 'p-5 sm:p-6' }"
    >
      <div class="grid gap-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
        <div class="min-w-0">
          <p class="text-base font-semibold text-highlighted">Quer repetir seu último pedido?</p>
          <ul
            v-if="quickReorderItems.length"
            class="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-sm text-muted"
            aria-label="Itens do último pedido"
          >
            <li v-for="line in quickReorderItems" :key="line.sku" class="min-w-0">
              <span class="font-medium text-highlighted">{{ line.qty }}×</span>
              <span> {{ line.name }}</span>
            </li>
          </ul>
          <p v-else class="mt-1 text-sm text-muted">O pedido anterior volta ao carrinho para revisão.</p>
        </div>
        <UButton
          label="Repetir pedido"
          color="neutral"
          variant="solid"
          size="md"
          class="sm:justify-self-end"
          :loading="reorderPending"
          @click="reorder"
        />
      </div>
    </UCard>

    <UCard
      v-if="showClosing"
      class="shop-soft-panel"
      :ui="{ body: 'p-4 sm:p-5' }"
    >
      <div class="flex items-center gap-4">
        <div>
          <p class="font-semibold text-highlighted">Últimos pedidos do dia</p>
          <p class="text-sm text-muted">{{ closingHint }}. Revise a disponibilidade antes de pedir.</p>
        </div>
      </div>
    </UCard>

    <UCard
      v-if="showWhatsappWelcome"
      class="shop-soft-panel"
      :ui="{ body: 'p-4 sm:p-5' }"
    >
      <div class="flex items-center gap-4">
        <div class="min-w-0 flex-1">
          <p class="font-semibold text-highlighted">Atendimento pelo WhatsApp</p>
          <p class="text-sm text-muted">Você chegou pelo WhatsApp. O atendimento continua por lá, se precisar.</p>
        </div>
        <UButton
          v-if="home.shop.whatsapp_url"
          :to="home.shop.whatsapp_url"
          target="_blank"
          rel="noopener"
          label="WhatsApp"
          color="success"
          variant="outline"
          size="sm"
        />
      </div>
    </UCard>
  </UContainer>
</template>
