import { describe, expect, it } from 'vitest'
import {
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
  structuredFromDraft,
  type AddressDraft
} from '../app/presentation/address'
import type { SavedAddressProjection } from '../app/types/shopman'

function savedAddress (overrides: Partial<SavedAddressProjection> = {}): SavedAddressProjection {
  return {
    id: 7,
    label: 'Casa',
    label_key: 'home',
    label_custom: '',
    formatted_address: 'R. das Flores, 123 - Jardim, Londrina - PR',
    complement: 'Apto 4B',
    delivery_instructions: 'Tocar interfone',
    is_default: true,
    route: 'R. das Flores',
    street_number: '123',
    neighborhood: 'Jardim',
    city: 'Londrina',
    state_code: 'PR',
    postal_code: '86010-000',
    latitude: -23.31,
    longitude: -51.16,
    place_id: 'place-abc',
    ...overrides
  }
}

function filledDraft (overrides: Partial<AddressDraft> = {}): AddressDraft {
  return {
    ...emptyAddressDraft(),
    route: 'R. das Flores',
    street_number: '123',
    neighborhood: 'Jardim',
    city: 'Londrina',
    state_code: 'PR',
    postal_code: '86010-000',
    ...overrides
  }
}

describe('CEP', () => {
  it('masks progressively as the customer types', () => {
    expect(maskCepInput('8')).toBe('8')
    expect(maskCepInput('86010')).toBe('86010')
    expect(maskCepInput('860100')).toBe('86010-0')
    expect(maskCepInput('86010000')).toBe('86010-000')
    expect(maskCepInput('86010-000extra')).toBe('86010-000')
  })

  it('detects an 8-digit query as CEP regardless of punctuation', () => {
    expect(looksLikeCep('86010000')).toBe(true)
    expect(looksLikeCep('86010-000')).toBe(true)
    expect(looksLikeCep('86.010 000')).toBe(true)
    expect(looksLikeCep('8601000')).toBe(false)
    expect(looksLikeCep('rua das flores 123')).toBe(false)
  })

  it('parses a ViaCEP payload into draft fields', () => {
    const partial = draftFromViaCep({
      logradouro: 'Rua das Flores',
      bairro: 'Jardim',
      localidade: 'Londrina',
      uf: 'pr',
      cep: '86010-000'
    }, '86010000')
    expect(partial).toMatchObject({
      route: 'Rua das Flores',
      neighborhood: 'Jardim',
      city: 'Londrina',
      state_code: 'PR',
      postal_code: '86010-000'
    })
  })

  it('rejects ViaCEP errors and incomplete payloads', () => {
    expect(draftFromViaCep({ erro: true }, '99999999')).toBeNull()
    expect(draftFromViaCep({ logradouro: 'Rua X' }, '86010000')).toBeNull()
    expect(draftFromViaCep(null, '86010000')).toBeNull()
  })
})

describe('draftFromGooglePlace', () => {
  it('maps address components into the canonical draft', () => {
    const partial = draftFromGooglePlace({
      id: 'place-xyz',
      formattedAddress: 'R. das Flores, 123 - Jardim, Londrina - PR, 86010-000',
      latitude: -23.31,
      longitude: -51.16,
      addressComponents: [
        { longText: '123', shortText: '123', types: ['street_number'] },
        { longText: 'Rua das Flores', shortText: 'R. das Flores', types: ['route'] },
        { longText: 'Jardim', shortText: 'Jardim', types: ['sublocality_level_1', 'sublocality'] },
        { longText: 'Londrina', shortText: 'Londrina', types: ['administrative_area_level_2'] },
        { longText: 'Paraná', shortText: 'PR', types: ['administrative_area_level_1'] },
        { longText: '86010-000', shortText: '86010-000', types: ['postal_code'] }
      ]
    })
    expect(partial).toMatchObject({
      route: 'Rua das Flores',
      street_number: '123',
      neighborhood: 'Jardim',
      city: 'Londrina',
      state_code: 'PR',
      postal_code: '86010-000',
      latitude: -23.31,
      longitude: -51.16,
      place_id: 'place-xyz'
    })
  })

  it('drops range artifacts ("1-494") that CEP lookups return as street number', () => {
    const partial = draftFromGooglePlace({
      addressComponents: [
        { longText: '1-494', shortText: '1-494', types: ['street_number'] },
        { longText: 'Rua Guaporé', shortText: 'R. Guaporé', types: ['route'] }
      ]
    })
    expect(partial.street_number).toBe('')
    expect(partial.route).toBe('Rua Guaporé')
  })

  it('degrades to empty fields when components are missing', () => {
    const partial = draftFromGooglePlace({ formattedAddress: 'Algum lugar' })
    expect(partial.route).toBe('')
    expect(partial.street_number).toBe('')
    expect(partial.latitude).toBeNull()
  })
})

describe('mergeReverseGeocode', () => {
  it('lets the pin govern the place but never erases the typed number or complement', () => {
    const draft = filledDraft({ complement: 'Fundos', delivery_instructions: 'Portaria' })
    const merged = mergeReverseGeocode(draft, {
      formatted_address: 'R. Nova, s/n - Centro, Londrina - PR',
      route: 'R. Nova',
      street_number: '',
      neighborhood: 'Centro',
      city: 'Londrina',
      state_code: 'PR',
      postal_code: '86020111',
      latitude: -23.5,
      longitude: -51.2,
      place_id: 'place-new'
    })
    expect(merged.route).toBe('R. Nova')
    expect(merged.street_number).toBe('123')
    expect(merged.neighborhood).toBe('Centro')
    expect(merged.postal_code).toBe('86020-111')
    expect(merged.latitude).toBe(-23.5)
    expect(merged.complement).toBe('Fundos')
    expect(merged.delivery_instructions).toBe('Portaria')
    expect(merged.place_id).toBe('place-new')
  })

  it('uses the reverse number when the pin found one', () => {
    const merged = mergeReverseGeocode(filledDraft(), {
      route: 'R. Nova',
      street_number: '456',
      city: 'Londrina',
      state_code: 'PR'
    })
    expect(merged.street_number).toBe('456')
  })
})

describe('guided flow', () => {
  it('jumps focus to the number unless the suggestion already has one', () => {
    expect(nextFocusAfterSuggestion({ street_number: '' })).toBe('street_number')
    expect(nextFocusAfterSuggestion({ street_number: '123' })).toBe('complement')
  })

  it('validates the canonical required fields', () => {
    expect(addressDraftErrors(filledDraft())).toEqual({})
    const errors = addressDraftErrors(emptyAddressDraft())
    expect(Object.keys(errors).sort()).toEqual([
      'city', 'neighborhood', 'postal_code', 'route', 'state_code', 'street_number'
    ])
  })

  it('accepts "s/n" as a street number', () => {
    expect(addressDraftErrors(filledDraft({ street_number: 's/n' }))).toEqual({})
  })

  it('composes a display line from the structured fields', () => {
    expect(composedAddressLine(filledDraft())).toBe('R. das Flores, 123 - Jardim - Londrina/PR')
    expect(draftSummaryLine(emptyAddressDraft())).toBe('')
    expect(draftSummaryLine({ ...emptyAddressDraft(), formatted_address: 'Só o formatado' })).toBe('Só o formatado')
  })
})

describe('structured payload', () => {
  it('only carries coordinates when both are present', () => {
    const structured = structuredFromDraft(filledDraft())
    expect(structured.latitude).toBeUndefined()
    expect(structured.place_id).toBeUndefined()

    const located = structuredFromDraft(filledDraft({ latitude: -23.31, longitude: -51.16, place_id: 'p1' }))
    expect(located.latitude).toBe(-23.31)
    expect(located.longitude).toBe(-51.16)
    expect(located.place_id).toBe('p1')
  })

  it('recomposes the formatted line from the current fields — the Google one goes stale after edits', () => {
    const structured = structuredFromDraft(filledDraft({ formatted_address: 'R. Guaporé, 1-494 - Centro, Londrina' }))
    expect(structured.formatted_address).toBe('R. das Flores, 123 - Jardim - Londrina/PR')
  })

  it('falls back to the composed line when there is no formatted address', () => {
    const structured = structuredFromDraft(filledDraft())
    expect(structured.formatted_address).toBe('R. das Flores, 123 - Jardim - Londrina/PR')
  })
})

describe('selection', () => {
  it('builds a complete selection from a saved address', () => {
    const selection = selectionFromSavedAddress(savedAddress())
    expect(selection.savedAddressId).toBe(7)
    expect(selection.formattedAddress).toContain('R. das Flores')
    expect(selection.complement).toBe('Apto 4B')
    expect(selection.deliveryInstructions).toBe('Tocar interfone')
    expect(selection.structured.latitude).toBe(-23.31)
  })

  it('builds a selection from a new draft', () => {
    const selection = selectionFromDraft(filledDraft({ complement: ' Fundos ' }))
    expect(selection.savedAddressId).toBeNull()
    expect(selection.complement).toBe('Fundos')
    expect(selection.structured.route).toBe('R. das Flores')
  })

  it('keeps the created id when the new address was saved to the profile', () => {
    expect(selectionFromDraft(filledDraft(), 42).savedAddressId).toBe(42)
  })

  it('roundtrips a saved address into a draft', () => {
    const draft = draftFromSavedAddress(savedAddress({ postal_code: '86010000' }))
    expect(draft.postal_code).toBe('86010-000')
    expect(draft.latitude).toBe(-23.31)
  })
})

describe('resolvePreselectedAddress', () => {
  const addresses = [savedAddress({ id: 1 }), savedAddress({ id: 2, is_default: false })]

  it('respects the server cascade id', () => {
    expect(resolvePreselectedAddress(addresses, 2)?.id).toBe(2)
  })

  it('falls back to the first saved address when the id is stale', () => {
    expect(resolvePreselectedAddress(addresses, 99)?.id).toBe(1)
    expect(resolvePreselectedAddress(addresses, null)?.id).toBe(1)
  })

  it('returns null without saved addresses', () => {
    expect(resolvePreselectedAddress([], 1)).toBeNull()
  })
})

describe('label depois', () => {
  it('clears the custom label unless "other" is chosen', () => {
    expect(labelPatchPayload('home', 'ignorado')).toEqual({ label: 'home', label_custom: '' })
    expect(labelPatchPayload('other', ' Casa da mãe ')).toEqual({ label: 'other', label_custom: 'Casa da mãe' })
  })

  it('prefers the custom label for display', () => {
    expect(savedAddressDisplayLabel({ label: 'Outro', label_key: 'other', label_custom: 'Casa da mãe' })).toBe('Casa da mãe')
    expect(savedAddressDisplayLabel({ label: 'Casa', label_key: 'home', label_custom: '' })).toBe('Casa')
  })
})
