interface ManifestSource {
  name?: string
  short_name?: string
  description?: string
  start_url?: string
  scope?: string
  display?: string
  orientation?: string
  background_color?: string
  theme_color?: string
  lang?: string
  dir?: string
  categories?: string[]
}

interface HomeBrandingSource {
  home?: {
    shop?: {
      brand_name?: string
      tagline?: string
      description?: string
      theme_color?: string
      background_color?: string
    }
  }
}

const FALLBACK_MANIFEST: Required<Pick<ManifestSource,
  'name' | 'short_name' | 'description' | 'background_color' | 'theme_color'
>> = {
  name: 'Shopman',
  short_name: 'Shopman',
  description: 'Cardápio, pedidos e acompanhamento da loja.',
  background_color: '#fafaf9',
  theme_color: '#ff9500'
}

const PWA_ICONS = [
  { src: '/pwa/icon-192.png', sizes: '192x192', type: 'image/png' },
  { src: '/pwa/icon-512.png', sizes: '512x512', type: 'image/png' },
  { src: '/pwa/icon-maskable-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' }
]

function textOrFallback (value: unknown, fallback: string) {
  return typeof value === 'string' && value.trim() ? value.trim() : fallback
}

function normalizeManifest (source: ManifestSource | null) {
  const name = textOrFallback(source?.name, FALLBACK_MANIFEST.name)
  const shortName = textOrFallback(source?.short_name, source?.name || FALLBACK_MANIFEST.short_name)

  return {
    name,
    short_name: shortName.slice(0, 30),
    description: textOrFallback(source?.description, FALLBACK_MANIFEST.description),
    start_url: '/menu',
    scope: '/',
    display: source?.display || 'standalone',
    orientation: source?.orientation || 'portrait',
    background_color: textOrFallback(source?.background_color, FALLBACK_MANIFEST.background_color),
    theme_color: textOrFallback(source?.theme_color, FALLBACK_MANIFEST.theme_color),
    lang: source?.lang || 'pt-BR',
    dir: source?.dir || 'ltr',
    categories: source?.categories?.length ? source.categories : ['food', 'shopping'],
    prefer_related_applications: false,
    icons: PWA_ICONS
  }
}

async function fetchDjangoManifest (event: Parameters<typeof useRuntimeConfig>[0]) {
  const config = useRuntimeConfig(event)
  try {
    return await $fetch<ManifestSource>(`${config.djangoBaseUrl}/manifest.json`, {
      headers: { accept: 'application/manifest+json' },
      timeout: 1500
    })
  } catch {
    return null
  }
}

async function fetchDjangoHomeBranding (event: Parameters<typeof useRuntimeConfig>[0]) {
  const config = useRuntimeConfig(event)
  try {
    return await $fetch<HomeBrandingSource>(`${config.djangoBaseUrl}/api/v1/storefront/home/`, {
      headers: { accept: 'application/json' },
      timeout: 1500
    })
  } catch {
    return null
  }
}

async function fetchManifestSource (event: Parameters<typeof useRuntimeConfig>[0]) {
  const [manifest, home] = await Promise.all([
    fetchDjangoManifest(event),
    fetchDjangoHomeBranding(event)
  ])
  const shop = home?.home?.shop

  return {
    ...manifest,
    name: textOrFallback(manifest?.name, shop?.brand_name || FALLBACK_MANIFEST.name),
    short_name: textOrFallback(manifest?.short_name, shop?.brand_name || manifest?.name || FALLBACK_MANIFEST.short_name),
    description: textOrFallback(
      manifest?.description,
      shop?.tagline || shop?.description || FALLBACK_MANIFEST.description
    ),
    theme_color: textOrFallback(manifest?.theme_color, shop?.theme_color || FALLBACK_MANIFEST.theme_color),
    background_color: textOrFallback(
      manifest?.background_color,
      shop?.background_color || FALLBACK_MANIFEST.background_color
    )
  }
}

export default defineEventHandler(async (event) => {
  setResponseHeader(event, 'Content-Type', 'application/manifest+json; charset=utf-8')
  setResponseHeader(event, 'Cache-Control', 'public, max-age=300')
  return normalizeManifest(await fetchManifestSource(event))
})
