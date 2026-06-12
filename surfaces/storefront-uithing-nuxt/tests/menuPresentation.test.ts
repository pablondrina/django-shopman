import { describe, expect, it } from 'vitest'
import {
  appliedFilterChips,
  buildSectionsBySku,
  collectionSearchOptions,
  filteredSections,
  filterKey,
  itemMatchesAnyFilter,
  keywordSearchOptions,
  orderedSections,
  parseFilterKey,
  primarySectionBySku,
  productSearchOptions,
  searchPanelView,
  tileBadge,
  uniqueItemsBySku
} from '~/presentation/menu'
import type { CatalogItemProjection, CatalogSectionProjection } from '~/types/shopman'

function item (overrides: Partial<CatalogItemProjection> = {}): CatalogItemProjection {
  return {
    sku: 'PAO-001',
    slug: 'pao-frances',
    name: 'Pão Francês',
    short_description: 'Crocante por fora.',
    image_url: null,
    category: 'Rústicos',
    tags: [],
    search_terms: [],
    base_price_q: 150,
    price_display: 'R$ 1,50',
    has_promotion: false,
    original_price_display: null,
    promotion_label: null,
    unit_weight_label: null,
    availability: 'available',
    availability_label: 'Disponível',
    can_add_to_cart: true,
    dietary_info: [],
    is_new: false,
    is_featured: false,
    qty_in_cart: 0,
    available_qty: null,
    allergens: [],
    ...overrides
  }
}

function section (overrides: Partial<CatalogSectionProjection> = {}): CatalogSectionProjection {
  return {
    ref: 'rusticos',
    label: 'Rústicos',
    icon: '',
    description: 'Pães de fermentação longa',
    is_dynamic: false,
    dynamic_ref: null,
    category: null,
    items: [item()],
    ...overrides
  }
}

const croissant = item({ sku: 'CROIS-001', name: 'Croissant', category: 'Folhados', tags: ['manteiga'], search_terms: ['café da manhã'] })
const brigadeiro = item({ sku: 'BRIG-001', name: 'Brigadeiro', category: 'Doces', tags: ['chocolate'] })

const sections = [
  section(),
  section({ ref: 'folhados', label: 'Folhados', description: 'Massa folhada', items: [croissant] }),
  section({ ref: 'destaques', label: 'Destaques', description: '', is_dynamic: true, dynamic_ref: 'featured', items: [croissant, brigadeiro] }),
  section({ ref: 'doces', label: 'Doces', description: '', items: [brigadeiro] })
]
const allItems = uniqueItemsBySku(sections.flatMap(s => s.items))
const sectionsBySku = buildSectionsBySku(sections)
const sectionBySku = primarySectionBySku(sectionsBySku)

describe('menu presentation — tileBadge', () => {
  it('omits the badge for plainly available items', () => {
    expect(tileBadge(item())).toBeNull()
  })

  it('keeps server copy for meaningful states', () => {
    expect(tileBadge(item({ availability: 'low_stock', availability_label: 'Últimas 3 unidades' })))
      .toEqual({ label: 'Últimas 3 unidades', variant: 'warning' })
    expect(tileBadge(item({ availability: 'planned_ok', availability_label: 'Encomenda para amanhã' })))
      .toEqual({ label: 'Encomenda para amanhã', variant: 'outline' })
    expect(tileBadge(item({ availability: 'unavailable', availability_label: 'Esgotado' })))
      .toEqual({ label: 'Esgotado', variant: 'destructive' })
  })
})

describe('menu presentation — sections and filters', () => {
  it('maps each sku to its first static section', () => {
    expect(sectionBySku.get('CROIS-001')?.ref).toBe('folhados')
    expect(sectionBySku.get('BRIG-001')?.ref).toBe('doces')
  })

  it('keeps natural order outside search and moves dynamic sections last inside search', () => {
    expect(orderedSections(sections, false).map(s => s.ref)).toEqual(['rusticos', 'folhados', 'destaques', 'doces'])
    expect(orderedSections(sections, true).map(s => s.ref)).toEqual(['rusticos', 'folhados', 'doces', 'destaques'])
  })

  it('deduplicates skus across sections only in search mode', () => {
    const neutral = filteredSections(sections, '', [], sectionsBySku)
    expect(neutral.flatMap(s => s.items).filter(i => i.sku === 'CROIS-001')).toHaveLength(2)

    const searched = filteredSections(sections, 'croissant', [], sectionsBySku)
    expect(searched.flatMap(s => s.items)).toHaveLength(1)
    expect(searched[0]!.ref).toBe('folhados')
  })

  it('matches search across tags, terms and section labels without diacritics', () => {
    const byTag = filteredSections(sections, 'chocolate', [], sectionsBySku)
    expect(byTag.flatMap(s => s.items).map(i => i.sku)).toEqual(['BRIG-001'])

    const bySection = filteredSections(sections, 'rusticos', [], sectionsBySku)
    expect(bySection.flatMap(s => s.items).map(i => i.sku)).toContain('PAO-001')
  })

  it('applies multi-select filters as OR', () => {
    const keys = [filterKey('product', 'PAO-001'), filterKey('keyword', 'chocolate')]
    expect(itemMatchesAnyFilter(item(), sections[0], keys, sectionsBySku)).toBe(true)
    expect(itemMatchesAnyFilter(brigadeiro, sections[3], keys, sectionsBySku)).toBe(true)
    expect(itemMatchesAnyFilter(croissant, sections[1], keys, sectionsBySku)).toBe(false)
  })

  it('round-trips filter keys including values with colons', () => {
    expect(parseFilterKey(filterKey('keyword', 'café: especial'))).toEqual({ kind: 'keyword', value: 'café: especial' })
    expect(parseFilterKey('nonsense')).toBeNull()
  })

  it('describes applied filters with human labels', () => {
    const chips = appliedFilterChips([filterKey('keyword', 'chocolate'), filterKey('collection', 'doces'), 'nonsense'], sections)
    expect(chips).toEqual([
      { key: 'keyword:chocolate', label: 'chocolate' },
      { key: 'collection:doces', label: 'Doces' }
    ])
  })
})

describe('menu presentation — search options', () => {
  it('ranks collections by label proximity', () => {
    const options = collectionSearchOptions(sections, 'folhados')
    expect(options[0]!.value).toBe('folhados')
  })

  it('ranks products by name, then tags, then catalog context', () => {
    const options = productSearchOptions(allItems, 'croissant', sectionBySku, sectionsBySku)
    expect(options[0]!.value).toBe('CROIS-001')
    const byTag = productSearchOptions(allItems, 'manteiga', sectionBySku, sectionsBySku)
    expect(byTag.map(o => o.value)).toContain('CROIS-001')
  })

  it('aggregates keyword options with item counts', () => {
    const options = keywordSearchOptions(allItems, 'chocolate', sectionBySku, sectionsBySku)
    expect(options).toHaveLength(1)
    expect(options[0]!.label).toBe('chocolate')
    expect(options[0]!.meta).toBe('1 item')
  })

  it('does not surface sku-like search terms as keyword chips', () => {
    const leaky = item({ sku: 'CROIS-001', name: 'Croissant', search_terms: ['CROISSANT', 'MINI-CROISSANT', 'café da manhã'] })
    const options = keywordSearchOptions([leaky], 'croissant', sectionBySku, sectionsBySku)
    expect(options.map(o => o.label)).toEqual([])
    const legit = keywordSearchOptions([leaky], 'cafe', sectionBySku, sectionsBySku)
    expect(legit.map(o => o.label)).toEqual(['café da manhã'])
  })

  it('lists all collections vertically when the query is empty and marks the favorite', () => {
    const view = searchPanelView({ sections, items: allItems, search: '', favoriteRef: 'doces', sectionBySku, sectionsBySku })
    expect(view.products).toHaveLength(0)
    expect(view.chips).toHaveLength(0)
    expect(view.collections.map(c => c.value)).toEqual(['rusticos', 'folhados', 'destaques', 'doces'])
    expect(view.collections.find(c => c.value === 'doces')?.icon).toBe('lucide:heart')
    expect(view.collections[0]!.count).toBe(1)
  })

  it('splits an active query into filter chips and product rows', () => {
    const view = searchPanelView({ sections, items: allItems, search: 'croissant', favoriteRef: '', sectionBySku, sectionsBySku })
    expect(view.collections).toHaveLength(0)
    expect(view.products.map(p => p.value)).toEqual(['CROIS-001'])
    expect(view.chips.every(c => c.kind !== 'product')).toBe(true)
  })
})
