import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { formatCount } from '../app/utils/display'

const root = fileURLToPath(new URL('..', import.meta.url))
const surfaceRoots = ['app/pages', 'app/components']

function collectVueFiles (dir: string): string[] {
  const absolute = join(root, dir)
  const files: string[] = []
  for (const entry of readdirSync(absolute)) {
    const path = join(absolute, entry)
    const rel = relative(root, path)
    if (rel.startsWith('app/components/Ui')) continue
    if (statSync(path).isDirectory()) {
      files.push(...collectVueFiles(rel))
    } else if (path.endsWith('.vue')) {
      files.push(rel)
    }
  }
  return files
}

function read (path: string) {
  return readFileSync(join(root, path), 'utf8')
}

function templateOnly (source: string) {
  return source.match(/<template>([\s\S]*?)<\/template>/)?.[1] || ''
}

const surfaceVueFiles = surfaceRoots.flatMap(collectVueFiles)

describe('surface UX guardrails', () => {
  it('keeps native controls wrapped behind UI Thing components', () => {
    const offenders = surfaceVueFiles
      .filter(file => /<(button|input|select|textarea)\b/.test(read(file)))
      .map(file => relative(root, join(root, file)))

    expect(offenders).toEqual([])
  })

  it('does not expose architecture vocabulary or placeholder plurals in templates', () => {
    const forbidden = /\b(backend|projection|mutation|canonic|ChannelConfig|payload|idempotente|servidor)\b|item\(ns\)|pedido\(s\)|salvo\(s\)|Disponibilidade projetada|Total projetado|Busca, secoes/i
    const offenders = surfaceVueFiles
      .filter(file => forbidden.test(templateOnly(read(file))))
      .map(file => relative(root, join(root, file)))

    expect(offenders).toEqual([])
  })

  it('uses the shared quantity control instead of plus/minus clones', () => {
    const quantitySurfaces = [
      'app/components/ProductTile.vue',
      'app/components/ProductDetailSheet.vue',
      'app/components/CartDrawer.vue',
      'app/pages/product/[sku].vue'
    ]
    for (const file of quantitySurfaces) {
      expect(read(file)).toContain('<QuantityControl')
      expect(read(file)).not.toMatch(/lucide:(plus|minus)/)
    }
  })

  it('does not revive stale projected quantities after cart removal', () => {
    const joined = surfaceVueFiles.map(read).join('\n')
    expect(joined).not.toMatch(/qtyForSku\([^)]*\)\s*\|\|\s*[^\n]*qty_in_cart/)
  })

  it('keeps storefront operational status sourced from shop_status', () => {
    const typeSource = read('app/types/shopman.ts')
    const omotenashiType = typeSource.match(/export interface OmotenashiProjection \{([\s\S]*?)\n\}/)?.[1] || ''

    expect(read('app/pages/index.vue')).not.toContain('home.omotenashi.is_open')
    expect(read('app/pages/index.vue')).toContain('home.value?.shop_status')
    expect(omotenashiType).not.toMatch(/\b(is_open|opens_at|closes_at)\b/)
  })

  it('does not render a second command search field in the menu', () => {
    expect(read('app/pages/menu.vue')).not.toContain('<UiCommandInput')
  })

  it('renders the menu product grid once instead of duplicating it in hidden tab panels', () => {
    const menu = read('app/pages/menu.vue')

    expect(menu).not.toMatch(/<UiTabsContent[\s\S]*?v-for=/)
    expect((menu.match(/<ProductTile/g) || [])).toHaveLength(1)
  })

  it('formats simple Portuguese counts without placeholder copy', () => {
    expect(formatCount(1, 'item', 'itens')).toBe('1 item')
    expect(formatCount(2, 'item', 'itens')).toBe('2 itens')
  })
})
