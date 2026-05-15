import type {
  CartCommandResponse,
  CartItemProjection,
  CartProjection,
  ProductCommandMeta
} from '~/types/shopman'

interface CartIssueItem {
  sku: string
  name: string
  requested_qty: number | null
  available_qty: number | null
  reason: string
}

interface CartStockIssue {
  title: string
  detail: string
  error_code: string
  sku: string
  name: string
  requested_qty: number | null
  available_qty: number | null
  is_paused: boolean
  is_planned: boolean
  planned_target_date: string | null
  substitutes: Array<{ sku?: string, name?: string, reason?: string }>
  items: CartIssueItem[]
}

interface CartRateLimitRecovery {
  detail: string
  retryAfterSeconds: number | null
}

interface CartCommandSnapshot {
  meta: ProductCommandMeta
  qty: number
}

const money = new Intl.NumberFormat('pt-BR', {
  style: 'currency',
  currency: 'BRL'
})

function emptyCart (): CartProjection {
  return {
    items: [],
    items_count: 0,
    is_empty: true,
    summary_pending: false,
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

function markSummaryPending (cart: CartProjection): CartProjection {
  const count = cart.items.reduce((sum, item) => sum + item.qty, 0)
  return {
    ...cart,
    items_count: count,
    is_empty: count === 0,
    summary_pending: true
  }
}

function numberOrNull (value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function stockReason (data: any) {
  if (data?.is_paused) return operationalCopy.availability.paused
  if (data?.is_planned) return operationalCopy.availability.plannedLimit
  if (typeof data?.available_qty === 'number' && data.available_qty > 0) {
    return `Disponível para este pedido: ${data.available_qty} unidade(s).`
  }
  return operationalCopy.availability.noStockForRequestedQty
}

function stockIssueFromPayload (data: any, meta: ProductCommandMeta): CartStockIssue {
  const fallbackItem: CartIssueItem = {
    sku: String(data?.sku || meta.sku),
    name: String(data?.name || meta.name || data?.sku || meta.sku),
    requested_qty: numberOrNull(data?.requested_qty),
    available_qty: numberOrNull(data?.available_qty),
    reason: stockReason(data)
  }
  const items = Array.isArray(data?.items)
    ? data.items.map((item: any) => ({
        sku: String(item?.sku || fallbackItem.sku),
        name: String(item?.name || fallbackItem.name),
        requested_qty: numberOrNull(item?.requested_qty),
        available_qty: numberOrNull(item?.available_qty),
        reason: String(item?.reason || fallbackItem.reason)
      }))
    : [fallbackItem]

  return {
    title: String(data?.title || operationalCopy.availability.reviewItem),
    detail: String(data?.detail || operationalCopy.availability.insufficientStock),
    error_code: String(data?.error_code || 'stock_unavailable'),
    sku: fallbackItem.sku,
    name: fallbackItem.name,
    requested_qty: fallbackItem.requested_qty,
    available_qty: fallbackItem.available_qty,
    is_paused: !!data?.is_paused,
    is_planned: !!data?.is_planned,
    planned_target_date: data?.planned_target_date || null,
    substitutes: Array.isArray(data?.substitutes) ? data.substitutes : [],
    items
  }
}

export function useCartState () {
  const cart = useState<CartProjection>('shopman-cart', emptyCart)
  const pendingBySku = useState<Record<string, boolean>>('shopman-cart-pending', () => ({}))
  const lastError = useState<string | null>('shopman-cart-error', () => null)
  const stockIssue = useState<CartStockIssue | null>('shopman-cart-stock-issue', () => null)
  const rateLimitRecovery = useState<CartRateLimitRecovery | null>('shopman-cart-rate-limit-recovery', () => null)
  const lastCartCommand = useState<CartCommandSnapshot | null>('shopman-cart-last-command', () => null)
  const apiPath = useShopmanApiPath()
  const csrfHeaders = useShopmanCsrfHeaders()
  const hasPendingMutations = computed(() => Object.values(pendingBySku.value).some(Boolean))

  function setFromServer (next?: CartProjection | null) {
    if (next) cart.value = { ...next, summary_pending: false }
    stockIssue.value = null
    rateLimitRecovery.value = null
  }

  function clearCart () {
    cart.value = emptyCart()
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
      if (current.items.length <= 1) {
        cart.value = { ...current, summary_pending: true }
        return
      }
      current.items = current.items.filter(item => item.sku !== meta.sku)
      cart.value = markSummaryPending(current)
      return
    }

    if (existing) {
      existing.qty = qty
      existing.total_price_q = existing.unit_price_q * qty
      existing.total_display = formatMoney(existing.total_price_q)
    } else {
      current.items.push(optimisticLine(meta, qty))
    }
    cart.value = markSummaryPending(current)
  }

  async function setSkuQty (meta: ProductCommandMeta, qty: number): Promise<CartCommandResponse> {
    const previous = cloneCart(cart.value)
    lastError.value = null
    stockIssue.value = null
    rateLimitRecovery.value = null
    lastCartCommand.value = { meta: { ...meta }, qty }
    pendingBySku.value = { ...pendingBySku.value, [meta.sku]: true }
    applyOptimisticQty(meta, qty)

    try {
      const response = await $fetch<CartCommandResponse>(apiPath(`/api/v1/cart/skus/${encodeURIComponent(meta.sku)}/`), {
        method: 'PUT',
        headers: await csrfHeaders(),
        body: { qty },
        credentials: 'include'
      })
      cart.value = response.cart
      lastCartCommand.value = null
      return response
    } catch (error: any) {
      cart.value = previous
      const status = error?.response?.status
      const data = error?.data
      if (status === 409 && data) {
        const availableQty = typeof data.available_qty === 'number' ? data.available_qty : null
        const isPlanned = !!data.is_planned
        const detail = isPlanned
          ? `Disponível por encomenda: até ${availableQty ?? 'algumas'} unidade(s).`
          : availableQty != null
            ? `Disponível para este pedido: ${availableQty} unidade(s).`
            : operationalCopy.availability.insufficientStock
        lastError.value = detail
        stockIssue.value = stockIssueFromPayload(data, meta)
      } else if (status === 429) {
        const detail = data?.detail || operationalCopy.recovery.cartRateLimit
        lastError.value = detail
        rateLimitRecovery.value = {
          detail,
          retryAfterSeconds: typeof data?.retry_after_seconds === 'number' ? data.retry_after_seconds : null
        }
      } else {
        const toast = useToast()
        lastError.value = 'Não foi possível atualizar o carrinho. Tente novamente.'
        toast.add({
          color: 'error',
          title: 'Algo deu errado',
          description: lastError.value || ''
        })
      }
      throw error
    } finally {
      const next = { ...pendingBySku.value }
      delete next[meta.sku]
      pendingBySku.value = next
    }
  }

  function dismissStockIssue () {
    stockIssue.value = null
  }

  function dismissRateLimitRecovery () {
    rateLimitRecovery.value = null
  }

  async function retryLastCartCommand () {
    const command = lastCartCommand.value
    if (!command) return
    await setSkuQty(command.meta, command.qty)
  }

  async function acceptStockIssueAvailable () {
    const command = lastCartCommand.value
    const availableQty = stockIssue.value?.available_qty
    if (!command || availableQty == null) return
    await setSkuQty(command.meta, availableQty)
  }

  return {
    cart,
    hasPendingMutations,
    lastError,
    stockIssue,
    rateLimitRecovery,
    lastCartCommand,
    setFromServer,
    clearCart,
    qtyForSku,
    isPending,
    setSkuQty,
    dismissStockIssue,
    dismissRateLimitRecovery,
    retryLastCartCommand,
    acceptStockIssueAvailable
  }
}
