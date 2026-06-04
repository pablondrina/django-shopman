export function quantityFromModelValue (value: unknown, minQty = 0): number | null {
  if (value === null || value === undefined || value === '') return null

  const numeric = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(numeric)) return null

  return Math.max(minQty, Math.trunc(numeric))
}

export function clampQuantity (qty: number, maxQty?: number | null, minQty = 0): number {
  const normalized = Math.max(minQty, Math.trunc(qty))
  return maxQty != null ? Math.min(normalized, maxQty) : normalized
}
