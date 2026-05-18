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

  it('formats simple Portuguese counts without placeholder copy', () => {
    expect(formatCount(1, 'item', 'itens')).toBe('1 item')
    expect(formatCount(2, 'item', 'itens')).toBe('2 itens')
  })
})
