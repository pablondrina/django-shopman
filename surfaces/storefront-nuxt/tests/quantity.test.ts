import { describe, expect, it } from 'vitest'
import { clampQuantity } from '../app/utils/quantity'

describe('quantity clamping', () => {
  it('clamps quantities against projected max', () => {
    expect(clampQuantity(18, 17)).toBe(17)
    expect(clampQuantity(-3, 17)).toBe(0)
    expect(clampQuantity(5, null)).toBe(5)
    expect(clampQuantity(2.9, null)).toBe(2)
  })

  it('respects a minimum of one inside cart lines', () => {
    expect(clampQuantity(0, null, 1)).toBe(1)
  })
})
