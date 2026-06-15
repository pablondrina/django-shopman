import type { CatalogItemProjection, ProductDetailProjection, ShopProjection } from '~/types/shopman'

// Lógica pura de SEO técnico. Contrato vem das projeções do backend (SAGRADO):
// montamos meta tags + JSON-LD schema.org a partir do dado já servido (produto,
// shop, config). Sem Vue/Nuxt aqui — 100% testável (vitest). As páginas passam
// o `origin`/`url` (via useRequestURL) para os links ficarem absolutos.

const CURRENCY = 'BRL'

// ── URLs absolutas ───────────────────────────────────────────────────────────
export function absoluteUrl (origin: string, path: string): string {
  const base = (origin || '').replace(/\/$/, '')
  if (!path) return base
  if (/^https?:\/\//i.test(path)) return path
  return `${base}${path.startsWith('/') ? '' : '/'}${path}`
}

// Imagem para Open Graph/schema: precisa ser absoluta. Resolve relativas contra
// o origin; passa absolutas adiante; null/vazio → null (cai no fallback).
export function absoluteImage (origin: string, imageUrl: string | null | undefined): string | null {
  const value = (imageUrl || '').trim()
  if (!value) return null
  return absoluteUrl(origin, value)
}

// ── Preço/disponibilidade no vocabulário schema.org ──────────────────────────
export function priceFromQ (priceQ: number | null | undefined): string {
  return (Math.max(0, Math.round(priceQ || 0)) / 100).toFixed(2)
}

export function availabilitySchemaUrl (availability: string | null | undefined): string {
  switch (availability) {
    case 'available':
    case 'low_stock':
      return 'https://schema.org/InStock'
    case 'planned_ok':
      return 'https://schema.org/PreOrder'
    default:
      return 'https://schema.org/OutOfStock'
  }
}

// ── Meta description ─────────────────────────────────────────────────────────
// Prioriza a curada (seo_description), cai para short_description; corta limpo
// em ~160 chars sem quebrar palavra.
export function metaDescription (
  product: Pick<ProductDetailProjection, 'seo_description' | 'short_description' | 'name'> | null | undefined,
  max = 160
): string {
  if (!product) return ''
  const raw = (product.seo_description || product.short_description || product.name || '').trim()
  return truncateClean(raw, max)
}

export function truncateClean (text: string, max: number): string {
  const value = (text || '').trim()
  if (value.length <= max) return value
  const cut = value.slice(0, max)
  const lastSpace = cut.lastIndexOf(' ')
  return `${(lastSpace > max * 0.6 ? cut.slice(0, lastSpace) : cut).trimEnd()}…`
}

// ── JSON-LD: Product + Offer ─────────────────────────────────────────────────
export function productJsonLd (params: {
  product: ProductDetailProjection
  origin: string
  url: string
  brandName: string
}): Record<string, unknown> {
  const { product, origin, url, brandName } = params
  const image = absoluteImage(origin, product.image_url)
  const ld: Record<string, unknown> = {
    '@context': 'https://schema.org',
    '@type': 'Product',
    name: product.name,
    sku: product.sku,
    description: metaDescription(product, 320),
    offers: {
      '@type': 'Offer',
      price: priceFromQ(product.base_price_q),
      priceCurrency: CURRENCY,
      availability: availabilitySchemaUrl(product.availability),
      url
    }
  }
  if (image) ld.image = image
  if (brandName) ld.brand = { '@type': 'Brand', name: brandName }
  if (Array.isArray(product.seo_keywords) && product.seo_keywords.length) {
    ld.keywords = product.seo_keywords.join(', ')
  }
  return ld
}

// ── JSON-LD: BreadcrumbList ──────────────────────────────────────────────────
export function breadcrumbJsonLd (items: Array<{ name: string, url: string }>): Record<string, unknown> {
  return {
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    itemListElement: items.map((item, index) => ({
      '@type': 'ListItem',
      position: index + 1,
      name: item.name,
      item: item.url
    }))
  }
}

// ── JSON-LD: CollectionPage + ItemList ───────────────────────────────────────
// Cardápio = uma página de coleção com a lista de produtos. Cada item aponta para
// a própria PDP (/product/<sku>) com Offer mínima — ajuda o Google a entender a
// vitrine sem duplicar o Product completo (que vive na PDP).
export function collectionJsonLd (params: {
  name: string
  url: string
  origin: string
  items: Array<Pick<CatalogItemProjection, 'sku' | 'name' | 'base_price_q' | 'availability' | 'image_url'>>
}): Record<string, unknown> {
  const { name, url, origin, items } = params
  return {
    '@context': 'https://schema.org',
    '@type': 'CollectionPage',
    name,
    url,
    mainEntity: {
      '@type': 'ItemList',
      numberOfItems: items.length,
      itemListElement: items.map((item, index) => {
        const product: Record<string, unknown> = {
          '@type': 'Product',
          name: item.name,
          sku: item.sku,
          url: absoluteUrl(origin, `/product/${encodeURIComponent(item.sku)}`),
          offers: {
            '@type': 'Offer',
            price: priceFromQ(item.base_price_q),
            priceCurrency: CURRENCY,
            availability: availabilitySchemaUrl(item.availability)
          }
        }
        const image = absoluteImage(origin, item.image_url)
        if (image) product.image = image
        return {
          '@type': 'ListItem',
          position: index + 1,
          item: product
        }
      })
    }
  }
}

// ── JSON-LD: Bakery (LocalBusiness) ──────────────────────────────────────────
// Subtipo de FoodEstablishment. Só emite o que existe — nada de campo vazio que
// gere schema inválido.
export function bakeryJsonLd (params: {
  shop: ShopProjection
  origin: string
  url: string
  latitude: number | null
  longitude: number | null
}): Record<string, unknown> {
  const { shop, origin, url, latitude, longitude } = params
  const ld: Record<string, unknown> = {
    '@context': 'https://schema.org',
    '@type': 'Bakery',
    name: shop.brand_name,
    url
  }
  const logo = absoluteImage(origin, shop.logo_url)
  if (logo) ld.image = logo
  if (shop.description) ld.description = truncateClean(shop.description, 320)
  if (shop.phone) ld.telephone = shop.phone
  if (shop.email) ld.email = shop.email
  if (shop.full_address) {
    ld.address = { '@type': 'PostalAddress', streetAddress: shop.full_address, addressLocality: shop.default_city || undefined }
  }
  if (typeof latitude === 'number' && typeof longitude === 'number') {
    ld.geo = { '@type': 'GeoCoordinates', latitude, longitude }
  }
  if (Array.isArray(shop.social_links) && shop.social_links.length) {
    ld.sameAs = shop.social_links.map(link => link.url).filter(Boolean)
  }
  return ld
}
