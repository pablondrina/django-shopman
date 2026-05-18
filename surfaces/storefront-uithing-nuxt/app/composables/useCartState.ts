import type { CartMutationResponse, CartProjection, ProductMutationMeta, SurfaceActionProjection } from '~/types/shopman'

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
  actions: SurfaceActionProjection[]
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

export function useCartState () {
  const cart = useState<CartProjection>('shopman-thing-cart', emptyCart)
  const pendingBySku = useState<Record<string, boolean>>('shopman-thing-cart-pending', () => ({}))
  const lastError = useState<string | null>('shopman-thing-cart-error', () => null)
  const cartIssue = useState<CartIssue | null>('shopman-thing-cart-issue', () => null)
  const rateLimitRecovery = useState<RateLimitRecovery | null>('shopman-thing-cart-rate-limit', () => null)
  const lastMutation = useState<CartMutationSnapshot | null>('shopman-thing-cart-last-mutation', () => null)
  const drawerOpen = useState<boolean>('shopman-thing-cart-drawer', () => false)
  const apiPath = useShopmanApiPath()
  const csrfHeaders = useShopmanCsrfHeaders()

  const hasPendingMutations = computed(() => Object.values(pendingBySku.value).some(Boolean))

  function setFromServer (next?: CartProjection | null) {
    if (!next) return
    cart.value = { ...next, summary_pending: false }
    cartIssue.value = null
    rateLimitRecovery.value = null
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
    return !!pendingBySku.value[sku]
  }

  async function refreshCart () {
    const response = await $fetch<{ cart: CartProjection }>(apiPath('/api/v1/storefront/cart/'), {
      credentials: 'include'
    })
    setFromServer(response.cart)
    return response.cart
  }

  async function setSkuQty (meta: ProductMutationMeta, qty: number): Promise<CartMutationResponse> {
    lastError.value = null
    cartIssue.value = null
    rateLimitRecovery.value = null
    lastMutation.value = { meta: { ...meta }, qty }
    pendingBySku.value = { ...pendingBySku.value, [meta.sku]: true }
    cart.value = { ...cart.value, summary_pending: true }

    try {
      const response = await $fetch<CartMutationResponse>(apiPath(`/api/v1/cart/skus/${encodeURIComponent(meta.sku)}/`), {
        method: 'PUT',
        headers: await csrfHeaders(),
        body: { qty },
        credentials: 'include'
      })
      setFromServer(response.cart)
      lastMutation.value = null
      if (import.meta.client) {
        if (qty > 0) drawerOpen.value = true
        useSonner(qty > 0 ? `${meta.name} atualizado no carrinho.` : `${meta.name} removido do carrinho.`)
      }
      return response
    } catch (error: any) {
      await refreshCart().catch(() => null)
      const status = error?.response?.status
      const data = error?.data
      if (status === 409 && data) {
        cartIssue.value = issueFromPayload(data, meta)
        lastError.value = cartIssue.value.detail
        drawerOpen.value = true
      } else if (status === 429) {
        const detail = String(data?.detail || 'Muitas tentativas. Aguarde um instante.')
        rateLimitRecovery.value = {
          detail,
          retryAfterSeconds: typeof data?.retry_after_seconds === 'number' ? data.retry_after_seconds : null
        }
        lastError.value = detail
      } else {
        lastError.value = String(data?.detail || 'Nao foi possivel atualizar o carrinho.')
      }
      if (import.meta.client) useSonner.error(lastError.value)
      throw error
    } finally {
      const next = { ...pendingBySku.value }
      delete next[meta.sku]
      pendingBySku.value = next
    }
  }

  async function applyCoupon (coupon_code: string) {
    const response = await $fetch<{ cart: CartProjection }>(apiPath('/api/v1/cart/coupon/'), {
      method: 'POST',
      headers: await csrfHeaders(),
      body: { coupon_code },
      credentials: 'include'
    })
    setFromServer(response.cart)
    if (import.meta.client) useSonner.success('Cupom aplicado.')
    return response.cart
  }

  async function removeCoupon () {
    const response = await $fetch<{ cart: CartProjection }>(apiPath('/api/v1/cart/coupon/'), {
      method: 'DELETE',
      headers: await csrfHeaders(),
      credentials: 'include'
    })
    setFromServer(response.cart)
    if (import.meta.client) useSonner('Cupom removido.')
    return response.cart
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
    drawerOpen,
    hasPendingMutations,
    pendingBySku,
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
