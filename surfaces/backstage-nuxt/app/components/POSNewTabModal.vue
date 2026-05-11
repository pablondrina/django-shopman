<script setup lang="ts">
const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{
  'update:open': [boolean]
  created: [string]
}>()

const cart = usePosCart()
const tabCode = ref('')
const label = ref('')
const submitting = ref(false)

watchEffect(() => {
  if (props.open) {
    tabCode.value = ''
    label.value = ''
    submitting.value = false
  }
})

async function submit () {
  const code = tabCode.value.trim()
  if (!code) return
  submitting.value = true
  const ok = await cart.createTab(code, label.value.trim())
  submitting.value = false
  if (ok) {
    emit('created', code)
    emit('update:open', false)
  }
}
</script>

<template>
  <UModal :open="open" title="Nova comanda" @update:open="emit('update:open', $event)">
    <template #body>
      <form class="grid gap-4" @submit.prevent="submit">
        <UFormField label="Código da comanda" required hint="Ex: 1013, T-001, MESA-A">
          <UInput v-model="tabCode" placeholder="Código" autofocus class="font-mono" />
        </UFormField>
        <UFormField label="Apelido (opcional)">
          <UInput v-model="label" placeholder="Ex: Mesa do balcão" />
        </UFormField>
      </form>
    </template>

    <template #footer>
      <div class="flex justify-end gap-2">
        <UButton color="neutral" variant="ghost" label="Cancelar" @click="emit('update:open', false)" />
        <UButton color="primary" icon="i-lucide-plus" label="Cadastrar" :loading="submitting" :disabled="!tabCode.trim()" @click="submit" />
      </div>
    </template>
  </UModal>
</template>
