import { normalizeSearchText, formatCount } from '~/utils/display'
import type { CatalogItemProjection, CatalogSectionProjection } from '~/types/shopman'

// Transforms puros do cardápio: busca com scoring, filtros multi-select e
// badges de disponibilidade. Nenhum estado de UI aqui — a página orquestra.

export type SearchFilterKind = 'collection' | 'product' | 'keyword'

export type SearchListOption = {
  key: string
  kind: SearchFilterKind
  value: string
  label: string
  meta: string
  count?: number
  icon: string
  imageUrl?: string
  item?: CatalogItemProjection
  section?: CatalogSectionProjection
}

// O painel de busca tem três zonas: sem busca, a lista vertical de coleções
// (navega até a seção); com busca, chips filtram ao vivo (keywords e
// coleções) e linhas de produto navegam para a PDP.
export type SearchPanelView = {
  collections: SearchListOption[]
  chips: SearchListOption[]
  products: SearchListOption[]
}

export type TileBadge = {
  label: string
  variant: 'warning' | 'outline' | 'destructive'
}

export const FILTERED_SECTION_VALUE = 'filtered'

// Badge só quando informa: disponível é o estado default e não ganha selo.
export function tileBadge (item: CatalogItemProjection): TileBadge | null {
  if (item.availability === 'low_stock') return { label: item.availability_label, variant: 'warning' }
  if (item.availability === 'planned_ok') return { label: item.availability_label, variant: 'outline' }
  if (item.availability === 'unavailable') return { label: item.availability_label, variant: 'destructive' }
  return null
}

export function uniqueItemsBySku (items: ReadonlyArray<CatalogItemProjection>): CatalogItemProjection[] {
  const seen = new Set<string>()
  return items.filter(item => {
    if (seen.has(item.sku)) return false
    seen.add(item.sku)
    return true
  })
}

export function buildSectionsBySku (sections: ReadonlyArray<CatalogSectionProjection>): Map<string, CatalogSectionProjection[]> {
  const map = new Map<string, CatalogSectionProjection[]>()
  for (const section of sections) {
    for (const item of section.items) {
      const memberships = map.get(item.sku) || []
      memberships.push(section)
      map.set(item.sku, memberships)
    }
  }
  return map
}

export function primarySectionBySku (sectionsBySku: Map<string, CatalogSectionProjection[]>): Map<string, CatalogSectionProjection> {
  const map = new Map<string, CatalogSectionProjection>()
  for (const [sku, memberships] of sectionsBySku.entries()) {
    const firstStaticSection = memberships.find(section => !section.is_dynamic)
    const primary = firstStaticSection || memberships[0]
    if (primary) map.set(sku, primary)
  }
  return map
}

export function matchesItem (item: CatalogItemProjection, section: CatalogSectionProjection | undefined, search: string): boolean {
  return normalizeSearchText([
    item.name,
    item.short_description,
    item.category,
    section?.label,
    (item.tags || []).join(' '),
    (item.search_terms || []).join(' '),
    (item.allergens || []).join(' '),
    (item.dietary_info || []).join(' ')
  ].join(' ')).includes(search)
}

export function matchesProductAcrossCatalog (
  item: CatalogItemProjection,
  search: string,
  sectionsBySku: Map<string, CatalogSectionProjection[]>
): boolean {
  return normalizeSearchText([
    item.name,
    item.short_description,
    item.category,
    ...((sectionsBySku.get(item.sku) || []).flatMap(section => [section.label, section.description, section.ref])),
    (item.tags || []).join(' '),
    (item.search_terms || []).join(' '),
    (item.allergens || []).join(' '),
    (item.dietary_info || []).join(' ')
  ].join(' ')).includes(search)
}

export function collectionSearchScore (section: CatalogSectionProjection, search: string): number {
  const label = normalizeSearchText(section.label)
  const haystack = normalizeSearchText([section.label, section.description, section.ref].join(' '))
  if (label === search) return 0
  if (label.startsWith(search)) return 1
  if (label.includes(search)) return 2
  if (haystack.includes(search)) return 3
  return Number.POSITIVE_INFINITY
}

export function productSearchScore (
  item: CatalogItemProjection,
  search: string,
  sectionsBySku: Map<string, CatalogSectionProjection[]>
): number {
  const name = normalizeSearchText(item.name)
  const directTerms = normalizeSearchText([
    item.name,
    (item.tags || []).join(' '),
    (item.search_terms || []).join(' ')
  ].join(' '))
  if (name === search) return 0
  if (name.startsWith(search)) return 1
  if (name.includes(search)) return 2
  if (directTerms.includes(search)) return 3
  if (matchesProductAcrossCatalog(item, search, sectionsBySku)) return 4
  return Number.POSITIVE_INFINITY
}

export function keywordLabelsForItem (item: CatalogItemProjection): string[] {
  const itemName = normalizeSearchText(item.name)
  const itemCategory = normalizeSearchText(item.category || '')
  return Array.from(new Set([
    ...(item.tags || []),
    ...(item.search_terms || []),
    ...(item.allergens || []),
    ...(item.dietary_info || [])
  ].map(term => term.trim()).filter(term => {
    const normalized = normalizeSearchText(term)
    if (!normalized || normalized === itemName || normalized === itemCategory) return false
    if (term.length > 32 || /[,.]/.test(term)) return false
    // SKUs vazam pelos search_terms; código de produto não é chip de keyword.
    if (/^[A-Z0-9_-]+$/.test(term) && /[A-Z]/.test(term)) return false
    return term.split(/\s+/).length <= 3
  })))
}

export function filterKey (kind: SearchFilterKind, value: string): string {
  return `${kind}:${value}`
}

export function parseFilterKey (key: string): { kind: SearchFilterKind, value: string } | null {
  const [kind, ...rest] = key.split(':')
  if (!kind || !['collection', 'product', 'keyword'].includes(kind) || !rest.length) return null
  return { kind: kind as SearchFilterKind, value: rest.join(':') }
}

export function itemMatchesFilter (
  item: CatalogItemProjection,
  section: CatalogSectionProjection | undefined,
  key: string,
  sectionsBySku: Map<string, CatalogSectionProjection[]>
): boolean {
  const parsed = parseFilterKey(key)
  if (!parsed) return false
  if (parsed.kind === 'product') return item.sku === parsed.value
  if (parsed.kind === 'collection') return section?.ref === parsed.value
  return matchesProductAcrossCatalog(item, normalizeSearchText(parsed.value), sectionsBySku)
}

export function itemMatchesAnyFilter (
  item: CatalogItemProjection,
  section: CatalogSectionProjection | undefined,
  keys: string[],
  sectionsBySku: Map<string, CatalogSectionProjection[]>
): boolean {
  if (!keys.length) return true
  return keys.some(key => itemMatchesFilter(item, section, key, sectionsBySku))
}

export function itemPassesMenuFilters (
  item: CatalogItemProjection,
  section: CatalogSectionProjection | undefined,
  search: string,
  appliedFilterKeys: string[],
  sectionsBySku: Map<string, CatalogSectionProjection[]>
): boolean {
  if (search && !matchesItem(item, section, search)) return false
  if (appliedFilterKeys.length && !itemMatchesAnyFilter(item, section, appliedFilterKeys, sectionsBySku)) return false
  return true
}

// Em busca/filtro as seções estáticas vêm antes das dinâmicas e cada SKU
// aparece uma vez só (a primeira seção que o contém fica com ele).
export function orderedSections (
  sections: ReadonlyArray<CatalogSectionProjection>,
  searchOrFilterMode: boolean
): CatalogSectionProjection[] {
  if (!searchOrFilterMode) return [...sections]
  const staticSections = sections.filter(section => !section.is_dynamic)
  const dynamicSections = sections.filter(section => section.is_dynamic)
  return [...staticSections, ...dynamicSections]
}

export function filteredSections (
  sections: ReadonlyArray<CatalogSectionProjection>,
  search: string,
  appliedFilterKeys: string[],
  sectionsBySku: Map<string, CatalogSectionProjection[]>
): CatalogSectionProjection[] {
  const searchOrFilterMode = Boolean(search || appliedFilterKeys.length)
  const seenSkus = new Set<string>()
  return orderedSections(sections, searchOrFilterMode)
    .map(section => ({
      ...section,
      items: section.items.filter(item => {
        if (!itemPassesMenuFilters(item, section, search, appliedFilterKeys, sectionsBySku)) return false
        if (!searchOrFilterMode) return true
        if (seenSkus.has(item.sku)) return false
        seenSkus.add(item.sku)
        return true
      })
    }))
    .filter(section => section.items.length)
}

export function collectionSearchOptions (
  sections: ReadonlyArray<CatalogSectionProjection>,
  search: string
): SearchListOption[] {
  if (!search) return []
  return sections
    .map(section => ({ section, score: collectionSearchScore(section, search) }))
    .filter(result => result.score < Number.POSITIVE_INFINITY)
    .sort((a, b) => a.score - b.score || a.section.label.localeCompare(b.section.label))
    .map(result => {
      const count = uniqueItemsBySku([...result.section.items]).length
      return {
        key: filterKey('collection', result.section.ref),
        kind: 'collection' as const,
        value: result.section.ref,
        label: result.section.label,
        meta: formatCount(count, 'item', 'itens'),
        count,
        icon: 'lucide:rows-3',
        section: result.section
      }
    })
    .slice(0, 12)
}

export function productSearchOptions (
  items: ReadonlyArray<CatalogItemProjection>,
  search: string,
  sectionBySku: Map<string, CatalogSectionProjection>,
  sectionsBySku: Map<string, CatalogSectionProjection[]>
): SearchListOption[] {
  if (!search) return []
  return items
    .map(item => ({
      item,
      section: sectionBySku.get(item.sku),
      score: productSearchScore(item, search, sectionsBySku)
    }))
    .filter(result => result.score < Number.POSITIVE_INFINITY)
    .sort((a, b) => a.score - b.score || a.item.name.localeCompare(b.item.name))
    .map(result => ({
      key: filterKey('product', result.item.sku),
      kind: 'product' as const,
      value: result.item.sku,
      label: result.item.name,
      meta: result.item.price_display,
      icon: 'lucide:utensils',
      imageUrl: result.item.image_url || undefined,
      item: result.item,
      section: result.section
    }))
    .slice(0, 12)
}

export function keywordSearchOptions (
  items: ReadonlyArray<CatalogItemProjection>,
  search: string,
  sectionBySku: Map<string, CatalogSectionProjection>,
  sectionsBySku: Map<string, CatalogSectionProjection[]>
): SearchListOption[] {
  if (!search) return []
  const options = new Map<string, SearchListOption & { skus: Set<string> }>()
  for (const item of items) {
    const section = sectionBySku.get(item.sku)
    for (const keyword of keywordLabelsForItem(item)) {
      const normalized = normalizeSearchText(keyword)
      if (!normalized || !normalized.includes(search)) continue
      const key = filterKey('keyword', keyword)
      if (!options.has(key)) {
        options.set(key, {
          key,
          kind: 'keyword',
          value: keyword,
          label: keyword,
          meta: '0 itens',
          icon: 'lucide:tag',
          section,
          skus: new Set()
        })
      }
      options.get(key)?.skus.add(item.sku)
    }
  }
  return Array.from(options.values())
    .map(option => {
      const count = items.filter(item => matchesProductAcrossCatalog(item, normalizeSearchText(option.value), sectionsBySku)).length
      return { ...option, count, meta: formatCount(count, 'item', 'itens') }
    })
    .sort((a, b) => (b.count || 0) - (a.count || 0) || a.label.localeCompare(b.label))
    .map(({ skus: _skus, ...option }) => option)
    .slice(0, 8)
}

// Chips dos filtros já aplicados — visíveis ao reabrir a busca, para
// desempilhar ou conferir o que está ativo.
export function appliedFilterChips (
  keys: string[],
  sections: ReadonlyArray<CatalogSectionProjection>
): Array<{ key: string, label: string }> {
  return keys
    .map(key => {
      const parsed = parseFilterKey(key)
      if (!parsed) return null
      if (parsed.kind === 'collection') {
        const section = sections.find(s => s.ref === parsed.value)
        return { key, label: section?.label || parsed.value }
      }
      return { key, label: parsed.value }
    })
    .filter((chip): chip is { key: string, label: string } => chip !== null)
}

export function searchPanelView (input: {
  sections: ReadonlyArray<CatalogSectionProjection>
  items: ReadonlyArray<CatalogItemProjection>
  search: string
  favoriteRef: string
  sectionBySku: Map<string, CatalogSectionProjection>
  sectionsBySku: Map<string, CatalogSectionProjection[]>
}): SearchPanelView {
  const { sections, items, search, favoriteRef, sectionBySku, sectionsBySku } = input
  if (!search) {
    return {
      collections: sections.map(section => {
        const count = uniqueItemsBySku([...section.items]).length
        return {
          key: filterKey('collection', section.ref),
          kind: 'collection' as const,
          value: section.ref,
          label: section.label,
          meta: formatCount(count, 'item', 'itens'),
          count,
          icon: !!favoriteRef && [section.ref, section.category?.ref, section.dynamic_ref].includes(favoriteRef) ? 'lucide:heart' : 'lucide:rows-3',
          section
        }
      }),
      chips: [],
      products: []
    }
  }

  const keywords = keywordSearchOptions(items, search, sectionBySku, sectionsBySku)
  const collections = collectionSearchOptions(sections, search)
  return {
    collections: [],
    chips: [...keywords, ...collections].slice(0, 10),
    products: productSearchOptions(items, search, sectionBySku, sectionsBySku)
  }
}
