import { describe, expect, it } from 'vitest'
import { applySkuQty, cartItemsCount, formatCentavos, isOptimisticLine } from '~/presentation/cart'
import type { CartItemProjection, CartProjection, ProductMutationMeta } from '~/types/shopman'

function line (overrides: Partial<CartItemProjection> = {}): CartItemProjection {
  return {
    line_id: 'line-1',
    sku: 'PAO-001',
    name: 'Pão Francês',
    qty: 2,
    unit_price_q: 150,
    total_price_q: 300,
    price_display: 'R$ 1,50',
    total_display: 'R$ 3,00',
    image_url: null,
    original_price_display: null,
    discount_label: null,
    is_available: true,
    availability_warning: null,
    available_qty: null,
    is_awaiting_confirmation: false,
    is_ready_for_confirmation: false,
    confirmation_deadline_iso: null,
    confirmation_deadline_display: null,
    ...overrides
  }
}

function cart (items: CartItemProjection[] = []): CartProjection {
  return {
    items,
    items_count: cartItemsCount(items),
    is_empty: items.length === 0,
    summary_pending: false,
    subtotal_q: 300,
    subtotal_display: 'R$ 3,00',
    original_subtotal_q: 300,
    original_subtotal_display: 'R$ 3,00',
    discount_total_q: 0,
    discount_total_display: 'R$ 0,00',
    has_discount: false,
    discount_lines: [],
    delivery_fee_q: null,
    delivery_fee_display: null,
    delivery_is_free: false,
    grand_total_q: 300,
    grand_total_display: 'R$ 3,00',
    coupon_code: null,
    coupon_discount_q: null,
    coupon_discount_display: null,
    has_unavailable_items: false,
    has_awaiting_confirmation_items: false,
    has_ready_for_confirmation_items: false,
    minimum_order_progress: null,
    upsell: null,
    actions: []
  }
}

const meta: ProductMutationMeta = {
  sku: 'CROIS-001',
  name: 'Croissant',
  price_q: 1200,
  price_display: 'R$ 12,00',
  image_url: null
}

describe('cart presentation — applySkuQty', () => {
  it('formats centavos in pt-BR currency', () => {
    expect(formatCentavos(1200)).toBe('R$ 12,00')
    expect(formatCentavos(0)).toBe('R$ 0,00')
    expect(formatCentavos(123456)).toBe('R$ 1.234,56')
  })

  it('inserts an optimistic line for a sku not yet in the cart', () => {
    const next = applySkuQty(cart([line()]), meta, 3)
    expect(next.items).toHaveLength(2)
    const added = next.items[1]!
    expect(added.sku).toBe('CROIS-001')
    expect(added.qty).toBe(3)
    expect(added.total_price_q).toBe(3600)
    expect(added.total_display).toBe('R$ 36,00')
    expect(isOptimisticLine(added)).toBe(true)
    expect(next.items_count).toBe(5)
    expect(next.is_empty).toBe(false)
  })

  it('updates qty and line totals for an existing line', () => {
    const next = applySkuQty(cart([line()]), { ...meta, sku: 'PAO-001' }, 5)
    expect(next.items).toHaveLength(1)
    expect(next.items[0]!.qty).toBe(5)
    expect(next.items[0]!.total_price_q).toBe(750)
    expect(next.items[0]!.total_display).toBe('R$ 7,50')
    expect(next.items[0]!.line_id).toBe('line-1')
    expect(isOptimisticLine(next.items[0]!)).toBe(false)
    expect(next.items_count).toBe(5)
  })

  it('removes the line when qty drops to zero', () => {
    const next = applySkuQty(cart([line()]), { ...meta, sku: 'PAO-001' }, 0)
    expect(next.items).toHaveLength(0)
    expect(next.items_count).toBe(0)
    expect(next.is_empty).toBe(true)
  })

  it('keeps the server summary untouched and flags it as pending', () => {
    const next = applySkuQty(cart([line()]), meta, 1)
    expect(next.summary_pending).toBe(true)
    expect(next.subtotal_display).toBe('R$ 3,00')
    expect(next.grand_total_display).toBe('R$ 3,00')
  })

  it('does not mutate the previous cart snapshot', () => {
    const previous = cart([line()])
    applySkuQty(previous, { ...meta, sku: 'PAO-001' }, 9)
    expect(previous.items[0]!.qty).toBe(2)
    expect(previous.items_count).toBe(2)
    expect(previous.summary_pending).toBe(false)
  })
})
