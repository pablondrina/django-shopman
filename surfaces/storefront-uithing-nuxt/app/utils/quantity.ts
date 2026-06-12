export function clampQuantity (qty: number, maxQty?: number | null, minQty = 0): number {
  const normalized = Math.max(minQty, Math.trunc(qty))
  return maxQty != null ? Math.min(normalized, maxQty) : normalized
}
