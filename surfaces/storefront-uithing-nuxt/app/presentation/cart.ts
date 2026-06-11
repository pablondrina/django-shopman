import type { CartItemProjection, CartProjection, ProductMutationMeta } from '~/types/shopman'

// Transforms puros para escrita otimista do carrinho. Linhas (qty, total da linha,
// contagem) mudam na hora; o resumo (subtotal, descontos, total geral) é
// autoritativo do servidor e fica marcado como summary_pending até a reconciliação.

export const OPTIMISTIC_LINE_PREFIX = 'optimistic-'

export function formatCentavos (amountQ: number): string {
  const display = (amountQ / 100).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
  return display.replace(/\u00A0/g, ' ')
}

export function isOptimisticLine (line: CartItemProjection): boolean {
  return line.line_id.startsWith(OPTIMISTIC_LINE_PREFIX)
}

function optimisticLine (meta: ProductMutationMeta, qty: number): CartItemProjection {
  return {
    line_id: `${OPTIMISTIC_LINE_PREFIX}${meta.sku}`,
    sku: meta.sku,
    name: meta.name,
    qty,
    unit_price_q: meta.price_q,
    total_price_q: meta.price_q * qty,
    price_display: meta.price_display,
    total_display: formatCentavos(meta.price_q * qty),
    image_url: meta.image_url,
    original_price_display: null,
    discount_label: null,
    is_available: true,
    availability_warning: null,
    available_qty: null,
    is_awaiting_confirmation: false,
    is_ready_for_confirmation: false,
    confirmation_deadline_iso: null,
    confirmation_deadline_display: null
  }
}

function withQty (line: CartItemProjection, qty: number): CartItemProjection {
  return {
    ...line,
    qty,
    total_price_q: line.unit_price_q * qty,
    total_display: formatCentavos(line.unit_price_q * qty)
  }
}

export function cartItemsCount (items: CartItemProjection[]): number {
  return items.reduce((total, line) => total + line.qty, 0)
}

export function applySkuQty (cart: CartProjection, meta: ProductMutationMeta, qty: number): CartProjection {
  const hasLine = cart.items.some(line => line.sku === meta.sku)
  let items: CartItemProjection[]
  if (qty <= 0) {
    items = cart.items.filter(line => line.sku !== meta.sku)
  } else if (hasLine) {
    items = cart.items.map(line => (line.sku === meta.sku ? withQty(line, qty) : line))
  } else {
    items = [...cart.items, optimisticLine(meta, qty)]
  }

  const itemsCount = cartItemsCount(items)
  return {
    ...cart,
    items,
    items_count: itemsCount,
    is_empty: itemsCount === 0,
    summary_pending: true
  }
}
