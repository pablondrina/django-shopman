import type { CatalogItemProjection, ProductDetailProjection, ProductNutritionProjection } from '~/types/shopman'

// Transforms puros da PDP: descrição sem eco, tabela nutricional com %VD e
// a lista "Veja também" (cross_sell por keywords compartilhadas).

export type NutritionTableRow = {
  label: string
  value: string
  pdv: number | null
}

export type NutritionTable = {
  serving: string
  rows: NutritionTableRow[]
}

export function detailDescription (product: Pick<ProductDetailProjection, 'short_description' | 'long_description'>): string {
  if (!product.long_description) return ''
  return product.long_description === product.short_description ? '' : product.long_description
}

export function nutritionTable (nutrition: ProductNutritionProjection | null): NutritionTable | null {
  if (!nutrition || !nutrition.rows.length) {
    if (!nutrition?.energy_kcal_display) return null
  }
  const rows: NutritionTableRow[] = []
  if (nutrition?.energy_kcal_display) {
    rows.push({ label: 'Valor energético', value: nutrition.energy_kcal_display, pdv: nutrition.energy_pdv })
  }
  for (const row of nutrition?.rows || []) {
    rows.push({ label: row.label, value: row.value_display, pdv: row.percent_daily_value })
  }
  if (!rows.length) return null
  return { serving: nutrition?.serving_size_display || '', rows }
}

export function crossSellItems (product: Pick<ProductDetailProjection, 'cross_sell' | 'sku'>, limit = 4): CatalogItemProjection[] {
  return (product.cross_sell || [])
    .filter(item => item.sku !== product.sku)
    .slice(0, limit)
}
