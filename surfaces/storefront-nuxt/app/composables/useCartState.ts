import { applySkuQty, substituteSwapPlan } from '~/presentation/cart'
import type { CartMutationResponse, CartProjection, ProductMutationMeta, Action, SubstituteProjection } from '~/types/shopman'

interface CartIssue {
  title: string
  detail: string
  error_code: string
  sku: string
  name: string
  requested_qty: number | null
  available_qty: number | null
  is_paused: boolean
  // Esgotado honesto e assinável: habilita o CTA "Me avise quando disponível" (WP-3).
  isNotifiable: boolean
  is_planned: boolean
  planned_offer_title: string
  planned_offer_message: string
  shortage_title: string
  paused_title: string
  paused_message: string
  substitutes_intro: string
  substitutes: SubstituteProjection[]
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
    delivery_zone_error: false,
    delivery_distance_km: null,
    delivery_distance_display: null,
    grand_total_q: 0,
    grand_total_display: 'R$ 0,00',
    loyalty_applied: false,
    coupon_code: null,
    coupon_discount_q: null,
    coupon_discount_display: null,
    has_unavailable_items: false,
    has_awaiting_confirmation_items: false,
    has_ready_for_confirmation_items: false,
    unavailable_banner: '',
    awaiting_confirmation_notice: '',
    minimum_order_progress: null,
    delivery_minimum_progress: null,
    free_delivery_progress: null,
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

function normalizeSubstitutes (raw: unknown): SubstituteProjection[] {
  if (!Array.isArray(raw)) return []
  return raw
    .map(asRecord)
    .filter(sub => typeof sub.sku === 'string' && sub.sku)
    .map(sub => ({
      sku: String(sub.sku),
      name: String(sub.name || sub.sku),
      price_q: numberOrNull(sub.price_q) ?? 0,
      price_display: typeof sub.price_display === 'string' ? sub.price_display : null,
      image_url: typeof sub.image_url === 'string' && sub.image_url ? sub.image_url : null,
      available_qty: numberOrNull(sub.available_qty),
      can_order: !!sub.can_order,
      target_qty: numberOrNull(sub.target_qty),
      reason: typeof sub.reason === 'string' && sub.reason ? sub.reason : undefined
    }))
}

function issueFromPayload (data: Record<string, unknown> | null | undefined, meta: ProductMutationMeta): CartIssue {
  const d = asRecord(data)
  const fallbackName = String(d.name || meta.name || d.sku || meta.sku)
  const rawItems = (Array.isArray(d.items) ? d.items : []).map(asRecord)
  const firstItemReason = rawItems.map(item => item.reason).find(reason => typeof reason === 'string' && reason.trim())
  const rawDetail = typeof d.detail === 'string' && !/^insufficient stock\.?$/i.test(d.detail.trim()) ? d.detail : ''
  const fallbackReason = String(firstItemReason || rawDetail || 'Revise a quantidade deste item.')
  const items = rawItems.length
    ? rawItems.map(item => ({
        sku: String(item.sku || d.sku || meta.sku),
        name: String(item.name || fallbackName),
        requested_qty: numberOrNull(item.requested_qty),
        available_qty: numberOrNull(item.available_qty),
        reason: String(item.reason || fallbackReason)
      }))
    : [{
        sku: String(d.sku || meta.sku),
        name: fallbackName,
        requested_qty: numberOrNull(d.requested_qty),
        available_qty: numberOrNull(d.available_qty),
        reason: fallbackReason
      }]

  return {
    title: String(d.title || 'Revise este item'),
    detail: fallbackReason,
    error_code: String(d.error_code || 'cart_issue'),
    sku: String(d.sku || meta.sku),
    name: fallbackName,
    requested_qty: numberOrNull(d.requested_qty),
    available_qty: numberOrNull(d.available_qty),
    is_paused: !!d.is_paused,
    isNotifiable: Boolean(d.is_notifiable),
    is_planned: !!d.is_planned,
    planned_offer_title: String(d.planned_offer_title || ''),
    planned_offer_message: String(d.planned_offer_message || ''),
    shortage_title: String(d.shortage_title || ''),
    paused_title: String(d.paused_title || ''),
    paused_message: String(d.paused_message || ''),
    substitutes_intro: String(d.substitutes_intro || ''),
    substitutes: normalizeSubstitutes(d.substitutes),
    actions: Array.isArray(d.actions) ? (d.actions as Action[]) : [],
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
    const count = (pendingCountBySku.value[sku] || 0) - 1
    pendingCountBySku.value = count > 0
      ? { ...pendingCountBySku.value, [sku]: count }
      : omitKey(pendingCountBySku.value, sku)
  }

  // Atualiza só a projeção do carrinho. NÃO mexe em cartIssue/rateLimitRecovery:
  // esses avisos têm ciclo de vida próprio (limpos por mutação bem-sucedida ou
  // pelo início da próxima mutação), e precisam sobreviver a fetches passivos.
  function setCartProjection (next: CartProjection) {
    cart.value = { ...next, summary_pending: false }
  }

  // Caminho de mutação bem-sucedida: a verdade do servidor chegou e qualquer
  // aviso pendente (issue/rate-limit) está resolvido — pode limpar.
  function applyServerCart (next: CartProjection) {
    setCartProjection(next)
    cartIssue.value = null
    rateLimitRecovery.value = null
  }

  function setFromServer (next?: CartProjection | null) {
    if (!next) return
    // Snapshots passivos (shell, projeções de página) não podem atropelar o
    // estado otimista enquanto há mutações em voo; a verdade chega no drain da fila.
    if (queueDepth > 0) return
    // PRESERVA cartIssue: um 409 (ex.: adicionar item esgotado pelo menu/PDP)
    // navega pra /sacola, e é justamente o fetch desta página que chegaria aqui.
    // Se limpasse o aviso, o cliente cairia numa sacola vazia muda — sem os
    // substitutos. O banner só some quando uma mutação de fato dá certo.
    setCartProjection(next)
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
    // Reconciliação passiva (revert do otimista no catch, poll de holds): preserva
    // cartIssue para o banner de substitutos não sumir enquanto o cliente decide.
    setCartProjection(response.cart)
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
      const response = await enqueueMutation(async () => retryWithBackoff(async () => $fetch<CartMutationResponse>(apiPath(`/api/v1/cart/skus/${encodeURIComponent(meta.sku)}/`), {
        method: 'PUT',
        headers: await csrfHeaders(),
        body: { qty },
        credentials: 'include'
      })))
      queueDepth -= 1
      dropPending(meta.sku)
      if (queueDepth === 0) {
        // Drain da fila: a última resposta é a verdade mais recente.
        applyServerCart(response.cart)
        lastMutation.value = null
      }
      return response
    } catch (error: unknown) {
      queueDepth -= 1
      dropPending(meta.sku)
      if (queueDepth === 0) await refreshCart().catch(() => null)
      const { status, data } = httpError(error)
      if (status === 409 && data) {
        // Não navega, e NÃO dispara toast: o SubstituteSheet global sobe no lugar
        // (menu/PDP/sacola) e já comunica tudo — um toast sobreposto atrapalhava.
        cartIssue.value = issueFromPayload(data, meta)
        lastError.value = cartIssue.value.detail
      } else if (status === 429) {
        // Sem toast: o banner de rate-limit (com countdown) é a UI dedicada.
        const detail = String(data?.detail || 'Muitas tentativas. Aguarde um instante.')
        rateLimitRecovery.value = {
          detail,
          retryAfterSeconds: typeof data?.retry_after_seconds === 'number' ? data.retry_after_seconds : null
        }
        lastError.value = detail
      } else {
        // Erro genérico não tem UI própria → o toast é a única forma de avisar.
        lastError.value = String(data?.detail || 'Não foi possível atualizar o carrinho.')
        if (import.meta.client) useSonner.error(lastError.value)
      }
      throw error
    }
  }

  async function mutateCoupon (method: 'POST' | 'DELETE', body?: Record<string, unknown>) {
    queueDepth += 1
    try {
      const response = await enqueueMutation(async () => retryWithBackoff(async () => $fetch<{ cart: CartProjection }>(apiPath('/api/v1/cart/coupon/'), {
        method,
        headers: await csrfHeaders(),
        body,
        credentials: 'include'
      })))
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

  function dismissCartIssue () {
    cartIssue.value = null
  }

  // Swap em 1 toque: troca o item que faltou por uma alternativa em estoque.
  // Reusa setSkuQty (otimista + fila + 409/429); no sucesso, applyServerCart
  // zera cartIssue e o banner some sozinho.
  async function addSubstitute (sub: SubstituteProjection) {
    const plan = substituteSwapPlan(sub, cartIssue.value?.requested_qty ?? null)
    if (!plan) return null
    const res = await setSkuQty(plan.meta, plan.qty)
    if (import.meta.client) useSonner.success(`Adicionamos ${sub.name} à sua sacola.`)
    return res
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
    acceptAvailableQty,
    addSubstitute,
    dismissCartIssue
  }
}
