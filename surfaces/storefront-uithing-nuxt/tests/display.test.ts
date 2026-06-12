import { describe, expect, it } from 'vitest'
import { addressLines } from '~/utils/display'

describe('addressLines', () => {
  it('breaks a canonical BR address into readable lines', () => {
    expect(addressLines('Av. Madre Leônia Milito, 446 - Bela Suíça, Londrina - PR, 86050-270')).toEqual([
      'Av. Madre Leônia Milito, 446',
      'Bela Suíça',
      'Londrina - PR',
      'CEP 86050-270'
    ])
    expect(addressLines('Rua A, 1 - Centro, Cambé - PR')).toEqual([
      'Rua A, 1',
      'Centro',
      'Cambé - PR'
    ])
  })

  it('falls back to a single line for unexpected formats', () => {
    expect(addressLines('Praça Central, 10')).toEqual(['Praça Central, 10'])
    expect(addressLines('')).toEqual([])
    expect(addressLines(null)).toEqual([])
  })
})
