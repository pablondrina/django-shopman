<script setup lang="ts">
// Componente único de endereço (ADDRESS-UX-PLAN) — usado pelo checkout e pela
// conta. Busca unificada (Places + fallback silencioso ViaCEP), "usar minha
// localização" com banner de candidato, ajuste fino no mapa em bottom-sheet
// e etiqueta perguntada DEPOIS de salvar. Lógica pura em presentation/address.
import {
  ADDRESS_LABEL_OPTIONS,
  addressDraftErrors,
  composedAddressLine,
  draftFromGooglePlace,
  draftFromSavedAddress,
  draftFromViaCep,
  draftSummaryLine,
  emptyAddressDraft,
  labelPatchPayload,
  looksLikeCep,
  maskCepInput,
  mergeReverseGeocode,
  nextFocusAfterSuggestion,
  resolvePreselectedAddress,
  savedAddressDisplayLabel,
  selectionFromDraft,
  selectionFromSavedAddress,
  type AddressDraft,
  type AddressLabelKey,
  type AddressSelection,
  type ViaCepPayload
} from '~/presentation/address'
import type { SavedAddressProjection, StructuredAddressProjection } from '~/types/shopman'

interface PickerSuggestion {
  id: string
  kind: 'place' | 'cep'
  main: string
  secondary: string
  prediction?: any
  cepPartial?: Partial<AddressDraft>
}

const props = withDefaults(defineProps<{
  context: 'checkout' | 'account'
  savedAddresses?: SavedAddressProjection[]
  preselectedId?: number | null
  editingAddress?: SavedAddressProjection | null
  initialIsDefault?: boolean
}>(), {
  savedAddresses: () => [],
  preselectedId: null,
  editingAddress: null,
  initialIsDefault: false
})

const emit = defineEmits<{
  'update:selection': [selection: AddressSelection | null]
  // Checkout: endereço pronto (salvo + etiqueta respondida) — pode avançar.
  confirmed: []
  // Conta: criação/edição concluída — o pai fecha o sheet e atualiza a lista.
  done: []
}>()

const apiPath = useShopmanApiPath()
const csrfHeaders = useShopmanCsrfHeaders()
const maps = useGoogleMaps()

type PickerMode = 'saved' | 'search' | 'form'

const isEditing = computed(() => !!props.editingAddress)
const mode = ref<PickerMode>(initialMode())
const draft = reactive<AddressDraft>(initialDraft())
const fieldErrors = ref<Record<string, string>>({})
const acceptedLine = ref(initialAcceptedLine())
const selectedSavedId = ref<number | null>(null)

const query = ref('')
const searching = ref(false)
const suggestions = ref<PickerSuggestion[]>([])
const searchOpen = ref(false)

const locating = ref(false)
const geoIssue = ref('')
const geoCandidate = ref<AddressDraft | null>(null)

const saving = ref(false)
const saveIssue = ref('')
const pendingCreatedId = ref<number | null>(null)

const labelOpen = ref(false)
const labelCustomOpen = ref(false)
const labelCustom = ref('')
const labelSaving = ref(false)

const accountLabel = ref<AddressLabelKey>((props.editingAddress?.label_key as AddressLabelKey) || 'home')
const accountLabelCustom = ref(props.editingAddress?.label_custom || '')
const isDefault = ref(props.editingAddress ? !!props.editingAddress.is_default : props.initialIsDefault)

const mapOpen = ref(false)
const mapLoading = ref(false)
const mapIssue = ref('')
const mapEl = ref<HTMLElement | null>(null)
let mapInstance: any = null
let mapMarker: any = null

const numberInput = ref<any>(null)
const complementInput = ref<any>(null)
const searchInput = ref<any>(null)

let searchTimer: ReturnType<typeof setTimeout> | null = null
let searchSeq = 0
let placesSessionToken: any = null

const labelOptions = ADDRESS_LABEL_OPTIONS
const hasSaved = computed(() => props.context === 'checkout' && props.savedAddresses.length > 0)
const canAdjustOnMap = computed(() => maps.enabled.value && draft.latitude != null && draft.longitude != null)
const draftLine = computed(() => draftSummaryLine(draft as AddressDraft))

function initialMode (): PickerMode {
  if (props.editingAddress) return 'form'
  if (props.context === 'checkout' && props.savedAddresses.length) return 'saved'
  return 'search'
}

function initialDraft (): AddressDraft {
  return props.editingAddress ? draftFromSavedAddress(props.editingAddress) : emptyAddressDraft()
}

function initialAcceptedLine (): string {
  return props.editingAddress ? (props.editingAddress.formatted_address || '') : ''
}

// ── Salvos (checkout) ──────────────────────────────────────────────────

function pickSaved (id: number) {
  const address = props.savedAddresses.find(candidate => candidate.id === id)
  selectedSavedId.value = id
  emit('update:selection', address ? selectionFromSavedAddress(address) : null)
}

watch(() => [props.savedAddresses, props.preselectedId] as const, () => {
  if (props.context !== 'checkout' || mode.value !== 'saved') return
  if (selectedSavedId.value && props.savedAddresses.some(address => address.id === selectedSavedId.value)) return
  const preselected = resolvePreselectedAddress(props.savedAddresses, props.preselectedId)
  if (preselected) pickSaved(preselected.id)
}, { immediate: true, deep: true })

function startNewAddress () {
  selectedSavedId.value = null
  emit('update:selection', null)
  resetDraft()
  mode.value = 'search'
  void focusSearch()
}

function backToSaved () {
  mode.value = 'saved'
  const preselected = resolvePreselectedAddress(props.savedAddresses, selectedSavedId.value ?? props.preselectedId)
  if (preselected) pickSaved(preselected.id)
}

function resetDraft () {
  Object.assign(draft, emptyAddressDraft())
  fieldErrors.value = {}
  acceptedLine.value = ''
  saveIssue.value = ''
  geoCandidate.value = null
  geoIssue.value = ''
  query.value = ''
  suggestions.value = []
}

// ── Busca unificada ────────────────────────────────────────────────────

async function focusSearch () {
  await nextTick()
  searchInput.value?.$el?.querySelector?.('input')?.focus?.()
  ;(searchInput.value as any)?.focus?.()
}

function onQueryInput () {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => { void runSearch(query.value) }, 300)
}

async function runSearch (value: string) {
  const seq = ++searchSeq
  const trimmed = value.trim()
  const isCep = looksLikeCep(trimmed)
  if (trimmed.length < 3) {
    suggestions.value = []
    searchOpen.value = false
    return
  }
  searching.value = true
  let results: PickerSuggestion[] = []
  try {
    if (maps.enabled.value && !isCep) results = await placesSuggestions(trimmed)
    if (maps.enabled.value && isCep && !results.length) results = await placesSuggestions(trimmed)
    if (isCep && !results.length) {
      const cepSuggestion = await viaCepSuggestion(trimmed)
      if (cepSuggestion) results = [cepSuggestion]
    }
  } finally {
    if (seq === searchSeq) {
      suggestions.value = results
      searchOpen.value = results.length > 0
      searching.value = false
    }
  }
}

async function placesSuggestions (input: string): Promise<PickerSuggestion[]> {
  try {
    const placesLib = await maps.importLibrary('places')
    if (!placesLib?.AutocompleteSuggestion) return []
    placesSessionToken = placesSessionToken || new placesLib.AutocompleteSessionToken()
    const request: Record<string, unknown> = {
      input,
      sessionToken: placesSessionToken,
      includedRegionCodes: ['br'],
      language: 'pt-BR'
    }
    if (maps.shopLocation.value) {
      request.locationBias = { center: maps.shopLocation.value, radius: 30000 }
    }
    const { suggestions: raw } = await placesLib.AutocompleteSuggestion.fetchAutocompleteSuggestions(request)
    return (raw || [])
      .filter((entry: any) => entry?.placePrediction)
      .map((entry: any): PickerSuggestion => ({
        id: `place-${entry.placePrediction.placeId}`,
        kind: 'place',
        main: entry.placePrediction.mainText?.text || entry.placePrediction.text?.text || '',
        secondary: entry.placePrediction.secondaryText?.text || '',
        prediction: entry.placePrediction
      }))
  } catch {
    return []
  }
}

async function viaCepSuggestion (value: string): Promise<PickerSuggestion | null> {
  try {
    const cep = value.replace(/\D/g, '')
    const payload = await $fetch<ViaCepPayload>(`https://viacep.com.br/ws/${cep}/json/`)
    const partial = draftFromViaCep(payload, cep)
    if (!partial) return null
    return {
      id: `cep-${cep}`,
      kind: 'cep',
      main: partial.formatted_address || maskCepInput(cep),
      secondary: `CEP ${maskCepInput(cep)}`,
      cepPartial: partial
    }
  } catch {
    return null
  }
}

async function acceptSuggestion (suggestion: PickerSuggestion) {
  searchOpen.value = false
  if (suggestion.kind === 'cep' && suggestion.cepPartial) {
    applyPartial(suggestion.cepPartial)
    return
  }
  try {
    searching.value = true
    const place = suggestion.prediction.toPlace()
    await place.fetchFields({ fields: ['addressComponents', 'formattedAddress', 'location', 'id'] })
    placesSessionToken = null
    const location = place.location
    const latitude = typeof location?.lat === 'function' ? location.lat() : location?.lat ?? null
    const longitude = typeof location?.lng === 'function' ? location.lng() : location?.lng ?? null
    applyPartial(draftFromGooglePlace({
      id: place.id,
      formattedAddress: place.formattedAddress,
      addressComponents: place.addressComponents,
      latitude,
      longitude
    }))
  } catch {
    saveIssue.value = 'Não foi possível carregar este endereço. Tente outra busca.'
  } finally {
    searching.value = false
  }
}

function applyPartial (partial: Partial<AddressDraft>) {
  const preserved = { complement: draft.complement, delivery_instructions: draft.delivery_instructions }
  Object.assign(draft, emptyAddressDraft(), preserved, partial)
  draft.postal_code = maskCepInput(draft.postal_code)
  acceptedLine.value = draftLine.value
  fieldErrors.value = {}
  geoCandidate.value = null
  mode.value = 'form'
  void focusGuided()
}

async function focusGuided () {
  await nextTick()
  const target = nextFocusAfterSuggestion(draft) === 'street_number' ? numberInput.value : complementInput.value
  target?.$el?.querySelector?.('input')?.focus?.()
  ;(target as any)?.focus?.()
}

function startManualEntry () {
  resetDraft()
  mode.value = 'form'
}

function backToSearch () {
  mode.value = 'search'
  void focusSearch()
}

// ── "Usar minha localização" — banner de candidato, nunca silencioso ───

async function locateMe () {
  if (!import.meta.client || !navigator.geolocation) {
    geoIssue.value = 'Geolocalização não está disponível neste aparelho.'
    return
  }
  locating.value = true
  geoIssue.value = ''
  geoCandidate.value = null
  try {
    const coords = await new Promise<GeolocationCoordinates>((resolve, reject) => {
      navigator.geolocation.getCurrentPosition(position => resolve(position.coords), reject, {
        enableHighAccuracy: true,
        timeout: 10000
      })
    })
    const result = await $fetch<StructuredAddressProjection>(apiPath('/api/v1/geocode/reverse/'), {
      method: 'POST',
      headers: await csrfHeaders(),
      credentials: 'include',
      body: { lat: coords.latitude, lng: coords.longitude }
    })
    geoCandidate.value = mergeReverseGeocode(emptyAddressDraft(), result)
  } catch (e: any) {
    geoIssue.value = e?.data?.detail || 'Não foi possível resolver sua localização.'
  } finally {
    locating.value = false
  }
}

function useGeoCandidate () {
  if (!geoCandidate.value) return
  applyPartial({ ...geoCandidate.value })
}

// ── Ajustar no mapa (bottom-sheet ~85%, pin arrastável) ────────────────

async function openMapAdjust () {
  if (!canAdjustOnMap.value) return
  mapOpen.value = true
  mapLoading.value = true
  mapIssue.value = ''
  await nextTick()
  try {
    const mapsLib = await maps.importLibrary('maps')
    if (!mapsLib?.Map || !mapEl.value) {
      mapIssue.value = 'O mapa não está disponível agora.'
      return
    }
    const center = { lat: draft.latitude as number, lng: draft.longitude as number }
    mapInstance = new mapsLib.Map(mapEl.value, {
      center,
      zoom: 17,
      disableDefaultUI: true,
      zoomControl: true,
      gestureHandling: 'greedy',
      clickableIcons: false
    })
    mapMarker = new (globalThis as any).google.maps.Marker({
      map: mapInstance,
      position: center,
      draggable: true
    })
  } catch {
    mapIssue.value = 'O mapa não está disponível agora.'
  } finally {
    mapLoading.value = false
  }
}

async function confirmMapAdjust () {
  const position = mapMarker?.getPosition?.()
  if (!position) {
    mapOpen.value = false
    return
  }
  mapLoading.value = true
  try {
    const result = await $fetch<StructuredAddressProjection>(apiPath('/api/v1/geocode/reverse/'), {
      method: 'POST',
      headers: await csrfHeaders(),
      credentials: 'include',
      body: { lat: position.lat(), lng: position.lng() }
    })
    Object.assign(draft, mergeReverseGeocode({ ...(draft as AddressDraft) }, result))
    acceptedLine.value = draftLine.value
    mapOpen.value = false
  } catch (e: any) {
    mapIssue.value = e?.data?.detail || 'Não foi possível confirmar o ponto. Tente de novo.'
  } finally {
    mapLoading.value = false
  }
}

watch(mapOpen, open => {
  if (!open) {
    mapInstance = null
    mapMarker = null
    mapIssue.value = ''
  }
})

// ── Salvar + etiqueta DEPOIS ───────────────────────────────────────────

function onCepInput () {
  draft.postal_code = maskCepInput(draft.postal_code)
}

function addressApiPayload (): Record<string, unknown> {
  const payload: Record<string, unknown> = {
    formatted_address: draft.formatted_address || composedAddressLine(draft as AddressDraft),
    route: draft.route.trim(),
    street_number: draft.street_number.trim(),
    neighborhood: draft.neighborhood.trim(),
    city: draft.city.trim(),
    state_code: draft.state_code.trim().toUpperCase(),
    postal_code: maskCepInput(draft.postal_code),
    complement: draft.complement.trim(),
    delivery_instructions: draft.delivery_instructions.trim(),
    place_id: draft.place_id || null
  }
  if (draft.latitude != null && draft.longitude != null) {
    payload.coordinates = [draft.latitude, draft.longitude]
  }
  return payload
}

function validateDraft (): boolean {
  fieldErrors.value = addressDraftErrors(draft as AddressDraft)
  return !Object.keys(fieldErrors.value).length
}

async function confirmDraft () {
  if (saving.value || !validateDraft()) return
  saveIssue.value = ''
  if (props.context === 'account') {
    await saveAccountAddress()
    return
  }
  // Checkout: salva no perfil (omotenashi — a próxima compra já começa
  // pronta) e só então pergunta a etiqueta. Falhou? O pedido segue com o
  // endereço estruturado mesmo assim.
  saving.value = true
  let createdId: number | null = null
  try {
    const created = await $fetch<SavedAddressProjection>(apiPath('/api/v1/account/addresses/'), {
      method: 'POST',
      headers: await csrfHeaders(),
      credentials: 'include',
      body: {
        ...addressApiPayload(),
        label: 'other',
        label_custom: '',
        is_default: !props.savedAddresses.length
      }
    })
    createdId = created?.id ?? null
  } catch {
    createdId = null
  } finally {
    saving.value = false
  }
  pendingCreatedId.value = createdId
  if (createdId) {
    labelOpen.value = true
  } else {
    finishNewAddress()
  }
}

function finishNewAddress () {
  emit('update:selection', selectionFromDraft({ ...(draft as AddressDraft) }, pendingCreatedId.value))
  emit('confirmed')
}

async function saveAccountAddress () {
  saving.value = true
  try {
    if (isEditing.value && props.editingAddress) {
      await $fetch(apiPath(`/api/v1/account/addresses/${encodeURIComponent(props.editingAddress.id)}/`), {
        method: 'PATCH',
        headers: await csrfHeaders(),
        credentials: 'include',
        body: {
          ...addressApiPayload(),
          ...labelPatchPayload(accountLabel.value, accountLabelCustom.value),
          is_default: isDefault.value
        }
      })
      emit('done')
      return
    }
    const created = await $fetch<SavedAddressProjection>(apiPath('/api/v1/account/addresses/'), {
      method: 'POST',
      headers: await csrfHeaders(),
      credentials: 'include',
      body: {
        ...addressApiPayload(),
        label: 'other',
        label_custom: '',
        is_default: isDefault.value
      }
    })
    pendingCreatedId.value = created?.id ?? null
    labelOpen.value = true
  } catch (e: any) {
    saveIssue.value = e?.data?.detail || 'Não foi possível salvar o endereço agora.'
  } finally {
    saving.value = false
  }
}

let labelResolved = false

async function chooseLabel (key: AddressLabelKey) {
  if (key === 'other' && !labelCustomOpen.value) {
    labelCustomOpen.value = true
    return
  }
  if (pendingCreatedId.value) {
    labelSaving.value = true
    try {
      await $fetch(apiPath(`/api/v1/account/addresses/${encodeURIComponent(pendingCreatedId.value)}/`), {
        method: 'PATCH',
        headers: await csrfHeaders(),
        credentials: 'include',
        body: labelPatchPayload(key, labelCustom.value)
      })
    } catch {
      // Etiqueta é açúcar — não trava o fluxo se falhar.
    } finally {
      labelSaving.value = false
    }
  }
  closeLabelFlow()
}

function skipLabel () {
  closeLabelFlow()
}

function finishAfterLabel () {
  labelCustomOpen.value = false
  labelCustom.value = ''
  if (props.context === 'account') {
    emit('done')
  } else {
    finishNewAddress()
  }
}

function closeLabelFlow () {
  labelResolved = true
  labelOpen.value = false
  finishAfterLabel()
}

// Fechar o sheet de etiqueta por gesto (X, overlay, ESC) = "Agora não" —
// o fluxo continua; o endereço fica com a etiqueta neutra.
watch(labelOpen, open => {
  if (open) {
    labelResolved = false
    return
  }
  if (!labelResolved) finishAfterLabel()
})
</script>

<template>
  <div class="space-y-4" data-address-picker>
    <!-- ── Endereços salvos (checkout) ─────────────────────────────── -->
    <template v-if="mode === 'saved'">
      <UiRadioGroup
        :model-value="selectedSavedId"
        class="grid gap-2"
        data-address-saved-list
        @update:model-value="pickSaved(Number($event))"
      >
        <UiFieldLabel v-for="address in savedAddresses" :key="address.id" :for="`address-saved-${address.id}`">
          <UiField orientation="horizontal">
            <UiRadioGroupItem :id="`address-saved-${address.id}`" :value="address.id" />
            <UiFieldContent>
              <UiFieldTitle>
                <Icon name="lucide:map-pin-house" class="size-4" />
                {{ savedAddressDisplayLabel(address) }}
                <UiBadge v-if="address.is_default" variant="secondary">Padrão</UiBadge>
              </UiFieldTitle>
              <UiFieldDescription>
                {{ address.formatted_address }}<template v-if="address.complement"> · {{ address.complement }}</template>
              </UiFieldDescription>
            </UiFieldContent>
          </UiField>
        </UiFieldLabel>
      </UiRadioGroup>
      <UiButton variant="ghost" size="sm" icon="lucide:plus" class="-ml-2" data-address-new @click="startNewAddress">
        Novo endereço
      </UiButton>
    </template>

    <!-- ── Busca unificada ─────────────────────────────────────────── -->
    <template v-else-if="mode === 'search'">
      <div class="space-y-2">
        <UiLabel for="address-search">Buscar endereço ou CEP</UiLabel>
        <div class="flex items-start gap-2">
          <div class="relative min-w-0 flex-1">
            <UiInputGroup>
              <UiInputGroupAddon align="inline-start">
                <Icon v-if="!searching" name="lucide:search" />
                <Icon v-else name="lucide:loader-circle" class="animate-spin" />
              </UiInputGroupAddon>
              <UiInputGroupInput
                id="address-search"
                ref="searchInput"
                v-model="query"
                type="text"
                autocomplete="off"
                placeholder="Rua, número ou CEP"
                data-address-search
                @input="onQueryInput"
              />
            </UiInputGroup>
            <ul
              v-if="searchOpen"
              class="absolute inset-x-0 top-full z-30 mt-1 overflow-hidden rounded-md border bg-background shadow-md"
              data-address-suggestions
            >
              <li v-for="suggestion in suggestions" :key="suggestion.id">
                <UiButton
                  variant="ghost"
                  class="h-auto min-h-10 w-full flex-col items-start gap-0.5 whitespace-normal rounded-none px-3 py-2 text-left font-normal"
                  @click="acceptSuggestion(suggestion)"
                >
                  <span class="w-full text-sm font-semibold">{{ suggestion.main }}</span>
                  <span v-if="suggestion.secondary" class="w-full text-xs text-muted-foreground">{{ suggestion.secondary }}</span>
                </UiButton>
              </li>
            </ul>
          </div>
          <UiButton
            variant="outline"
            class="size-10 shrink-0"
            :loading="locating"
            aria-label="Usar minha localização"
            title="Usar minha localização"
            data-address-locate
            @click="locateMe"
          >
            <Icon v-if="!locating" name="lucide:locate-fixed" class="size-5" />
          </UiButton>
        </div>
        <p v-if="geoIssue" class="text-sm text-destructive">{{ geoIssue }}</p>
      </div>

      <!-- Candidato da localização: confirmação explícita, nunca preenchimento silencioso. -->
      <div
        v-if="geoCandidate"
        class="-mx-4 space-y-3 border-y px-4 py-3 sm:mx-0 sm:rounded-md sm:border sm:px-3"
        data-address-geo-candidate
      >
        <div class="flex items-start gap-2">
          <Icon name="lucide:map-pin" class="mt-0.5 size-4 shrink-0 text-muted-foreground" />
          <div class="min-w-0">
            <p class="text-sm font-semibold">Você está aqui?</p>
            <p class="mt-0.5 text-sm text-muted-foreground">{{ draftSummaryLine(geoCandidate) }}</p>
          </div>
        </div>
        <div class="flex flex-wrap gap-2">
          <UiButton size="sm" class="min-h-10" @click="useGeoCandidate">Usar este endereço</UiButton>
          <UiButton size="sm" variant="ghost" class="min-h-10" @click="geoCandidate = null">Agora não</UiButton>
        </div>
      </div>

      <div class="flex flex-wrap items-center gap-x-4 gap-y-1">
        <UiButton variant="ghost" size="sm" class="-ml-2 text-muted-foreground hover:text-foreground" data-address-manual @click="startManualEntry">
          Preencher manualmente
        </UiButton>
        <UiButton
          v-if="hasSaved"
          variant="ghost"
          size="sm"
          class="text-muted-foreground hover:text-foreground"
          @click="backToSaved"
        >
          Voltar aos salvos
        </UiButton>
      </div>
    </template>

    <!-- ── Campos estruturados ─────────────────────────────────────── -->
    <template v-else>
      <div v-if="acceptedLine" class="flex flex-wrap items-center gap-x-2 gap-y-1" data-address-accepted>
        <Icon name="lucide:map-pin" class="size-4 shrink-0 text-muted-foreground" />
        <p class="min-w-0 flex-1 text-sm font-semibold">{{ acceptedLine }}</p>
        <UiButton
          v-if="canAdjustOnMap"
          variant="ghost"
          size="sm"
          icon="lucide:map"
          class="text-muted-foreground hover:text-foreground"
          data-address-adjust-map
          @click="openMapAdjust"
        >
          Ajustar no mapa
        </UiButton>
      </div>

      <UiAlert v-if="saveIssue" variant="destructive">
        <UiAlertTitle>Revise o endereço</UiAlertTitle>
        <UiAlertDescription>{{ saveIssue }}</UiAlertDescription>
      </UiAlert>

      <div class="grid grid-cols-1 gap-4">
        <div class="space-y-2">
          <UiLabel for="address-route">Rua</UiLabel>
          <UiInput id="address-route" v-model="draft.route" autocomplete="address-line1" />
          <UiFieldError v-if="fieldErrors.route" :errors="fieldErrors.route" />
        </div>
        <div class="grid grid-cols-[7rem_minmax(0,1fr)] gap-4">
          <div class="space-y-2">
            <UiLabel for="address-number">Número</UiLabel>
            <UiInput id="address-number" ref="numberInput" v-model="draft.street_number" inputmode="numeric" />
            <UiFieldError v-if="fieldErrors.street_number" :errors="fieldErrors.street_number" />
          </div>
          <div class="space-y-2">
            <UiLabel for="address-complement">Complemento</UiLabel>
            <UiInput id="address-complement" ref="complementInput" v-model="draft.complement" placeholder="Apto, bloco, referência" />
          </div>
        </div>
        <div class="space-y-2">
          <UiLabel for="address-neighborhood">Bairro</UiLabel>
          <UiInput id="address-neighborhood" v-model="draft.neighborhood" autocomplete="address-level3" />
          <UiFieldError v-if="fieldErrors.neighborhood" :errors="fieldErrors.neighborhood" />
        </div>
        <div class="grid grid-cols-[minmax(0,1fr)_4.5rem_7rem] gap-4">
          <div class="space-y-2">
            <UiLabel for="address-city">Cidade</UiLabel>
            <UiInput id="address-city" v-model="draft.city" autocomplete="address-level2" />
            <UiFieldError v-if="fieldErrors.city" :errors="fieldErrors.city" />
          </div>
          <div class="space-y-2">
            <UiLabel for="address-state">UF</UiLabel>
            <UiInput id="address-state" v-model="draft.state_code" maxlength="2" class="uppercase" autocomplete="address-level1" />
            <UiFieldError v-if="fieldErrors.state_code" :errors="fieldErrors.state_code" />
          </div>
          <div class="space-y-2">
            <UiLabel for="address-cep">CEP</UiLabel>
            <UiInput id="address-cep" v-model="draft.postal_code" inputmode="numeric" autocomplete="postal-code" placeholder="00000-000" @input="onCepInput" />
            <UiFieldError v-if="fieldErrors.postal_code" :errors="fieldErrors.postal_code" />
          </div>
        </div>
        <div class="space-y-2">
          <UiLabel for="address-instructions">Instruções de entrega</UiLabel>
          <UiInput id="address-instructions" v-model="draft.delivery_instructions" placeholder="Portaria, interfone, melhor acesso" />
        </div>
      </div>

      <!-- Conta: etiqueta editável inline só na edição (já foi salva antes). -->
      <template v-if="context === 'account' && isEditing">
        <div class="space-y-2">
          <UiLabel>Etiqueta</UiLabel>
          <div class="flex flex-wrap gap-2">
            <UiButton
              v-for="option in labelOptions"
              :key="option.key"
              size="sm"
              class="min-h-10"
              :variant="accountLabel === option.key ? 'default' : 'outline'"
              :icon="option.icon"
              @click="accountLabel = option.key"
            >
              {{ option.key === 'other' ? 'Outro' : option.label }}
            </UiButton>
          </div>
          <UiInput
            v-if="accountLabel === 'other'"
            v-model="accountLabelCustom"
            placeholder="Ex: Casa da mãe"
            aria-label="Nome da etiqueta"
          />
        </div>
      </template>

      <UiFieldLabel v-if="context === 'account'" for="address-default" class="w-full">
        <div class="-mx-4 flex w-full items-center gap-4 border-y px-4 py-3 sm:mx-0 sm:px-0">
          <div class="min-w-0 flex-1">
            <p class="text-sm font-semibold">Usar como padrão</p>
            <p class="mt-0.5 text-xs font-normal leading-5 text-muted-foreground">Este endereço aparece primeiro na próxima compra.</p>
          </div>
          <UiSwitch id="address-default" v-model="isDefault" />
        </div>
      </UiFieldLabel>

      <div class="flex flex-wrap items-center gap-x-4 gap-y-2">
        <UiButton size="lg" :loading="saving" icon="lucide:check" data-address-confirm @click="confirmDraft">
          {{ context === 'account' ? (isEditing ? 'Salvar alterações' : 'Salvar endereço') : 'Usar este endereço' }}
        </UiButton>
        <UiButton
          v-if="!isEditing"
          variant="ghost"
          size="sm"
          class="text-muted-foreground hover:text-foreground"
          @click="backToSearch"
        >
          Buscar outro endereço
        </UiButton>
      </div>
    </template>

    <!-- ── Ajustar no mapa: bottom-sheet ~85%, pin arrastável ─────────── -->
    <UiSheet v-model:open="mapOpen">
      <UiSheetContent side="bottom" class="h-[85dvh] gap-0 p-0" data-address-map-sheet>
        <UiSheetHeader class="border-b px-4 py-3 pr-12">
          <UiSheetTitle title="Ajustar no mapa" />
          <UiSheetDescription description="Arraste o pin até o ponto exato da entrega." />
        </UiSheetHeader>
        <div class="relative min-h-0 flex-1">
          <div ref="mapEl" class="absolute inset-0" />
          <div v-if="mapLoading" class="absolute inset-0 grid place-items-center bg-background/60">
            <Icon name="lucide:loader-circle" class="size-6 animate-spin text-muted-foreground" />
          </div>
          <p v-if="mapIssue" class="absolute inset-x-4 top-3 rounded-md border bg-background px-3 py-2 text-sm text-destructive shadow-sm">
            {{ mapIssue }}
          </p>
        </div>
        <UiSheetFooter class="grid grid-cols-2 gap-2 border-t bg-background p-4">
          <UiButton variant="outline" class="w-full" @click="mapOpen = false">Cancelar</UiButton>
          <UiButton class="w-full" :loading="mapLoading" @click="confirmMapAdjust">Confirmar</UiButton>
        </UiSheetFooter>
      </UiSheetContent>
    </UiSheet>

    <!-- ── Etiqueta DEPOIS de salvar — modal discreto, fácil de dispensar ── -->
    <UiSheet v-model:open="labelOpen">
      <UiSheetContent
        side="bottom"
        variant="floating"
        class="mx-auto w-[calc(100%-2rem)] max-w-md gap-0 p-0"
        data-address-label-sheet
      >
        <UiSheetHeader class="px-5 pt-5">
          <UiSheetTitle title="Endereço salvo" />
          <UiSheetDescription description="Como você quer chamar este endereço?" />
        </UiSheetHeader>
        <div class="space-y-3 px-5 pb-5 pt-3">
          <div class="flex flex-wrap gap-2">
            <UiButton
              v-for="option in labelOptions"
              :key="option.key"
              variant="outline"
              class="min-h-10"
              :icon="option.icon"
              :loading="labelSaving && option.key !== 'other'"
              @click="chooseLabel(option.key)"
            >
              {{ option.label }}
            </UiButton>
          </div>
          <div v-if="labelCustomOpen" class="flex items-start gap-2">
            <UiInput v-model="labelCustom" class="min-w-0 flex-1" placeholder="Ex: Casa da mãe" aria-label="Nome da etiqueta" />
            <UiButton :loading="labelSaving" :disabled="!labelCustom.trim()" @click="chooseLabel('other')">Salvar</UiButton>
          </div>
          <UiButton variant="ghost" size="sm" class="-ml-2 text-muted-foreground hover:text-foreground" @click="skipLabel">
            Agora não
          </UiButton>
        </div>
      </UiSheetContent>
    </UiSheet>
  </div>
</template>
