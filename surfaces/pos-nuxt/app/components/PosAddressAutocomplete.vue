<script setup lang="ts">
import type { POSAddressAutocompleteProjection, StructuredAddressProjection } from "~/types/pos";
import type { GoogleAddressComponent, GoogleAutocomplete, GooglePlaceResult } from "~/types/googleMaps";

// O template ref pode ser o elemento nativo OU a instância do UiInput (que expõe
// `inputRef`/`$el`); getInputElement() normaliza para o <input> real.
type AddressInputRef = HTMLInputElement | { inputRef?: HTMLInputElement; $el?: HTMLElement };

const props = defineProps<{
  modelValue: string;
  capability: POSAddressAutocompleteProjection | null;
}>();

const emit = defineEmits<{
  "update:modelValue": [string];
  selected: [StructuredAddressProjection];
}>();

const inputRef = ref<AddressInputRef | null>(null);
const capabilityRef = computed(() => props.capability);
const { isAvailable, ensureLoaded } = usePosGoogleMaps(capabilityRef);
const isLoading = ref(false);
const error = ref("");
const initialized = ref(false);

let autocomplete: GoogleAutocomplete | null = null;

function componentValue(components: GoogleAddressComponent[] | undefined, type: string, useShort = false): string {
  const match = components?.find((component) => Array.isArray(component.types) && component.types.includes(type));
  if (!match) return "";
  return String(useShort ? match.short_name || "" : match.long_name || "").trim();
}

function structuredFromPlace(place: GooglePlaceResult): StructuredAddressProjection {
  const location = place?.geometry?.location;
  const lat = typeof location?.lat === "function" ? location.lat() : null;
  const lng = typeof location?.lng === "function" ? location.lng() : null;
  const components = place?.address_components || [];
  return {
    formatted_address: place?.formatted_address || "",
    route: componentValue(components, "route"),
    street_number: componentValue(components, "street_number"),
    neighborhood:
      componentValue(components, "sublocality_level_1")
      || componentValue(components, "sublocality")
      || componentValue(components, "neighborhood"),
    city: componentValue(components, "administrative_area_level_2") || componentValue(components, "locality"),
    state_code: componentValue(components, "administrative_area_level_1", true),
    postal_code: componentValue(components, "postal_code"),
    country: componentValue(components, "country"),
    country_code: componentValue(components, "country", true),
    latitude: lat,
    longitude: lng,
    place_id: place?.place_id || null,
    is_verified: Boolean(place?.place_id),
  };
}

function getInputElement(): HTMLInputElement | null {
  const refValue = inputRef.value;
  if (!refValue) return null;
  if (refValue instanceof HTMLInputElement) return refValue;
  if (refValue.inputRef) return refValue.inputRef;
  if (refValue.$el) return (refValue.$el as HTMLElement).querySelector?.("input") || null;
  return null;
}

async function setupAutocomplete() {
  if (initialized.value || !isAvailable.value) return;
  isLoading.value = true;
  error.value = "";
  try {
    const places = await ensureLoaded();
    await nextTick();
    const input = getInputElement();
    if (!input || !places?.Autocomplete) return;
    const config = props.capability;
    const options: Record<string, unknown> = {
      componentRestrictions: { country: config?.countries?.length ? config.countries : ["br"] },
      fields: config?.fields?.length ? config.fields : ["formatted_address", "address_components", "geometry", "place_id"],
      types: config?.types?.length ? config.types : ["address"],
    };
    if (config?.shop_latitude && config.shop_longitude && window.google?.maps?.LatLng && window.google?.maps?.Circle) {
      const origin = new window.google.maps.LatLng(config.shop_latitude, config.shop_longitude);
      options.origin = origin;
      options.bounds = new window.google.maps.Circle({
        center: origin,
        radius: config.bias_radius_m || 15000,
      }).getBounds();
    }
    const instance = new places.Autocomplete(input, options);
    autocomplete = instance;
    instance.addListener("place_changed", () => {
      const place = instance.getPlace();
      if (!place?.formatted_address) return;
      emit("update:modelValue", place.formatted_address);
      emit("selected", structuredFromPlace(place));
    });
    initialized.value = true;
  } catch (err) {
    const message = err instanceof Error ? err.message : "";
    error.value = message === "SSR" ? "" : "Busca automática indisponível.";
  } finally {
    isLoading.value = false;
  }
}

watch(isAvailable, (available) => {
  if (available) void setupAutocomplete();
}, { immediate: true });

onMounted(() => { void setupAutocomplete(); });
onBeforeUnmount(() => {
  if (autocomplete && window.google?.maps?.event) {
    window.google.maps.event.clearInstanceListeners(autocomplete);
  }
});
</script>

<template>
  <div class="grid gap-1">
    <div class="relative">
      <Icon name="lucide:map-pin" class="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
      <UiInput
        ref="inputRef"
        :model-value="modelValue"
        class="pl-9"
        autocomplete="street-address"
        placeholder="Buscar endereço"
        @update:model-value="$emit('update:modelValue', String($event || ''))"
      />
      <Icon v-if="isLoading" name="lucide:loader-circle" class="absolute right-3 top-1/2 size-4 -translate-y-1/2 animate-spin text-muted-foreground" />
    </div>
    <p v-if="!isAvailable" class="text-xs text-muted-foreground">Digite o endereço manualmente.</p>
    <p v-else-if="error" class="text-xs text-amber-700">{{ error }}</p>
  </div>
</template>
