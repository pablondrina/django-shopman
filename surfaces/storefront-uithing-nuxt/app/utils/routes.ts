const DJANGO_PAYMENT_RE = /^\/pedido\/([^/?#]+)\/pagamento\/?(?:([?#].*)?)$/
const DJANGO_TRACKING_RE = /^\/pedido\/([^/?#]+)\/acompanhar\/?(?:([?#].*)?)$/

export function localRouteFromBackend (value: string | null | undefined): string {
  if (!value) return '/'
  if (/^https?:\/\//i.test(value)) return value

  const normalized = value.startsWith('/') ? value : `/${value}`
  const payment = normalized.match(DJANGO_PAYMENT_RE)
  if (payment) return `/pedido/${payment[1]}/pagamento${payment[2] || ''}`

  const tracking = normalized.match(DJANGO_TRACKING_RE)
  if (tracking) return `/tracking/${tracking[1]}${tracking[2] || ''}`

  return normalized
}

export function orderTrackingRoute (ref: string): string {
  return `/tracking/${encodeURIComponent(ref)}`
}

export function orderPaymentRoute (ref: string): string {
  return `/pedido/${encodeURIComponent(ref)}/pagamento`
}
