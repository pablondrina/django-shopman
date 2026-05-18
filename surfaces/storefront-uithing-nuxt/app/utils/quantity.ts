export function quantityFromModelValue (value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null

  const numeric = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(numeric)) return null

  return Math.max(0, Math.trunc(numeric))
}

export function clampQuantity (qty: number, maxQty?: number | null): number {
  const normalized = Math.max(0, Math.trunc(qty))
  return maxQty != null ? Math.min(normalized, maxQty) : normalized
}
