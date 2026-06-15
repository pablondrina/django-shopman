import { describe, expect, it } from 'vitest'
import { shopThemeCss, shopThemeStyle, tokenVars } from '../app/utils/shopTheme'
import type { ShopProjection } from '../app/types/shopman'

function shop (design_tokens: ShopProjection['design_tokens']): ShopProjection {
  return {
    brand_name: 'Nelson',
    tagline: '',
    description: '',
    description_html: '',
    logo_url: '',
    color_mode: 'light',
    theme_color: '#7c3a40',
    whatsapp_url: '',
    phone: '',
    phone_display: '',
    phone_url: '',
    email: '',
    full_address: '',
    maps_url: '',
    default_city: '',
    social_links: [],
    design_tokens
  }
}

const BRAND = {
  background: '244 235 215',
  foreground: '59 42 30',
  primary: '124 58 64',
  primary_foreground: '247 239 224',
  accent: '239 226 201',
  dark: {
    background: '36 23 18',
    foreground: '244 235 215',
    primary: '200 150 47'
  }
}

describe('shop theme — marca como override das variáveis reais', () => {
  it('mapeia design_tokens para as variáveis CSS que os componentes consomem (rgb)', () => {
    expect(shopThemeStyle(shop(BRAND))).toMatchObject({
      '--background': 'rgb(244 235 215)',
      '--foreground': 'rgb(59 42 30)',
      '--primary': 'rgb(124 58 64)',
      '--primary-foreground': 'rgb(247 239 224)',
      '--accent': 'rgb(239 226 201)'
    })
  })

  it('emite :root{} (claro) e .dark{} (escuro) a partir do mapa dark', () => {
    const css = shopThemeCss(shop(BRAND))
    expect(css).toContain(':root:root {')
    expect(css).toContain('--primary: rgb(124 58 64);')
    expect(css).toContain(':root.dark {')
    expect(css).toContain('--primary: rgb(200 150 47);')
    expect(css).toContain('--background: rgb(36 23 18);')
  })

  it('reversibilidade: sem design_tokens ⇒ nenhum override (cai no neutro)', () => {
    expect(shopThemeStyle(shop(undefined))).toEqual({})
    expect(shopThemeCss(shop(undefined))).toBe('')
    expect(tokenVars(undefined)).toEqual({})
  })

  it('reversibilidade: ?theme=neutral força o neutro ao vivo, sem tocar em dado', () => {
    expect(shopThemeCss(shop(BRAND), { preview: 'neutral' })).toBe('')
  })

  it('só emite a variável quando o token existe (token ausente ⇒ herda o neutro)', () => {
    const style = shopThemeStyle(shop({ primary: '124 58 64' }))
    expect(style).toEqual({ '--primary': 'rgb(124 58 64)' })
    expect(style).not.toHaveProperty('--background')
  })
})
