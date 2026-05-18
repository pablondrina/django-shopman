import type { ShopProjection } from '~/types/shopman'

const TOKEN_TO_CSS_VAR: Record<string, string> = {
  background: '--background',
  foreground: '--foreground',
  card: '--card',
  card_foreground: '--card-foreground',
  popover: '--popover',
  popover_foreground: '--popover-foreground',
  primary: '--primary',
  primary_foreground: '--primary-foreground',
  secondary: '--secondary',
  secondary_foreground: '--secondary-foreground',
  muted: '--muted',
  muted_foreground: '--muted-foreground',
  accent: '--accent',
  accent_foreground: '--accent-foreground',
  destructive: '--destructive',
  destructive_foreground: '--destructive-foreground',
  success: '--success',
  success_foreground: '--success-foreground',
  warning: '--warning',
  warning_foreground: '--warning-foreground',
  info: '--info',
  info_foreground: '--info-foreground',
  border: '--border',
  input: '--input',
  ring: '--ring'
}

function cssColor (value: string): string {
  const trimmed = value.trim()
  if (/^\d+\s+\d+\s+\d+(?:\s*\/\s*[\d.]+)?$/.test(trimmed)) return `rgb(${trimmed})`
  return trimmed
}

export function shopThemeStyle (shop: ShopProjection | null | undefined): Record<string, string> {
  const style: Record<string, string> = {}
  const tokens = shop?.design_tokens
  if (tokens) {
    for (const [token, cssVar] of Object.entries(TOKEN_TO_CSS_VAR)) {
      const value = tokens[token as keyof typeof tokens]
      if (typeof value === 'string' && value.trim()) style[cssVar] = cssColor(value)
    }
  }
  if (shop?.theme_color && !style['--primary']) style['--primary'] = shop.theme_color
  if (shop?.background_color && !style['--background']) style['--background'] = shop.background_color
  return style
}

