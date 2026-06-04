import type { ShopProjection } from '~/types/shopman'

function cssColor (value: string): string {
  const trimmed = value.trim()
  if (/^\d+\s+\d+\s+\d+(?:\s*\/\s*[\d.]+)?$/.test(trimmed)) return `rgb(${trimmed})`
  return trimmed
}

export function shopThemeStyle (shop: ShopProjection | null | undefined): Record<string, string> {
  const style: Record<string, string> = {}
  if (shop?.theme_color?.trim()) style['--shop-brand-color'] = cssColor(shop.theme_color)
  if (shop?.background_color?.trim()) style['--shop-brand-background'] = cssColor(shop.background_color)
  return style
}
