// Refazer pedido (WP-S1): sucesso hidrata o carrinho e navega; 409 abre o painel
// de conflito (sem navegar); pending é sempre limpo no finally.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mockNuxtImport } from '@nuxt/test-utils/runtime'

const { navigateTo } = vi.hoisted(() => ({ navigateTo: vi.fn() }))
mockNuxtImport('navigateTo', () => navigateTo)
mockNuxtImport('useSonner', () => {
  const fn: any = () => {}
  fn.success = () => {}
  fn.error = () => {}
  return () => fn
})

function fetchError (status: number, data: Record<string, unknown>) {
  return Object.assign(new Error(`HTTP ${status}`), { response: { status }, data })
}

async function loadReorder () {
  const { useReorder } = await import('~/composables/useReorder')
  return useReorder()
}

describe('useReorder', () => {
  beforeEach(() => {
    document.cookie = 'csrftoken=testtoken'
    vi.unstubAllGlobals()
    navigateTo.mockClear()
  })

  it('submit success hydrates the cart, clears conflict and navigates to the bag', async () => {
    const $fetch = vi.fn().mockResolvedValue({ ok: true, cart: { items: [{ sku: 'X', qty: 1 }], items_count: 1, is_empty: false } })
    vi.stubGlobal('$fetch', $fetch)
    const reorder = await loadReorder()

    const res = await reorder.submit('ORD-9', 'append')
    expect(res.ok).toBe(true)
    expect(reorder.conflict.value).toBeNull()
    expect(navigateTo).toHaveBeenCalledWith('/sacola')
    // idempotency key foi enviada
    expect($fetch.mock.calls[0]?.[1]?.headers?.['x-idempotency-key']).toBeTruthy()
    expect(reorder.pending.value['ORD-9']).toBeUndefined() // limpo no finally
  })

  it('409 opens the conflict panel without navigating', async () => {
    const conflictPayload = { unavailable: [{ sku: 'X', name: 'X' }], mode: 'append' }
    const $fetch = vi.fn().mockRejectedValue(fetchError(409, conflictPayload))
    vi.stubGlobal('$fetch', $fetch)
    const reorder = await loadReorder()

    await expect(reorder.submit('ORD-7')).rejects.toThrow()
    expect(reorder.conflict.value).toEqual(conflictPayload)
    expect(navigateTo).not.toHaveBeenCalled()
    expect(reorder.pending.value['ORD-7']).toBeUndefined()
  })

  it('performAction extracts the order ref from the action href', async () => {
    const $fetch = vi.fn().mockResolvedValue({ ok: true, cart: { items: [], items_count: 0, is_empty: true } })
    vi.stubGlobal('$fetch', $fetch)
    const reorder = await loadReorder()

    await reorder.performAction({ href: '/api/v1/orders/ORD-42/reorder/' } as never, 'replace')
    expect($fetch.mock.calls[0]?.[0]).toContain('/orders/ORD-42/reorder/')
    expect($fetch.mock.calls[0]?.[1]?.body).toEqual({ mode: 'replace' })
  })

  it('performAction is a no-op when the href has no order ref', async () => {
    const $fetch = vi.fn()
    vi.stubGlobal('$fetch', $fetch)
    const reorder = await loadReorder()

    const res = await reorder.performAction({ href: '/nope/' } as never)
    expect(res).toBeNull()
    expect($fetch).not.toHaveBeenCalled()
  })
})
