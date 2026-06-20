import { describe, expect, it } from 'vitest'
import { localRouteFromBackend, orderPaymentRoute, orderTrackingRoute } from '../app/utils/routes'

describe('backend route adapter', () => {
  it('keeps Django payment URLs inside the UI Thing payment route', () => {
    expect(localRouteFromBackend('/pedido/ORD-123/pagamento')).toBe('/pedido/ORD-123/pagamento')
    expect(localRouteFromBackend('/pedido/ORD-123/pagamento/?retry=1')).toBe('/pedido/ORD-123/pagamento?retry=1')
  })

  it('maps tracking (Django acompanhar + legado /tracking) para a rota pt-BR /pedido', () => {
    expect(localRouteFromBackend('/pedido/ORD-123/acompanhar/')).toBe('/pedido/ORD-123')
    expect(localRouteFromBackend('/tracking/ORD-123')).toBe('/pedido/ORD-123')
    expect(localRouteFromBackend('https://wa.me/5543999999999')).toBe('https://wa.me/5543999999999')
  })

  it('traduz rotas em inglês emitidas pelo backend para pt-BR', () => {
    expect(localRouteFromBackend('/cart')).toBe('/sacola')
    expect(localRouteFromBackend('/checkout')).toBe('/finalizar')
    expect(localRouteFromBackend('/login?next=/conta')).toBe('/entrar?next=/conta')
    expect(localRouteFromBackend('/account')).toBe('/conta')
  })

  it('builds local routes without touching backend API contracts', () => {
    expect(orderTrackingRoute('ORD 123')).toBe('/pedido/ORD%20123')
    expect(orderPaymentRoute('ORD 123')).toBe('/pedido/ORD%20123/pagamento')
  })
})
