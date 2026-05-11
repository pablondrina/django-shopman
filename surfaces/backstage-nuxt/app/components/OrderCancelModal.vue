<script setup lang="ts">
import type { OrderCardProjection } from '~/types/backstage'

const props = defineProps<{ open: boolean, order: OrderCardProjection | null }>()
const emit = defineEmits<{
  'update:open': [boolean]
  confirm: [{ order: OrderCardProjection, reason: string }]
}>()

const reason = ref('')
const submitting = ref(false)

watchEffect(() => {
  if (props.open) {
    reason.value = ''
    submitting.value = false
  }
})

async function confirm () {
  if (!props.order || !reason.value.trim()) return
  submitting.value = true
  emit('confirm', { order: props.order, reason: reason.value.trim() })
}
</script>

<template>
  <UModal :open="open" :title="`Cancelar pedido #${order?.ref || ''}`" @update:open="emit('update:open', $event)">
    <template #body>
      <div class="grid gap-4">
        <UAlert
          color="warning"
          variant="subtle"
          icon="i-lucide-triangle-alert"
          title="Esta ação é irreversível"
          description="O pedido será cancelado e o cliente notificado se aplicável."
        />

        <UFormField label="Motivo do cancelamento" required>
          <UTextarea
            v-model="reason"
            :rows="3"
            placeholder="Ex: Sem estoque do produto principal, cliente pediu cancelamento, endereço inválido..."
            autofocus
          />
        </UFormField>
      </div>
    </template>

    <template #footer>
      <div class="flex justify-end gap-2">
        <UButton color="neutral" variant="ghost" label="Voltar" @click="emit('update:open', false)" />
        <UButton
          color="error"
          icon="i-lucide-circle-x"
          label="Cancelar pedido"
          :loading="submitting"
          :disabled="!reason.trim()"
          @click="confirm"
        />
      </div>
    </template>
  </UModal>
</template>
