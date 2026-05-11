<script setup lang="ts">
const model = defineModel<string>({ required: true })
const props = defineProps<{
  placeholder?: string
  defaultCity?: string
}>()

const inputRef = ref<HTMLInputElement | null>(null)
const { isAvailable, ensureLoaded } = useGoogleMaps()
const isLoading = ref(false)
const error = ref<string | null>(null)
const initialized = ref(false)

let autocomplete: any = null

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
    await ensureLoaded()
    await nextTick()
    const input = getInputElement()
    if (!input || !window.google?.maps?.places) return
    autocomplete = new window.google.maps.places.Autocomplete(input, {
      componentRestrictions: { country: 'br' },
      fields: ['formatted_address', 'address_components', 'geometry'],
      types: ['address']
    })
    autocomplete.addListener('place_changed', () => {
      const place = autocomplete.getPlace()
      if (place?.formatted_address) {
        model.value = place.formatted_address
      }
    })
    initialized.value = true
  } catch (e: any) {
    error.value = e?.message || 'Não foi possível carregar a busca de endereços.'
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
