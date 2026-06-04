import { describe, expect, it } from 'vitest'
import { clampQuantity, quantityFromModelValue } from '../app/utils/quantity'

describe('quantity control serialization', () => {
  it('does not turn transient empty NumberField values into remove mutations', () => {
    expect(quantityFromModelValue(undefined)).toBeNull()
    expect(quantityFromModelValue(null)).toBeNull()
    expect(quantityFromModelValue('')).toBeNull()
    expect(quantityFromModelValue(Number.NaN)).toBeNull()
  })

  it('preserves explicit zero and normalizes positive integer quantities', () => {
    expect(quantityFromModelValue(0)).toBe(0)
    expect(quantityFromModelValue('0')).toBe(0)
    expect(quantityFromModelValue('2')).toBe(2)
    expect(quantityFromModelValue(2.9)).toBe(2)
  })

  it('clamps only valid quantities against projected max', () => {
    expect(clampQuantity(18, 17)).toBe(17)
    expect(clampQuantity(-3, 17)).toBe(0)
    expect(clampQuantity(5, null)).toBe(5)
  })

  it('supports explicit removal outside cart review and a minimum of one inside cart lines', () => {
    expect(quantityFromModelValue(0)).toBe(0)
    expect(quantityFromModelValue(0, 1)).toBe(1)
    expect(clampQuantity(0, null, 1)).toBe(1)
  })
})
