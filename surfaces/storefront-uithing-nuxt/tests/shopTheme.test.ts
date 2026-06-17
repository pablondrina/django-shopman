import { describe, expect, it } from 'vitest'
import { shopFontFamily, shopFontLinks, shopThemeCss, shopThemeStyle, tokenVars } from '../app/utils/shopTheme'
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

describe('shop theme — tipografia da marca', () => {
  // Instrument Sans é a fonte CANÔNICA do tema (self-hospedada via @nuxt/fonts no
  // tailwind.css). A marca não a re-injeta nem busca externamente.
  const CANON = { ...BRAND, heading_font: 'Instrument Sans', body_font: 'Instrument Sans' }
  // Um tenant pode pedir uma fonte DIFERENTE — aí o override + <link> permanecem.
  const TENANT = { ...BRAND, heading_font: 'Poppins', body_font: 'Poppins' }

  it('fonte canônica (Instrument Sans) é self-hospedada: sem override de --font-sans e sem <link> de runtime', () => {
    expect(shopFontFamily(CANON)).toBeNull()
    expect(shopThemeCss(shop(CANON))).not.toContain('--font-sans')
    expect(shopFontLinks(shop(CANON))).toEqual([])
  })

  it('tenant com fonte DIFERENTE ainda sobrescreve --font-sans + carrega via <link> Google (400/500/600)', () => {
    expect(shopFontFamily(TENANT)).toBe("'Poppins', ui-sans-serif, system-ui, sans-serif")
    expect(shopThemeCss(shop(TENANT))).toContain("--font-sans: 'Poppins', ui-sans-serif, system-ui, sans-serif;")
    const links = shopFontLinks(shop(TENANT))
    expect(links.some(l => l.rel === 'preconnect' && l.href === 'https://fonts.googleapis.com')).toBe(true)
    const sheet = links.find(l => l.rel === 'stylesheet')
    expect(sheet?.href).toContain('family=Poppins:wght@400;500;600')
    expect(sheet?.href).toContain('display=swap')
  })

  it('reversibilidade: sem fonte / preview neutro ⇒ sem --font-sans e sem links', () => {
    expect(shopFontFamily(undefined)).toBeNull()
    expect(shopThemeCss(shop(BRAND))).not.toContain('--font-sans')
    expect(shopFontLinks(shop(undefined))).toEqual([])
    expect(shopFontLinks(shop(TENANT), { preview: 'neutral' })).toEqual([])
  })
})

describe('shop theme — superfícies de identidade (navbar/rodapé)', () => {
  const SURFACES = {
    ...BRAND,
    header: '124 58 64',
    header_foreground: '247 239 224',
    footer: '94 123 59',
    footer_foreground: '247 239 224'
  }

  it('mapeia header/footer para --shop-header*/--shop-footer*', () => {
    expect(shopThemeStyle(shop(SURFACES))).toMatchObject({
      '--shop-header': 'rgb(124 58 64)',
      '--shop-header-foreground': 'rgb(247 239 224)',
      '--shop-footer': 'rgb(94 123 59)',
      '--shop-footer-foreground': 'rgb(247 239 224)'
    })
  })

  it('emite o remap escopado da navbar só quando há header (conteúdo creme sobre burgundy)', () => {
    const css = shopThemeCss(shop(SURFACES))
    expect(css).toContain('.shop-header-bar {')
    expect(css).toContain('--foreground: var(--shop-header-foreground)')
    expect(css).toContain('--background: var(--shop-header)')
    // sem header ⇒ sem remap (navbar neutra)
    expect(shopThemeCss(shop(BRAND))).not.toContain('.shop-header-bar')
  })

  it('reversibilidade: ?theme=neutral ⇒ sem vars de superfície e sem remap', () => {
    expect(shopThemeCss(shop(SURFACES), { preview: 'neutral' })).toBe('')
  })
})
