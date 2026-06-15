import { describe, expect, it } from 'vitest'
import type { ProductDetailProjection, ShopProjection } from '~/types/shopman'
import {
  absoluteImage,
  absoluteUrl,
  availabilitySchemaUrl,
  bakeryJsonLd,
  breadcrumbJsonLd,
  collectionJsonLd,
  metaDescription,
  priceFromQ,
  productJsonLd,
  truncateClean
} from '~/presentation/seo'

const ORIGIN = 'https://loja.exemplo.com'

function product (overrides: Partial<ProductDetailProjection> = {}): ProductDetailProjection {
  return {
    sku: 'CROIS-01',
    name: 'Croissant de Manteiga',
    short_description: 'Folhado, amanteigado, assado na hora.',
    seo_description: 'Croissant artesanal francês, folhado em camadas, assado fresco todo dia.',
    seo_keywords: ['croissant', 'padaria francesa', 'café da manhã'],
    image_url: '/media/produtos/croissant.jpg',
    base_price_q: 1290,
    price_display: 'R$ 12,90',
    availability: 'available',
    availability_label: 'Disponível',
    ...overrides
  } as unknown as ProductDetailProjection
}

function shop (overrides: Partial<ShopProjection> = {}): ShopProjection {
  return {
    brand_name: 'Nelson Boulangerie',
    description: 'Padaria artesanal francesa em Londrina.',
    logo_url: '/static/logo.png',
    phone: '+554333231997',
    email: 'nelson@boulangerie.com.br',
    full_address: 'Av. Madre Leônia Milito, 446 - Bela Suíça',
    default_city: 'Londrina',
    social_links: [{ url: 'https://instagram.com/nelson', platform: 'instagram', label: 'Instagram', icon_svg: '' }],
    ...overrides
  } as unknown as ShopProjection
}

describe('absoluteUrl', () => {
  it('junta origin + path', () => {
    expect(absoluteUrl(ORIGIN, '/produto/x')).toBe('https://loja.exemplo.com/produto/x')
    expect(absoluteUrl(ORIGIN + '/', 'produto/x')).toBe('https://loja.exemplo.com/produto/x')
  })
  it('preserva URL já absoluta', () => {
    expect(absoluteUrl(ORIGIN, 'https://cdn.x/y.jpg')).toBe('https://cdn.x/y.jpg')
  })
})

describe('absoluteImage', () => {
  it('resolve relativa contra origin', () => {
    expect(absoluteImage(ORIGIN, '/media/a.jpg')).toBe('https://loja.exemplo.com/media/a.jpg')
  })
  it('null quando vazio', () => {
    expect(absoluteImage(ORIGIN, null)).toBeNull()
    expect(absoluteImage(ORIGIN, '')).toBeNull()
  })
})

describe('priceFromQ', () => {
  it('centavos → reais com 2 casas', () => {
    expect(priceFromQ(1290)).toBe('12.90')
    expect(priceFromQ(0)).toBe('0.00')
    expect(priceFromQ(null)).toBe('0.00')
  })
})

describe('availabilitySchemaUrl', () => {
  it('mapeia disponibilidade para schema.org', () => {
    expect(availabilitySchemaUrl('available')).toBe('https://schema.org/InStock')
    expect(availabilitySchemaUrl('low_stock')).toBe('https://schema.org/InStock')
    expect(availabilitySchemaUrl('planned_ok')).toBe('https://schema.org/PreOrder')
    expect(availabilitySchemaUrl('unavailable')).toBe('https://schema.org/OutOfStock')
    expect(availabilitySchemaUrl(undefined)).toBe('https://schema.org/OutOfStock')
  })
})

describe('truncateClean', () => {
  it('mantém texto curto', () => {
    expect(truncateClean('curto', 160)).toBe('curto')
  })
  it('corta sem quebrar palavra', () => {
    const out = truncateClean('palavra '.repeat(40), 50)
    expect(out.length).toBeLessThanOrEqual(51)
    expect(out.endsWith('…')).toBe(true)
    expect(out).not.toContain('palavr…')
  })
})

describe('metaDescription', () => {
  it('prioriza seo_description', () => {
    expect(metaDescription(product())).toContain('Croissant artesanal')
  })
  it('cai para short_description', () => {
    expect(metaDescription(product({ seo_description: '' }))).toContain('Folhado')
  })
  it('vazio sem produto', () => {
    expect(metaDescription(null)).toBe('')
  })
})

describe('productJsonLd', () => {
  it('monta Product + Offer com dados do backend', () => {
    const url = 'https://loja.exemplo.com/produto/CROIS-01'
    const ld = productJsonLd({ product: product(), origin: ORIGIN, url, brandName: 'Nelson Boulangerie' })
    expect(ld['@type']).toBe('Product')
    expect(ld.name).toBe('Croissant de Manteiga')
    expect(ld.sku).toBe('CROIS-01')
    expect(ld.image).toBe('https://loja.exemplo.com/media/produtos/croissant.jpg')
    expect(ld.brand).toEqual({ '@type': 'Brand', name: 'Nelson Boulangerie' })
    expect(ld.keywords).toBe('croissant, padaria francesa, café da manhã')
    const offer = ld.offers as Record<string, unknown>
    expect(offer.price).toBe('12.90')
    expect(offer.priceCurrency).toBe('BRL')
    expect(offer.availability).toBe('https://schema.org/InStock')
    expect(offer.url).toBe(url)
  })
  it('omite imagem/brand quando ausentes', () => {
    const ld = productJsonLd({ product: product({ image_url: null }), origin: ORIGIN, url: 'x', brandName: '' })
    expect(ld.image).toBeUndefined()
    expect(ld.brand).toBeUndefined()
  })
})

describe('breadcrumbJsonLd', () => {
  it('numera as posições a partir de 1', () => {
    const ld = breadcrumbJsonLd([
      { name: 'Início', url: 'https://x/' },
      { name: 'Cardápio', url: 'https://x/menu' },
      { name: 'Croissant', url: 'https://x/produto/CROIS-01' }
    ])
    expect(ld['@type']).toBe('BreadcrumbList')
    const items = ld.itemListElement as Array<Record<string, unknown>>
    expect(items).toHaveLength(3)
    expect(items[0]!.position).toBe(1)
    expect(items[2]!.position).toBe(3)
    expect(items[2]!.name).toBe('Croissant')
    expect(items[2]!.item).toBe('https://x/produto/CROIS-01')
  })
})

describe('collectionJsonLd', () => {
  const items = [
    { sku: 'CROIS-01', name: 'Croissant', base_price_q: 1290, availability: 'available' as const, image_url: '/media/c.jpg' },
    { sku: 'BAGUE-01', name: 'Baguete', base_price_q: 1300, availability: 'unavailable' as const, image_url: null }
  ]
  it('monta CollectionPage com ItemList de produtos', () => {
    const ld = collectionJsonLd({ name: 'Cardápio', url: ORIGIN + '/menu', origin: ORIGIN, items })
    expect(ld['@type']).toBe('CollectionPage')
    expect(ld.url).toBe('https://loja.exemplo.com/menu')
    const list = ld.mainEntity as Record<string, unknown>
    expect(list['@type']).toBe('ItemList')
    expect(list.numberOfItems).toBe(2)
    const elements = list.itemListElement as Array<Record<string, unknown>>
    expect(elements[0]!.position).toBe(1)
    const first = elements[0]!.item as Record<string, unknown>
    expect(first['@type']).toBe('Product')
    expect(first.url).toBe('https://loja.exemplo.com/product/CROIS-01')
    expect(first.image).toBe('https://loja.exemplo.com/media/c.jpg')
    expect((first.offers as Record<string, unknown>).price).toBe('12.90')
  })
  it('omite imagem quando ausente', () => {
    const ld = collectionJsonLd({ name: 'Cardápio', url: ORIGIN + '/menu', origin: ORIGIN, items })
    const elements = (ld.mainEntity as Record<string, unknown>).itemListElement as Array<Record<string, unknown>>
    const second = elements[1]!.item as Record<string, unknown>
    expect(second.image).toBeUndefined()
    expect((second.offers as Record<string, unknown>).availability).toBe('https://schema.org/OutOfStock')
  })
})

describe('bakeryJsonLd', () => {
  it('monta Bakery com endereço, geo e sameAs', () => {
    const ld = bakeryJsonLd({
      shop: shop(), origin: ORIGIN, url: ORIGIN + '/', latitude: -23.31, longitude: -51.16
    })
    expect(ld['@type']).toBe('Bakery')
    expect(ld.name).toBe('Nelson Boulangerie')
    expect(ld.telephone).toBe('+554333231997')
    expect(ld.image).toBe('https://loja.exemplo.com/static/logo.png')
    expect((ld.address as Record<string, unknown>).addressLocality).toBe('Londrina')
    expect((ld.geo as Record<string, unknown>).latitude).toBe(-23.31)
    expect(ld.sameAs).toEqual(['https://instagram.com/nelson'])
  })
  it('omite geo quando faltam coordenadas', () => {
    const ld = bakeryJsonLd({ shop: shop(), origin: ORIGIN, url: ORIGIN, latitude: null, longitude: null })
    expect(ld.geo).toBeUndefined()
  })
})
