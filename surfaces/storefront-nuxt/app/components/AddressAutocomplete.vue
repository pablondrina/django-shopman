<script setup lang="ts">
import type { StructuredAddressProjection } from '~/types/shopman'

const model = defineModel<string>({ required: true })
const props = defineProps<{
  placeholder?: string
  defaultCity?: string
}>()
const emit = defineEmits<{
  selected: [StructuredAddressProjection]
}>()

const inputRef = ref<HTMLInputElement | null>(null)
const { isAvailable, ensureLoaded } = useGoogleMaps()
const isLoading = ref(false)
const error = ref<string | null>(null)
const initialized = ref(false)

let autocomplete: any = null

function componentValue (components: any[] | undefined, type: string, useShort = false): string {
  const match = components?.find(c => Array.isArray(c.types) && c.types.includes(type))
  if (!match) return ''
  return String(useShort ? match.short_name || '' : match.long_name || '').trim()
}

function structuredFromPlace (place: any): StructuredAddressProjection {
  const location = place?.geometry?.location
  const lat = typeof location?.lat === 'function' ? location.lat() : null
  const lng = typeof location?.lng === 'function' ? location.lng() : null
  const components = place?.address_components || []
  return {
    formatted_address: place?.formatted_address || '',
    route: componentValue(components, 'route'),
    street_number: componentValue(components, 'street_number'),
    neighborhood: componentValue(components, 'sublocality') || componentValue(components, 'sublocality_level_1') || componentValue(components, 'neighborhood'),
    city: componentValue(components, 'administrative_area_level_2') || componentValue(components, 'locality'),
    state_code: componentValue(components, 'administrative_area_level_1', true),
    postal_code: componentValue(components, 'postal_code'),
    country: componentValue(components, 'country'),
    country_code: componentValue(components, 'country', true),
    latitude: lat,
    longitude: lng,
    place_id: place?.place_id || null
  }
}

function getInputElement (): HTMLInputElement | null {
  const ref = inputRef.value as any
  if (!ref) return null
  if (ref instanceof HTMLInputElement) return ref
  if (ref.$el) {
    return (ref.$el as HTMLElement).querySelector?.('input') || null
  }
  if (ref.inputRef) return ref.inputRef
  return null
}

async function setup () {
  if (initialized.value || !isAvailable.value) return
  isLoading.value = true
  try {
    const places = await ensureLoaded()
    await nextTick()
    const input = getInputElement()
    if (!input || !places?.Autocomplete) return
    autocomplete = new places.Autocomplete(input, {
      componentRestrictions: { country: 'br' },
      fields: ['formatted_address', 'address_components', 'geometry', 'place_id'],
      types: ['address']
    })
    autocomplete.addListener('place_changed', () => {
      const place = autocomplete.getPlace()
      if (place?.formatted_address) {
        model.value = place.formatted_address
        emit('selected', structuredFromPlace(place))
      }
    })
    initialized.value = true
  } catch (e: any) {
    error.value = e?.message === 'SSR'
      ? null
      : 'Busca automática indisponível. Digite o endereço completo.'
  } finally {
    isLoading.value = false
  }
}

watch(isAvailable, (available) => {
  if (available) void setup()
}, { immediate: true })

onMounted(() => { void setup() })
onBeforeUnmount(() => {
  if (autocomplete && window.google?.maps?.event) {
    window.google.maps.event.clearInstanceListeners(autocomplete)
  }
})
</script>

<template>
  <div class="grid gap-1.5">
    <UInput
      ref="inputRef"
      v-model="model"
      :placeholder="placeholder || `Buscar endereço${defaultCity ? ` em ${defaultCity}` : ''}`"
      icon="i-lucide-map-pin"
      :loading="isLoading"
      autocomplete="street-address"
      class="w-full"
    />
    <p v-if="!isAvailable && !isLoading" class="text-sm text-muted">
      Busca automática indisponível. Digite o endereço completo.
    </p>
    <p v-if="error" class="text-sm text-error">{{ error }}</p>
  </div>
</template>
