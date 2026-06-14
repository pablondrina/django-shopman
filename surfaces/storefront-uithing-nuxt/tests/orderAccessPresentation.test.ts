import { describe, expect, it } from 'vitest'
import { orderAccessErrorView } from '~/presentation/orderAccess'

describe('order access error view', () => {
  it('treats 404/403 as "needs login", not a dead error', () => {
    for (const code of [404, 403]) {
      const v = orderAccessErrorView(code, 'payment')
      expect(v.showLogin).toBe(true)
      expect(v.canRetry).toBe(false)
      expect(v.title).toBe('Não encontramos este pagamento')
      expect(v.message).toMatch(/Entre com seu telefone/)
    }
    expect(orderAccessErrorView(404, 'tracking').title).toBe('Não encontramos este pedido')
  })

  it('treats 429 as a calm wait-and-retry', () => {
    const v = orderAccessErrorView(429, 'tracking')
    expect(v.showLogin).toBe(false)
    expect(v.canRetry).toBe(true)
    expect(v.title).toMatch(/Muitas atualizações/)
  })

  it('falls back to a retryable instability message', () => {
    const v = orderAccessErrorView(500, 'payment')
    expect(v.showLogin).toBe(false)
    expect(v.canRetry).toBe(true)
    expect(v.title).toBe('Não foi possível abrir o pagamento agora')
    const t = orderAccessErrorView(undefined, 'tracking')
    expect(t.canRetry).toBe(true)
    expect(t.title).toBe('Não foi possível carregar o acompanhamento agora')
  })
})
