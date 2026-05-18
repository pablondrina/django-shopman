import { describe, expect, it } from 'vitest'
import { shopThemeStyle } from '../app/utils/shopTheme'

describe('shop theme tokens', () => {
  it('maps backend design tokens into CSS variables', () => {
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
      '--background': 'rgb(255 255 255)',
      '--foreground': 'rgb(10 10 10)',
      '--primary': 'rgb(23 23 23)',
      '--primary-foreground': 'rgb(250 250 250)',
      '--accent': 'rgb(255 68 0)'
    })
  })
})
