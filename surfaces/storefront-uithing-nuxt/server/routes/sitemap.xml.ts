import type { MenuResponse } from '~/types/shopman'

// sitemap.xml domain-aware, alimentado pelo catálogo real (Django). Inclui a
// home, o cardápio, cada coleção estática (/colecao/<ref>) e cada PDP
// (/produto/<sku>). As variantes de filtro (?filtro=/?secao=) NÃO entram — elas
// canonicalizam para /menu (anti-duplicate).
export default defineEventHandler(async (event) => {
  const config = useRuntimeConfig()
  const origin = getRequestURL(event).origin

  let skus: string[] = []
  let collectionRefs: string[] = []
  try {
    const menu = await $fetch<MenuResponse>(`${config.djangoBaseUrl}/api/v1/storefront/menu/`)
    const items = menu?.catalog?.items || []
    skus = [...new Set(items.map(item => item.sku).filter(Boolean))]
    // Só coleções ESTÁTICAS viram rota indexável; seções dinâmicas ("Destaques"
    // etc.) são curadoria volátil → ficam fora do sitemap.
    const sections = menu?.catalog?.sections || []
    collectionRefs = [...new Set(sections.filter(s => s && !s.is_dynamic && s.ref).map(s => s.ref))]
  } catch {
    // Catálogo indisponível: ainda servimos as rotas estáticas.
  }

  const urls = [
    { loc: `${origin}/`, priority: '1.0' },
    { loc: `${origin}/menu`, priority: '0.9' },
    ...collectionRefs.map(ref => ({ loc: `${origin}/colecao/${encodeURIComponent(ref)}`, priority: '0.7' })),
    ...skus.map(sku => ({ loc: `${origin}/produto/${encodeURIComponent(sku)}`, priority: '0.8' }))
  ]

  const body = `<?xml version="1.0" encoding="UTF-8"?>\n`
    + `<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n`
    + urls.map(url => `  <url><loc>${url.loc}</loc><priority>${url.priority}</priority></url>`).join('\n')
    + `\n</urlset>\n`

  setHeader(event, 'content-type', 'application/xml; charset=utf-8')
  return body
})
