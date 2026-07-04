// Testes de estado do carrinho (WP-S1): fila serial de mutações, optimistic +
// reconciliação no drain, e os três ramos de erro que o cliente sente na sacola
// (409 substitutos, 429 rate-limit, falha genérica). $fetch é stubado como global
// (o composable resolve $fetch do runtime do Nuxt); o env `nuxt` provê useState.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mockNuxtImport } from '@nuxt/test-utils/runtime'
import type { ProductMutationMeta, SubstituteProjection } from '~/types/shopman'

mockNuxtImport('useSonner', () => {
  const fn: any = () => {}
  fn.success = () => {}
  fn.error = () => {}
  return () => fn
})

const meta: ProductMutationMeta = {
  sku: 'CROISSANT',
  name: 'Croissant',
  price_q: 500,
  price_display: 'R$ 5,00',
  image_url: null
}

function serverCart (overrides: Record<string, unknown> = {}) {
  return {
    items: [{ sku: 'CROISSANT', qty: 2 }],
    items_count: 2,
    is_empty: false,
    subtotal_q: 1000,
    subtotal_display: 'R$ 10,00',
    ...overrides
  }
}

function fetchError (status: number, data: Record<string, unknown>) {
  return Object.assign(new Error(`HTTP ${status}`), { response: { status }, data })
}

async function loadStore () {
  const { useCartState } = await import('~/composables/useCartState')
  const store = useCartState()
  store.clearCart()
  return store
}

describe('useCartState', () => {
  beforeEach(() => {
    document.cookie = 'csrftoken=testtoken'
    vi.unstubAllGlobals()
  })

  it('optimistic update reconciles to server truth on drain', async () => {
    const $fetch = vi.fn().mockResolvedValue({ cart: serverCart() })
    vi.stubGlobal('$fetch', $fetch)
    const store = await loadStore()

    const res = await store.setSkuQty(meta, 2)

    expect($fetch).toHaveBeenCalledOnce()
    expect(res.cart.items_count).toBe(2)
    expect(store.cart.value.items_count).toBe(2)
    expect(store.cart.value.summary_pending).toBe(false)
    expect(store.isPending('CROISSANT')).toBe(false)
    expect(store.lastMutation.value).toBeNull()
    expect(store.lastError.value).toBeNull()
  })

  it('409 surfaces a cart issue with substitutes and preserves it', async () => {
    const issuePayload = {
      title: 'Sem estoque',
      detail: 'Croissant esgotou.',
      error_code: 'insufficient_stock',
      sku: 'CROISSANT',
      name: 'Croissant',
      requested_qty: 3,
      available_qty: 1,
      substitutes: [
        { sku: 'PAO', name: 'Pão', price_q: 400, can_order: true, target_qty: 2 }
      ]
    }
    const $fetch = vi
      .fn()
      .mockRejectedValueOnce(fetchError(409, issuePayload))
      .mockResolvedValueOnce({ cart: serverCart({ items: [], items_count: 0, is_empty: true }) })
    vi.stubGlobal('$fetch', $fetch)
    const store = await loadStore()

    await expect(store.setSkuQty(meta, 3)).rejects.toThrow()

    expect(store.cartIssue.value?.error_code).toBe('insufficient_stock')
    expect(store.cartIssue.value?.sku).toBe('CROISSANT')
    expect(store.cartIssue.value?.available_qty).toBe(1)
    expect(store.cartIssue.value?.substitutes).toHaveLength(1)
    expect(store.lastError.value).toBe('Croissant esgotou.')
    // Reconciliação passiva (refreshCart) rodou após o erro.
    expect($fetch).toHaveBeenCalledTimes(2)

    // Um snapshot passivo NÃO pode apagar o aviso de substitutos.
    store.setFromServer(serverCart({ items: [], items_count: 0, is_empty: true }) as never)
    expect(store.cartIssue.value?.error_code).toBe('insufficient_stock')
  })

  it('429 captures rate-limit recovery with retry-after', async () => {
    const $fetch = vi
      .fn()
      .mockRejectedValueOnce(fetchError(429, { detail: 'Muitas tentativas.', retry_after_seconds: 12 }))
      .mockResolvedValueOnce({ cart: serverCart() })
    vi.stubGlobal('$fetch', $fetch)
    const store = await loadStore()

    await expect(store.setSkuQty(meta, 2)).rejects.toThrow()

    expect(store.rateLimitRecovery.value?.retryAfterSeconds).toBe(12)
    expect(store.rateLimitRecovery.value?.detail).toBe('Muitas tentativas.')
    expect(store.cartIssue.value).toBeNull()
  })

  it('generic failure sets a human fallback error', async () => {
    const $fetch = vi
      .fn()
      .mockRejectedValueOnce(fetchError(500, {}))
      .mockResolvedValueOnce({ cart: serverCart() })
    vi.stubGlobal('$fetch', $fetch)
    const store = await loadStore()

    await expect(store.setSkuQty(meta, 2)).rejects.toThrow()

    expect(store.lastError.value).toBe('Não foi possível atualizar o carrinho.')
    expect(store.cartIssue.value).toBeNull()
    expect(store.rateLimitRecovery.value).toBeNull()
  })

  it('retryLastMutation replays the last failed mutation', async () => {
    const $fetch = vi
      .fn()
      .mockRejectedValueOnce(fetchError(500, {})) // mutação falha
      .mockResolvedValueOnce({ cart: serverCart({ items: [], items_count: 0, is_empty: true }) }) // refresh
      .mockResolvedValueOnce({ cart: serverCart() }) // retry bem-sucedido
    vi.stubGlobal('$fetch', $fetch)
    const store = await loadStore()

    await expect(store.setSkuQty(meta, 2)).rejects.toThrow()
    expect(store.lastMutation.value).not.toBeNull()

    const res = await store.retryLastMutation()
    expect(res?.cart.items_count).toBe(2)
    expect(store.cart.value.items_count).toBe(2)
    expect(store.lastError.value).toBeNull()
  })

  it('acceptAvailableQty re-submits with the available quantity from a 409', async () => {
    const $fetch = vi
      .fn()
      .mockRejectedValueOnce(fetchError(409, { error_code: 'insufficient_stock', sku: 'CROISSANT', requested_qty: 5, available_qty: 2 }))
      .mockResolvedValueOnce({ cart: serverCart({ items: [], items_count: 0, is_empty: true }) })
      .mockResolvedValueOnce({ cart: serverCart() })
    vi.stubGlobal('$fetch', $fetch)
    const store = await loadStore()

    await expect(store.setSkuQty(meta, 5)).rejects.toThrow()
    expect(store.cartIssue.value?.available_qty).toBe(2)

    const res = await store.acceptAvailableQty()
    expect(res?.cart.items_count).toBe(2)
    // A 3ª chamada (retry) mandou qty=2.
    const lastCall = $fetch.mock.calls.at(-1)
    expect(lastCall?.[1]?.body).toEqual({ qty: 2 })
  })

  it('addSubstitute swaps the out-of-stock item for an alternative', async () => {
    const $fetch = vi
      .fn()
      .mockRejectedValueOnce(fetchError(409, {
        error_code: 'insufficient_stock', sku: 'CROISSANT', requested_qty: 2, available_qty: 0,
        substitutes: [{ sku: 'PAO', name: 'Pão', price_q: 400, can_order: true, target_qty: 2 }]
      }))
      .mockResolvedValueOnce({ cart: serverCart({ items: [], items_count: 0, is_empty: true }) })
      .mockResolvedValueOnce({ cart: serverCart({ items: [{ sku: 'PAO', qty: 2 }] }) })
    vi.stubGlobal('$fetch', $fetch)
    const store = await loadStore()

    await expect(store.setSkuQty(meta, 2)).rejects.toThrow()
    const sub = store.cartIssue.value?.substitutes[0] as SubstituteProjection

    const res = await store.addSubstitute(sub)
    expect(res?.cart.items[0]?.sku).toBe('PAO')
    // O swap zera o aviso ao dar certo.
    expect(store.cartIssue.value).toBeNull()
    const lastCall = $fetch.mock.calls.at(-1)
    expect(lastCall?.[0]).toContain('/cart/skus/PAO/')
    expect(lastCall?.[1]?.body).toEqual({ qty: 2 })
  })

  it('serial queue keeps rapid mutations in order and settles on the last truth', async () => {
    const calls: number[] = []
    const $fetch = vi.fn().mockImplementation((_url: string, opts: any) => {
      const qty = opts?.body?.qty
      calls.push(qty)
      return Promise.resolve({ cart: serverCart({ items: [{ sku: 'CROISSANT', qty }], items_count: qty }) })
    })
    vi.stubGlobal('$fetch', $fetch)
    const store = await loadStore()

    const p1 = store.setSkuQty(meta, 1)
    const p2 = store.setSkuQty(meta, 4)
    await Promise.all([p1, p2])

    expect(calls).toEqual([1, 4]) // ordem preservada pela fila
    expect(store.cart.value.items_count).toBe(4) // última verdade
    expect(store.isPending('CROISSANT')).toBe(false)
  })

  it('retries a transient network blip transparently (no error surfaced)', async () => {
    const $fetch = vi.fn()
      .mockRejectedValueOnce(Object.assign(new Error('network'), {})) // sem status = rede
      .mockResolvedValueOnce({ cart: serverCart() })
    vi.stubGlobal('$fetch', $fetch)
    const store = await loadStore()

    const res = await store.setSkuQty(meta, 2)
    expect(res.cart.items_count).toBe(2)
    expect($fetch).toHaveBeenCalledTimes(2) // 1 falha + 1 retry
    expect(store.lastError.value).toBeNull() // soluço absorvido, cliente não vê erro
  })

  it('dismissCartIssue clears the banner', async () => {
    const $fetch = vi
      .fn()
      .mockRejectedValueOnce(fetchError(409, { error_code: 'insufficient_stock', sku: 'CROISSANT' }))
      .mockResolvedValueOnce({ cart: serverCart() })
    vi.stubGlobal('$fetch', $fetch)
    const store = await loadStore()

    await expect(store.setSkuQty(meta, 2)).rejects.toThrow()
    expect(store.cartIssue.value).not.toBeNull()
    store.dismissCartIssue()
    expect(store.cartIssue.value).toBeNull()
  })
})
