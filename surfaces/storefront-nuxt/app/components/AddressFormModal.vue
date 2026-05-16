<script setup lang="ts">
import type { StructuredAddressProjection } from '~/types/shopman'

interface AddressShape {
  id?: number
  label?: string
  label_key?: string
  label_custom?: string
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
  label_custom: '',
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

function addressLabelKey (address?: AddressShape | null): 'home' | 'work' | 'other' {
  const raw = String(address?.label_key || address?.label || '').trim().toLowerCase()
  if (raw === 'home' || raw === 'work' || raw === 'other') return raw
  if (raw === 'casa') return 'home'
  if (raw === 'trabalho') return 'work'
  if (raw === 'outro') return 'other'
  return raw ? 'other' : 'home'
}

function addressLabelCustom (address: AddressShape | null | undefined, labelKey: string): string {
  if (!address || labelKey !== 'other') return ''
  if (address.label_custom) return address.label_custom
  const displayLabel = String(address.label || '').trim()
  return displayLabel && !/^outro$/i.test(displayLabel) ? displayLabel : ''
}

watch([() => props.open, () => props.address], ([open]) => {
  if (open) {
    const labelKey = addressLabelKey(props.address)
    form.label = labelKey
    form.label_custom = addressLabelCustom(props.address, labelKey)
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
}, { immediate: true })

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
        label_custom: form.label === 'other' ? form.label_custom : '',
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
          <USelectMenu
            v-model="form.label"
            :items="labelOptions"
            value-key="value"
            label-key="label"
            :search-input="false"
            class="w-full"
          />
        </UFormField>

        <UFormField v-if="form.label === 'other'" label="Nome do endereço">
          <UInput v-model="form.label_custom" placeholder="Casa da mãe" class="w-full" />
        </UFormField>

        <UFormField label="Endereço">
          <AddressAutocomplete v-model="form.formatted_address" placeholder="Buscar endereço" @selected="onAddressSelected" />
        </UFormField>

        <UFormField label="Complemento">
          <UInput v-model="form.complement" placeholder="Apto, bloco, ponto de referência" class="w-full" />
        </UFormField>

        <UFormField label="Instruções para a entrega">
          <UTextarea v-model="form.delivery_instructions" :rows="2" placeholder="Algo que ajuda a chegar até você?" class="w-full" />
        </UFormField>

        <UCheckbox v-model="form.is_default" label="Salvar como padrão" />

        <div class="grid gap-2 pt-2 sm:flex sm:justify-end">
          <UButton
            color="neutral"
            variant="ghost"
            label="Cancelar"
            class="justify-center"
            @click="emit('update:open', false)"
          />
          <UButton
            type="submit"
            :loading="submitting"
            icon="i-lucide-save"
            label="Salvar"
            class="justify-center"
          />
        </div>
      </form>
    </template>
  </UModal>
</template>
