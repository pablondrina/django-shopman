import { readFileSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const root = fileURLToPath(new URL('..', import.meta.url))
const sourceFiles = [
  'app/composables/useCartState.ts',
  'app/composables/useReorder.ts',
  'app/pages/index.vue',
  'app/pages/menu.vue',
  'app/pages/product/[sku].vue',
  'app/pages/cart.vue',
  'app/pages/checkout.vue',
  'app/pages/tracking/[ref].vue',
  'app/pages/pedido/[ref]/pagamento.vue',
  'app/pages/account.vue',
  'app/pages/login.vue',
  'server/api/v1/[...path].ts',
  'server/api/auth/[...path].ts'
]

const allowedPrefixes = [
  '/api/v1/storefront/',
  '/api/v1/cart/',
  '/api/v1/checkout/',
  '/api/v1/auth/',
  '/api/auth/',
  '/api/v1/account/',
  '/api/v1/orders/',
  '/api/v1/payment/',
  '/api/v1/tracking/',
  '/api/v1/geocode/',
  '/api/v1/delivery/'
]

function read (path: string) {
  return readFileSync(join(root, path), 'utf8')
}

function apiPathLiterals (source: string) {
  const matches = [...source.matchAll(/apiPath\((['"`])([^'"`$]+)\1/g)]
  return matches.map(match => match[2])
}

describe('canonical endpoint guardrail', () => {
  it('uses only canonical API prefixes for direct calls', () => {
    const offenders: string[] = []
    for (const file of sourceFiles) {
      for (const literal of apiPathLiterals(read(file))) {
        if (!literal.startsWith('/api/')) continue
        if (!allowedPrefixes.some(prefix => literal.startsWith(prefix))) {
          offenders.push(`${relative(root, join(root, file))}: ${literal}`)
        }
      }
    }

    expect(offenders).toEqual([])
  })

  it('does not call Django/Penguin HTML storefront endpoints as data sources', () => {
    const joined = sourceFiles.map(read).join('\n')
    expect(joined).not.toMatch(/\$fetch[^)]*\/pedido\//)
    expect(joined).not.toMatch(/apiPath\((['"`])\/storefront\/cart\/?\1/)
    expect(joined).not.toMatch(/apiPath\((['"`])\/storefront\/menu\/?\1/)
  })

  it('keeps auth verification pinned to the backend-returned requested phone', () => {
    const login = read('app/pages/login.vue')
    expect(login).toContain('requestedPhone.value = response.phone')
    expect(login).toContain('body: { phone: requestedPhone.value, code: code.value }')
  })
})
