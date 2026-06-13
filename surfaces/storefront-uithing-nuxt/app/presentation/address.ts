// Transforms puros do fluxo de endereço (ADDRESS-UX-PLAN): rascunho canônico,
// máscara/detecção de CEP, parsing de sugestão do Places e do ViaCEP,
// validação de campos, foco guiado e seleção (salvo × novo) para o checkout.

import type { SavedAddressProjection, StructuredAddressProjection } from '~/types/shopman'

export interface AddressDraft {
  formatted_address: string
  route: string
  street_number: string
  complement: string
  neighborhood: string
  city: string
  state_code: string
  postal_code: string
  latitude: number | null
  longitude: number | null
  place_id: string
  delivery_instructions: string
}

export function emptyAddressDraft (): AddressDraft {
  return {
    formatted_address: '',
    route: '',
    street_number: '',
    complement: '',
    neighborhood: '',
    city: '',
    state_code: '',
    postal_code: '',
    latitude: null,
    longitude: null,
    place_id: '',
    delivery_instructions: ''
  }
}

// ── CEP ────────────────────────────────────────────────────────────────

export function cepDigits (value: string): string {
  return (value || '').replace(/\D/g, '').slice(0, 8)
}

export function maskCepInput (value: string): string {
  const digits = cepDigits(value)
  if (digits.length <= 5) return digits
  return `${digits.slice(0, 5)}-${digits.slice(5)}`
}

// 8 dígitos numéricos (com ou sem hífen/ponto/espaço) parecem CEP — gatilho
// do fallback silencioso ViaCEP quando o Places não responde bem.
export function looksLikeCep (query: string): boolean {
  const compact = (query || '').replace(/[\s.-]/g, '')
  return /^\d{8}$/.test(compact)
}

export interface ViaCepPayload {
  erro?: boolean | string
  logradouro?: string
  bairro?: string
  localidade?: string
  uf?: string
  cep?: string
}

export function draftFromViaCep (payload: ViaCepPayload | null | undefined, queriedCep: string): Partial<AddressDraft> | null {
  if (!payload || payload.erro) return null
  const postal = maskCepInput(payload.cep || queriedCep)
  const route = (payload.logradouro || '').trim()
  const neighborhood = (payload.bairro || '').trim()
  const city = (payload.localidade || '').trim()
  const stateCode = (payload.uf || '').trim().toUpperCase()
  if (!city || !stateCode) return null
  return {
    route,
    neighborhood,
    city,
    state_code: stateCode,
    postal_code: postal,
    formatted_address: viaCepSummary(payload)
  }
}

export function viaCepSummary (payload: ViaCepPayload): string {
  const cityState = [payload.localidade, payload.uf].filter(Boolean).join('/')
  return [payload.logradouro, payload.bairro, cityState].map(part => (part || '').trim()).filter(Boolean).join(', ')
}

// ── Google Places ──────────────────────────────────────────────────────

export interface GoogleAddressComponent {
  longText?: string | null
  shortText?: string | null
  types?: string[]
}

export interface GooglePlaceFields {
  id?: string | null
  formattedAddress?: string | null
  addressComponents?: GoogleAddressComponent[] | null
  latitude?: number | null
  longitude?: number | null
}

function componentText (components: GoogleAddressComponent[], types: string[], short = false): string {
  const wanted = new Set(types)
  for (const component of components) {
    if ((component.types || []).some(type => wanted.has(type))) {
      const text = short ? component.shortText : component.longText
      if (text) return text
    }
  }
  return ''
}

// Consultas de CEP devolvem faixa ("1-494") como street_number — não é um
// número de porta; melhor deixar vazio e o foco guiado pedir o número.
function cleanStreetNumber (value: string): string {
  return /^\d+\s*-\s*\d+$/.test(value.trim()) ? '' : value
}

export function draftFromGooglePlace (place: GooglePlaceFields): Partial<AddressDraft> {
  const components = place.addressComponents || []
  return {
    formatted_address: place.formattedAddress || '',
    route: componentText(components, ['route']),
    street_number: cleanStreetNumber(componentText(components, ['street_number'])),
    neighborhood: componentText(components, ['sublocality_level_1', 'sublocality', 'neighborhood']),
    city: componentText(components, ['administrative_area_level_2', 'locality']),
    state_code: componentText(components, ['administrative_area_level_1'], true),
    postal_code: maskCepInput(componentText(components, ['postal_code'])),
    latitude: place.latitude ?? null,
    longitude: place.longitude ?? null,
    place_id: place.id || ''
  }
}

// Reverse geocode do servidor (POST /api/v1/geocode/reverse) já devolve as
// chaves canônicas. O pin manda em tudo que é do lugar; número só se o
// reverse trouxe um (pin no meio do quarteirão não apaga o número digitado).
// Complemento e instruções são do cliente — nunca sobrescrever.
export function mergeReverseGeocode (draft: AddressDraft, result: StructuredAddressProjection): AddressDraft {
  return {
    ...draft,
    formatted_address: result.formatted_address || draft.formatted_address,
    route: result.route || draft.route,
    street_number: result.street_number || draft.street_number,
    neighborhood: result.neighborhood || draft.neighborhood,
    city: result.city || draft.city,
    state_code: result.state_code || draft.state_code,
    postal_code: maskCepInput(result.postal_code || draft.postal_code),
    latitude: result.latitude ?? draft.latitude,
    longitude: result.longitude ?? draft.longitude,
    place_id: result.place_id || draft.place_id
  }
}

// ── Fluxo guiado ───────────────────────────────────────────────────────

// Sugestão aceita: foco pula para o número; se a sugestão já trouxe o
// número, pula direto para o complemento.
export function nextFocusAfterSuggestion (draft: Pick<AddressDraft, 'street_number'>): 'street_number' | 'complement' {
  return draft.street_number.trim() ? 'complement' : 'street_number'
}

export function addressDraftErrors (draft: AddressDraft): Record<string, string> {
  const errors: Record<string, string> = {}
  if (!draft.route.trim()) errors.route = 'Informe a rua.'
  if (!draft.street_number.trim()) errors.street_number = 'Informe o número (ou "s/n").'
  if (!draft.neighborhood.trim()) errors.neighborhood = 'Informe o bairro.'
  if (!draft.city.trim()) errors.city = 'Informe a cidade.'
  if (!draft.state_code.trim()) errors.state_code = 'UF.'
  if (cepDigits(draft.postal_code).length !== 8) errors.postal_code = 'CEP com 8 dígitos.'
  return errors
}

export function composedAddressLine (draft: AddressDraft): string {
  const street = [draft.route.trim(), draft.street_number.trim()].filter(Boolean).join(', ')
  const cityState = [draft.city.trim(), draft.state_code.trim()].filter(Boolean).join('/')
  return [street, draft.neighborhood.trim(), cityState].filter(Boolean).join(' - ')
}

// Linha exibida para a sugestão aceita / candidato de localização.
export function draftSummaryLine (draft: AddressDraft): string {
  return composedAddressLine(draft) || draft.formatted_address
}

export function structuredFromDraft (draft: AddressDraft): StructuredAddressProjection {
  // A linha formatada é recomposta dos campos atuais — o formatted do Google
  // fica obsoleto assim que o cliente edita número/complemento.
  const structured: StructuredAddressProjection = {
    formatted_address: composedAddressLine(draft) || draft.formatted_address,
    route: draft.route.trim(),
    street_number: draft.street_number.trim(),
    neighborhood: draft.neighborhood.trim(),
    city: draft.city.trim(),
    state_code: draft.state_code.trim(),
    postal_code: maskCepInput(draft.postal_code)
  }
  if (draft.latitude != null && draft.longitude != null) {
    structured.latitude = draft.latitude
    structured.longitude = draft.longitude
  }
  if (draft.place_id) structured.place_id = draft.place_id
  return structured
}

export function draftFromSavedAddress (address: SavedAddressProjection): AddressDraft {
  return {
    formatted_address: address.formatted_address || '',
    route: address.route || '',
    street_number: address.street_number || '',
    complement: address.complement || '',
    neighborhood: address.neighborhood || '',
    city: address.city || '',
    state_code: address.state_code || '',
    postal_code: maskCepInput(address.postal_code || ''),
    latitude: address.latitude ?? null,
    longitude: address.longitude ?? null,
    place_id: address.place_id || '',
    delivery_instructions: address.delivery_instructions || ''
  }
}

// ── Seleção (checkout) ─────────────────────────────────────────────────

export interface AddressSelection {
  savedAddressId: number | null
  formattedAddress: string
  structured: StructuredAddressProjection
  complement: string
  deliveryInstructions: string
}

export function selectionFromSavedAddress (address: SavedAddressProjection): AddressSelection {
  const draft = draftFromSavedAddress(address)
  return {
    savedAddressId: address.id,
    formattedAddress: address.formatted_address || draftSummaryLine(draft),
    structured: structuredFromDraft(draft),
    complement: address.complement || '',
    deliveryInstructions: address.delivery_instructions || ''
  }
}

export function selectionFromDraft (draft: AddressDraft, savedAddressId: number | null = null): AddressSelection {
  return {
    savedAddressId,
    formattedAddress: composedAddressLine(draft) || draft.formatted_address,
    structured: structuredFromDraft(draft),
    complement: draft.complement.trim(),
    deliveryInstructions: draft.delivery_instructions.trim()
  }
}

// Cascata de pré-seleção resolvida pelo servidor (padrão → geo → último →
// mais usado). O cliente só respeita o id; cai para o primeiro salvo se o
// id não estiver mais na lista.
export function resolvePreselectedAddress (
  savedAddresses: SavedAddressProjection[],
  preselectedId: number | null | undefined
): SavedAddressProjection | null {
  if (!savedAddresses.length) return null
  return savedAddresses.find(address => address.id === preselectedId) || savedAddresses[0] || null
}

// ── Etiqueta DEPOIS de salvar ──────────────────────────────────────────

export type AddressLabelKey = 'home' | 'work' | 'other'

export const ADDRESS_LABEL_OPTIONS: Array<{ key: AddressLabelKey, label: string, icon: string }> = [
  { key: 'home', label: 'Casa', icon: 'lucide:house' },
  { key: 'work', label: 'Trabalho', icon: 'lucide:briefcase-business' },
  { key: 'other', label: 'Outro…', icon: 'lucide:tag' }
]

export function labelPatchPayload (key: AddressLabelKey, custom = ''): { label: AddressLabelKey, label_custom: string } {
  return { label: key, label_custom: key === 'other' ? custom.trim() : '' }
}

export function savedAddressDisplayLabel (address: Pick<SavedAddressProjection, 'label' | 'label_key' | 'label_custom'>): string {
  if (address.label_key === 'other' && address.label_custom) return address.label_custom
  return address.label || 'Endereço'
}
