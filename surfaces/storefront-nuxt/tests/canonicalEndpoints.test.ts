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
  'app/pages/produto/[sku].vue',
  'app/pages/sacola.vue',
  'app/pages/finalizar.vue',
  'app/pages/pedido/[ref]/index.vue',
  'app/pages/pedido/[ref]/pagamento.vue',
  'app/pages/conta/index.vue',
  'app/pages/conta/pedidos.vue',
  'app/pages/conta/enderecos.vue',
  'app/pages/conta/perfil.vue',
  'app/pages/conta/preferencias.vue',
  'app/pages/conta/seguranca.vue',
  'app/middleware/account.ts',
  'app/pages/entrar.vue',
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
  '/api/v1/geocode/'
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
    const login = read('app/pages/entrar.vue')
    expect(login).toContain('requestedPhone.value = response.phone')
    expect(login).toContain('body: { phone: requestedPhone.value, code: code.value }')
  })
})
