import { describe, expect, it } from 'vitest'
import { crossSellItems, detailDescription, nutritionTable } from '~/presentation/product'
import type { CatalogItemProjection, ProductNutritionProjection } from '~/types/shopman'

function nutrition (overrides: Partial<ProductNutritionProjection> = {}): ProductNutritionProjection {
  return {
    serving_size_display: '50 g (1 unidade)',
    servings_per_container: 1,
    energy_kcal_display: '180 kcal',
    energy_pdv: 9,
    rows: [
      { field: 'carbs', label: 'Carboidratos', value_display: '23 g', unit: 'g', percent_daily_value: 8 },
      { field: 'protein', label: 'Proteínas', value_display: '4 g', unit: 'g', percent_daily_value: null }
    ],
    ...overrides
  }
}

describe('product presentation', () => {
  it('suppresses the long description when it merely echoes the short one', () => {
    expect(detailDescription({ short_description: 'Crocante.', long_description: 'Crocante.' })).toBe('')
    expect(detailDescription({ short_description: 'Crocante.', long_description: 'Feito com levain.' })).toBe('Feito com levain.')
    expect(detailDescription({ short_description: 'Crocante.', long_description: '' })).toBe('')
  })

  it('builds the nutrition table with energy first and %VD when present', () => {
    const table = nutritionTable(nutrition())
    expect(table?.serving).toBe('50 g (1 unidade)')
    expect(table?.rows[0]).toEqual({ label: 'Valor energético', value: '180 kcal', pdv: 9 })
    expect(table?.rows[1]).toEqual({ label: 'Carboidratos', value: '23 g', pdv: 8 })
    expect(table?.rows[2]!.pdv).toBeNull()
  })

  it('returns null when there is nothing nutritional to show', () => {
    expect(nutritionTable(null)).toBeNull()
    expect(nutritionTable(nutrition({ energy_kcal_display: null, energy_pdv: null, rows: [] }))).toBeNull()
  })

  it('limits cross sell and never suggests the product itself', () => {
    const item = (sku: string) => ({ sku } as CatalogItemProjection)
    const product = { sku: 'A', cross_sell: [item('A'), item('B'), item('C'), item('D'), item('E'), item('F')] }
    const result = crossSellItems(product)
    expect(result.map(i => i.sku)).toEqual(['B', 'C', 'D', 'E'])
  })
})
