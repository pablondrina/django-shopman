import type {
  CartCommandResponse,
  CartItemProjection,
  CartProjection,
  ProductCommandMeta
} from '~/types/shopman'

const money = new Intl.NumberFormat('pt-BR', {
  style: 'currency',
  currency: 'BRL'
})

function emptyCart (): CartProjection {
  return {
    items: [],
    items_count: 0,
    is_empty: true,
    subtotal_q: 0,
    subtotal_display: 'R$ 0,00',
    original_subtotal_q: 0,
    original_subtotal_display: 'R$ 0,00',
    discount_total_q: 0,
    discount_total_display: 'R$ 0,00',
    has_discount: false,
    discount_lines: [],
    delivery_fee_q: null,
    delivery_fee_display: null,
    delivery_is_free: false,
    grand_total_q: 0,
    grand_total_display: 'R$ 0,00',
    coupon_code: null,
    coupon_discount_q: null,
    coupon_discount_display: null,
    has_unavailable_items: false,
    has_awaiting_confirmation_items: false,
    has_ready_for_confirmation_items: false,
    minimum_order_progress: null,
    upsell: null
  }
}

function cloneCart (cart: CartProjection): CartProjection {
  return JSON.parse(JSON.stringify(cart)) as CartProjection
}

function formatMoney (valueQ: number): string {
  return money.format(valueQ / 100)
}

function optimisticLine (meta: ProductCommandMeta, qty: number): CartItemProjection {
  const total = meta.price_q * qty
  return {
    line_id: `optimistic:${meta.sku}`,
    sku: meta.sku,
    name: meta.name,
    qty,
    unit_price_q: meta.price_q,
    total_price_q: total,
    price_display: meta.price_display || formatMoney(meta.price_q),
    total_display: formatMoney(total),
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

function recomputeTotals (cart: CartProjection): CartProjection {
  const subtotal = cart.items.reduce((sum, item) => sum + item.total_price_q, 0)
  const count = cart.items.reduce((sum, item) => sum + item.qty, 0)
  return {
    ...cart,
    items_count: count,
    is_empty: count === 0,
    subtotal_q: subtotal,
    subtotal_display: formatMoney(subtotal),
    original_subtotal_q: subtotal,
    original_subtotal_display: formatMoney(subtotal),
    grand_total_q: subtotal,
    grand_total_display: formatMoney(subtotal)
  }
}

export function useCartState () {
  const cart = useState<CartProjection>('shopman-cart', emptyCart)
  const pendingBySku = useState<Record<string, boolean>>('shopman-cart-pending', () => ({}))
  const lastError = useState<string | null>('shopman-cart-error', () => null)

  function setFromServer (next?: CartProjection | null) {
    if (next) cart.value = next
  }

  function qtyForSku (sku: string): number {
    return cart.value.items.find(item => item.sku === sku)?.qty || 0
  }

  function isPending (sku: string): boolean {
    return !!pendingBySku.value[sku]
  }

  function applyOptimisticQty (meta: ProductCommandMeta, qty: number) {
    const current = cloneCart(cart.value)
    const existing = current.items.find(item => item.sku === meta.sku)

    if (qty <= 0) {
      current.items = current.items.filter(item => item.sku !== meta.sku)
      cart.value = recomputeTotals(current)
      return
    }

    if (existing) {
      existing.qty = qty
      existing.total_price_q = existing.unit_price_q * qty
      existing.total_display = formatMoney(existing.total_price_q)
    } else {
      current.items.push(optimisticLine(meta, qty))
    }
    cart.value = recomputeTotals(current)
  }

  async function setSkuQty (meta: ProductCommandMeta, qty: number): Promise<CartCommandResponse> {
    const previous = cloneCart(cart.value)
    lastError.value = null
    pendingBySku.value = { ...pendingBySku.value, [meta.sku]: true }
    applyOptimisticQty(meta, qty)

    try {
      const response = await $fetch<CartCommandResponse>(shopmanApiPath(`/api/v1/cart/skus/${encodeURIComponent(meta.sku)}/`), {
        method: 'PUT',
        body: { qty },
        credentials: 'include'
      })
      cart.value = response.cart
      return response
    } catch (error) {
      cart.value = previous
      lastError.value = 'Não foi possível atualizar o carrinho.'
      throw error
    } finally {
      const next = { ...pendingBySku.value }
      delete next[meta.sku]
      pendingBySku.value = next
    }
  }

  return {
    cart,
    lastError,
    setFromServer,
    qtyForSku,
    isPending,
    setSkuQty
  }
}
