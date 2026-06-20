import { applySkuQty } from '~/presentation/cart'
import type { CartMutationResponse, CartProjection, ProductMutationMeta, Action } from '~/types/shopman'

interface CartIssue {
  title: string
  detail: string
  error_code: string
  sku: string
  name: string
  requested_qty: number | null
  available_qty: number | null
  is_paused: boolean
  is_planned: boolean
  substitutes: Array<{ sku?: string, name?: string, reason?: string, available_qty?: number, target_qty?: number, can_order?: boolean }>
  actions: Action[]
  items: Array<{
    sku: string
    name: string
    requested_qty: number | null
    available_qty: number | null
    reason: string
  }>
}

interface RateLimitRecovery {
  detail: string
  retryAfterSeconds: number | null
}

interface CartMutationSnapshot {
  meta: ProductMutationMeta
  qty: number
}

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
    delivery_distance_km: null,
    delivery_distance_display: null,
    grand_total_q: 0,
    grand_total_display: 'R$ 0,00',
    coupon_code: null,
    coupon_discount_q: null,
    coupon_discount_display: null,
    has_unavailable_items: false,
    has_awaiting_confirmation_items: false,
    has_ready_for_confirmation_items: false,
    minimum_order_progress: null,
    upsell: null,
    actions: [
      {
        ref: 'checkout',
        kind: 'link',
        label: 'Finalizar pedido',
        priority: 'primary',
        enabled: false,
        reason: 'Carrinho vazio.',
        href: '/finalizar',
        method: '',
        payload_schema: {},
        idempotency: 'none',
        confirmation: {}
      },
      {
        ref: 'continue_shopping',
        kind: 'link',
        label: 'Continuar comprando',
        priority: 'secondary',
        enabled: true,
        reason: '',
        href: '/menu',
        method: '',
        payload_schema: {},
        idempotency: 'none',
        confirmation: {}
      }
    ]
  }
}

function numberOrNull (value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function issueFromPayload (data: any, meta: ProductMutationMeta): CartIssue {
  const fallbackName = String(data?.name || meta.name || data?.sku || meta.sku)
  const rawItems = Array.isArray(data?.items) ? data.items : []
  const firstItemReason = rawItems.map((item: any) => item?.reason).find((reason: unknown) => typeof reason === 'string' && reason.trim())
  const rawDetail = typeof data?.detail === 'string' && !/^insufficient stock\.?$/i.test(data.detail.trim()) ? data.detail : ''
  const fallbackReason = String(firstItemReason || rawDetail || 'Revise a quantidade deste item.')
  const items = rawItems.length
    ? rawItems.map((item: any) => ({
        sku: String(item?.sku || data?.sku || meta.sku),
        name: String(item?.name || fallbackName),
        requested_qty: numberOrNull(item?.requested_qty),
        available_qty: numberOrNull(item?.available_qty),
        reason: String(item?.reason || fallbackReason)
      }))
    : [{
        sku: String(data?.sku || meta.sku),
        name: fallbackName,
        requested_qty: numberOrNull(data?.requested_qty),
        available_qty: numberOrNull(data?.available_qty),
        reason: fallbackReason
      }]

  return {
    title: String(data?.title || 'Revise este item'),
    detail: fallbackReason,
    error_code: String(data?.error_code || 'cart_issue'),
    sku: String(data?.sku || meta.sku),
    name: fallbackName,
    requested_qty: numberOrNull(data?.requested_qty),
    available_qty: numberOrNull(data?.available_qty),
    is_paused: !!data?.is_paused,
    is_planned: !!data?.is_planned,
    substitutes: Array.isArray(data?.substitutes) ? data.substitutes : [],
    actions: Array.isArray(data?.actions) ? data.actions : [],
    items
  }
}

// Fila serial de mutações compartilhada por toda a superfície: toques em rajada
// não se perdem nem chegam fora de ordem no servidor; a fila sobrevive a erros.
let mutationChain: Promise<unknown> = Promise.resolve()
let queueDepth = 0

function enqueueMutation<T> (run: () => Promise<T>): Promise<T> {
  const result = mutationChain.then(run)
  mutationChain = result.then(() => undefined, () => undefined)
  return result
}

export function useCartState () {
  const cart = useState<CartProjection>('storefront-cart', emptyCart)
  const pendingCountBySku = useState<Record<string, number>>('storefront-cart-pending', () => ({}))
  const lastError = useState<string | null>('storefront-cart-error', () => null)
  const cartIssue = useState<CartIssue | null>('storefront-cart-issue', () => null)
  const rateLimitRecovery = useState<RateLimitRecovery | null>('storefront-cart-rate-limit', () => null)
  const lastMutation = useState<CartMutationSnapshot | null>('storefront-cart-last-mutation', () => null)
  const apiPath = useShopmanApiPath()
  const csrfHeaders = useShopmanCsrfHeaders()

  const hasPendingMutations = computed(() => Object.values(pendingCountBySku.value).some(count => count > 0))

  function bumpPending (sku: string) {
    pendingCountBySku.value = { ...pendingCountBySku.value, [sku]: (pendingCountBySku.value[sku] || 0) + 1 }
  }

  function dropPending (sku: string) {
    const next = { ...pendingCountBySku.value }
    const count = (next[sku] || 0) - 1
    if (count > 0) next[sku] = count
    else delete next[sku]
    pendingCountBySku.value = next
  }

  function applyServerCart (next: CartProjection) {
    cart.value = { ...next, summary_pending: false }
    cartIssue.value = null
    rateLimitRecovery.value = null
  }

  function setFromServer (next?: CartProjection | null) {
    if (!next) return
    // Snapshots passivos (shell, projeções de página) não podem atropelar o
    // estado otimista enquanto há mutações em voo; a verdade chega no drain da fila.
    if (queueDepth > 0) return
    applyServerCart(next)
  }

  function clearCart () {
    cart.value = emptyCart()
    cartIssue.value = null
    rateLimitRecovery.value = null
    lastMutation.value = null
  }

  function qtyForSku (sku: string): number {
    return cart.value.items.find(item => item.sku === sku)?.qty || 0
  }

  function isPending (sku: string): boolean {
    return (pendingCountBySku.value[sku] || 0) > 0
  }

  async function refreshCart () {
    const response = await $fetch<{ cart: CartProjection }>(apiPath('/api/v1/storefront/cart/'), {
      credentials: 'include'
    })
    applyServerCart(response.cart)
    return response.cart
  }

  async function setSkuQty (meta: ProductMutationMeta, qty: number): Promise<CartMutationResponse> {
    lastError.value = null
    cartIssue.value = null
    rateLimitRecovery.value = null
    lastMutation.value = { meta: { ...meta }, qty }

    // Otimista: a linha muda na hora; o resumo fica pendente até a verdade do servidor.
    cart.value = applySkuQty(cart.value, meta, qty)
    bumpPending(meta.sku)
    queueDepth += 1

    try {
      const response = await enqueueMutation(async () => $fetch<CartMutationResponse>(apiPath(`/api/v1/cart/skus/${encodeURIComponent(meta.sku)}/`), {
        method: 'PUT',
        headers: await csrfHeaders(),
        body: { qty },
        credentials: 'include'
      }))
      queueDepth -= 1
      dropPending(meta.sku)
      if (queueDepth === 0) {
        // Drain da fila: a última resposta é a verdade mais recente.
        applyServerCart(response.cart)
        lastMutation.value = null
      }
      return response
    } catch (error: any) {
      queueDepth -= 1
      dropPending(meta.sku)
      if (queueDepth === 0) await refreshCart().catch(() => null)
      const status = error?.response?.status
      const data = error?.data
      if (status === 409 && data) {
        cartIssue.value = issueFromPayload(data, meta)
        lastError.value = cartIssue.value.detail
        if (import.meta.client) await navigateTo('/sacola')
      } else if (status === 429) {
        const detail = String(data?.detail || 'Muitas tentativas. Aguarde um instante.')
        rateLimitRecovery.value = {
          detail,
          retryAfterSeconds: typeof data?.retry_after_seconds === 'number' ? data.retry_after_seconds : null
        }
        lastError.value = detail
      } else {
        lastError.value = String(data?.detail || 'Não foi possível atualizar o carrinho.')
      }
      if (import.meta.client) useSonner.error(lastError.value)
      throw error
    }
  }

  async function mutateCoupon (method: 'POST' | 'DELETE', body?: Record<string, unknown>) {
    queueDepth += 1
    try {
      const response = await enqueueMutation(async () => $fetch<{ cart: CartProjection }>(apiPath('/api/v1/cart/coupon/'), {
        method,
        headers: await csrfHeaders(),
        body,
        credentials: 'include'
      }))
      queueDepth -= 1
      if (queueDepth === 0) applyServerCart(response.cart)
      return response.cart
    } catch (error) {
      queueDepth -= 1
      throw error
    }
  }

  async function applyCoupon (coupon_code: string) {
    const nextCart = await mutateCoupon('POST', { code: coupon_code })
    if (import.meta.client) useSonner.success('Cupom aplicado.')
    return nextCart
  }

  async function removeCoupon () {
    const nextCart = await mutateCoupon('DELETE')
    if (import.meta.client) useSonner('Cupom removido.')
    return nextCart
  }

  async function retryLastMutation () {
    const mutation = lastMutation.value
    if (!mutation) return null
    return setSkuQty(mutation.meta, mutation.qty)
  }

  async function acceptAvailableQty () {
    const mutation = lastMutation.value
    const availableQty = cartIssue.value?.available_qty
    if (!mutation || availableQty == null) return null
    return setSkuQty(mutation.meta, availableQty)
  }

  return {
    cart,
    hasPendingMutations,
    pendingCountBySku,
    lastError,
    cartIssue,
    rateLimitRecovery,
    lastMutation,
    setFromServer,
    clearCart,
    refreshCart,
    qtyForSku,
    isPending,
    setSkuQty,
    applyCoupon,
    removeCoupon,
    retryLastMutation,
    acceptAvailableQty
  }
}
