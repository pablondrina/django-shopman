import { describe, expect, it } from 'vitest'
import { localRouteFromBackend, orderPaymentRoute, orderTrackingRoute } from '../app/utils/routes'

describe('backend route adapter', () => {
  it('keeps Django payment URLs inside the UI Thing payment route', () => {
    expect(localRouteFromBackend('/pedido/ORD-123/pagamento')).toBe('/pedido/ORD-123/pagamento')
    expect(localRouteFromBackend('/pedido/ORD-123/pagamento/?retry=1')).toBe('/pedido/ORD-123/pagamento?retry=1')
  })

  it('maps legacy tracking aliases and leaves canonical API-independent paths alone', () => {
    expect(localRouteFromBackend('/pedido/ORD-123/acompanhar/')).toBe('/tracking/ORD-123')
    expect(localRouteFromBackend('/tracking/ORD-123')).toBe('/tracking/ORD-123')
    expect(localRouteFromBackend('https://wa.me/5543999999999')).toBe('https://wa.me/5543999999999')
  })

  it('builds local routes without touching backend API contracts', () => {
    expect(orderTrackingRoute('ORD 123')).toBe('/tracking/ORD%20123')
    expect(orderPaymentRoute('ORD 123')).toBe('/pedido/ORD%20123/pagamento')
  })
})
