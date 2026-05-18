import { describe, expect, it } from 'vitest'
import { shopThemeStyle } from '../app/utils/shopTheme'

describe('shop theme tokens', () => {
  it('keeps UI Thing tokens surface-owned and exposes backend brand hints separately', () => {
    expect(shopThemeStyle({
      brand_name: 'Nelson',
      tagline: '',
      description: '',
      description_html: '',
      logo_url: '',
      color_mode: 'light',
      theme_color: '#171717',
      whatsapp_url: '',
      phone: '',
      phone_display: '',
      phone_url: '',
      email: '',
      full_address: '',
      maps_url: '',
      default_city: '',
      social_links: [],
      design_tokens: {
        background: '255 255 255',
        foreground: '10 10 10',
        primary: '23 23 23',
        primary_foreground: '250 250 250',
        accent: '255 68 0'
      }
    })).toMatchObject({
      '--shop-brand-color': '#171717'
    })
  })

  it('does not let shop projection tokens override UI Thing theme variables', () => {
    const style = shopThemeStyle({
      brand_name: 'Nelson',
      tagline: '',
      description: '',
      description_html: '',
      logo_url: '',
      color_mode: 'light',
      theme_color: '#171717',
      background_color: '255 255 255',
      whatsapp_url: '',
      phone: '',
      phone_display: '',
      phone_url: '',
      email: '',
      full_address: '',
      maps_url: '',
      default_city: '',
      social_links: [],
      design_tokens: {
        background: '255 255 255',
        foreground: '10 10 10',
        primary: '23 23 23',
        primary_foreground: '250 250 250',
        accent: '255 68 0'
      }
    })

    expect(style).toEqual({
      '--shop-brand-color': '#171717',
      '--shop-brand-background': 'rgb(255 255 255)'
    })
    expect(style).not.toHaveProperty('--background')
    expect(style).not.toHaveProperty('--primary')
    expect(style).not.toHaveProperty('--accent')
  })
})
