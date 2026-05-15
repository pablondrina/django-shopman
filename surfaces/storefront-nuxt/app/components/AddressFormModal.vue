<script setup lang="ts">
import type { StructuredAddressProjection } from '~/types/shopman'

interface AddressShape {
  id?: number
  label?: string
  formatted_address?: string
  complement?: string
  delivery_instructions?: string
  is_default?: boolean
  route?: string
  street_number?: string
  neighborhood?: string
  city?: string
  state_code?: string
  postal_code?: string
  latitude?: number | null
  longitude?: number | null
  place_id?: string | null
}

const props = defineProps<{ open: boolean, address?: AddressShape | null }>()
const emit = defineEmits<{
  'update:open': [boolean]
  saved: [AddressShape]
}>()

const apiPath = useShopmanApiPath()
const submitting = ref(false)
const errorMessage = ref<string | null>(null)

const form = reactive({
  label: 'home',
  formatted_address: '',
  complement: '',
  delivery_instructions: '',
  is_default: false
})
const structuredAddress = ref<StructuredAddressProjection>({})

const labelOptions = [
  { label: 'Casa', value: 'home' },
  { label: 'Trabalho', value: 'work' },
  { label: 'Outro', value: 'other' }
]

watchEffect(() => {
  if (props.open) {
    form.label = props.address?.label === 'work' || props.address?.label === 'other' ? props.address.label : 'home'
    form.formatted_address = props.address?.formatted_address || ''
    form.complement = props.address?.complement || ''
    form.delivery_instructions = props.address?.delivery_instructions || ''
    form.is_default = !!props.address?.is_default
    structuredAddress.value = props.address
      ? {
          formatted_address: props.address.formatted_address,
          route: props.address.route,
          street_number: props.address.street_number,
          neighborhood: props.address.neighborhood,
          city: props.address.city,
          state_code: props.address.state_code,
          postal_code: props.address.postal_code,
          latitude: props.address.latitude,
          longitude: props.address.longitude,
          place_id: props.address.place_id
        }
      : {}
    errorMessage.value = null
  }
})

function onAddressSelected (address: StructuredAddressProjection) {
  structuredAddress.value = address
  if (address.formatted_address) {
    form.formatted_address = address.formatted_address
  }
}

watch(() => form.formatted_address, (value) => {
  const canonical = structuredAddress.value.formatted_address?.trim()
  if (canonical && value.trim() !== canonical) {
    structuredAddress.value = {}
  }
})

function addressErrorMessage (err: any): string {
  const detail = String(err?.data?.detail || '')
  if (/constraint|not null|integrity|database/i.test(detail)) {
    return 'Não foi possível salvar o endereço. Confira os dados e tente novamente.'
  }
  return detail || 'Não foi possível salvar o endereço. Confira os dados e tente novamente.'
}

async function submit () {
  errorMessage.value = null
  if (!form.formatted_address.trim()) {
    errorMessage.value = 'Informe o endereço.'
    return
  }
  submitting.value = true
  try {
    const isEdit = !!props.address?.id
    const url = isEdit
      ? apiPath(`/api/v1/account/addresses/${props.address!.id}/`)
      : apiPath('/api/v1/account/addresses/')
    const method = isEdit ? 'PATCH' : 'POST'
    const result = await $fetch<AddressShape>(url, {
      method,
      body: {
        label: form.label,
        formatted_address: form.formatted_address,
        route: structuredAddress.value.route || '',
        street_number: structuredAddress.value.street_number || '',
        neighborhood: structuredAddress.value.neighborhood || '',
        city: structuredAddress.value.city || '',
        state_code: structuredAddress.value.state_code || '',
        postal_code: structuredAddress.value.postal_code || '',
        place_id: structuredAddress.value.place_id || '',
        coordinates: structuredAddress.value.latitude != null && structuredAddress.value.longitude != null
          ? [structuredAddress.value.latitude, structuredAddress.value.longitude]
          : undefined,
        complement: form.complement,
        delivery_instructions: form.delivery_instructions,
        is_default: form.is_default
      },
      credentials: 'include'
    })
    emit('saved', result)
    emit('update:open', false)
  } catch (err: any) {
    errorMessage.value = addressErrorMessage(err)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <UModal :open="open" :title="address?.id ? 'Editar endereço' : 'Novo endereço'" :ui="{ content: 'max-w-lg' }" @update:open="emit('update:open', $event)">
    <template #body>
      <form class="grid gap-4" @submit.prevent="submit">
        <UAlert v-if="errorMessage" color="error" variant="soft" :title="errorMessage" />

        <UFormField label="Apelido">
          <URadioGroup
            v-model="form.label"
            :items="labelOptions"
            orientation="horizontal"
            variant="card"
            :ui="{ fieldset: 'gap-2' }"
          />
        </UFormField>

        <UFormField label="Endereço">
          <AddressAutocomplete v-model="form.formatted_address" placeholder="Buscar endereço" @selected="onAddressSelected" />
        </UFormField>

        <UFormField label="Complemento">
          <UInput v-model="form.complement" placeholder="Apto, bloco, ponto de referência" />
        </UFormField>

        <UFormField label="Instruções para a entrega">
          <UTextarea v-model="form.delivery_instructions" :rows="2" placeholder="Algo que ajuda a chegar até você?" />
        </UFormField>

        <UCheckbox v-model="form.is_default" label="Salvar como padrão" />

        <div class="flex items-center justify-end gap-2 pt-2">
          <UButton color="neutral" variant="ghost" label="Cancelar" @click="emit('update:open', false)" />
          <UButton type="submit" :loading="submitting" icon="i-lucide-save" label="Salvar" />
        </div>
      </form>
    </template>
  </UModal>
</template>
