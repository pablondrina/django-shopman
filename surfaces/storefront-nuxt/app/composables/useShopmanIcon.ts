const SHOPMAN_ICON_FALLBACK = 'i-lucide-utensils'

const SHOPMAN_ICON_MAP: Record<string, string> = {
  restaurant_menu: SHOPMAN_ICON_FALLBACK,
  restaurant: SHOPMAN_ICON_FALLBACK,
  bakery_dining: 'i-lucide-wheat',
  local_cafe: 'i-lucide-coffee',
  local_drink: 'i-lucide-cup-soda',
  inventory_2: 'i-lucide-package',
  sell: 'i-lucide-badge-percent',
  lunch_dining: 'i-lucide-sandwich',
  star: 'i-lucide-star',
  favorite: 'i-lucide-heart',
  category: 'i-lucide-layout-grid'
}

export function useShopmanIcon (icon: string | null | undefined): string {
  const key = String(icon || '').trim()
  if (!key) return SHOPMAN_ICON_FALLBACK
  if (key.startsWith('i-lucide-')) return key
  return SHOPMAN_ICON_MAP[key] || SHOPMAN_ICON_FALLBACK
}
