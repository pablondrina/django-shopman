import type { CartProjection, SurfaceActionProjection } from '~/types/shopman'

interface ReorderConflict {
  orderRef: string
  href: string
  method: string
  items: Array<{ sku: string, name: string, qty: number }>
  actions: SurfaceActionProjection[]
}

interface ReorderSkippedItem {
  sku?: string
  name: string
  reason: string
}

interface ReorderRateLimitRecovery {
  detail: string
  retryAfterSeconds: number | null
  orderRef: string
  href: string
  method: string
  mode?: 'replace' | 'append'
  idempotencyKey: string
}

interface ReorderResponse {
  ok: true
  skipped: string[]
  skipped_items?: ReorderSkippedItem[]
  cart: CartProjection
}

const conflictState = () => useState<ReorderConflict | null>('shopman-reorder-conflict', () => null)
const skippedState = () => useState<ReorderSkippedItem[]>('shopman-reorder-skipped-items', () => [])
const rateLimitState = () => useState<ReorderRateLimitRecovery | null>('shopman-reorder-rate-limit-recovery', () => null)

function skippedDescription (skipped: string[]) {
  if (!skipped.length) return ''
  const visible = skipped.slice(0, 3).join(', ')
  const suffix = skipped.length > 3 ? ` e mais ${skipped.length - 3}` : ''
  return `Ficaram fora desta vez: ${visible}${suffix}.`
}

export function useReorder () {
  const apiPath = useShopmanApiPath()
  const csrfHeaders = useShopmanCsrfHeaders()
  const { setFromServer } = useCartState()
  const conflict = conflictState()
  const skippedItems = skippedState()
  const rateLimitRecovery = rateLimitState()
  const pending = useState<boolean>('shopman-reorder-pending', () => false)
  const toast = useToast()

  function normalizeSkippedItems (response: ReorderResponse): ReorderSkippedItem[] {
    if (Array.isArray(response.skipped_items) && response.skipped_items.length) {
      return response.skipped_items.map(item => ({
        sku: item.sku,
        name: item.name,
        reason: item.reason || operationalCopy.availability.unavailableForReorder
      }))
    }
    return (response.skipped || []).map(name => ({
      name,
      reason: operationalCopy.availability.unavailableForReorder
    }))
  }

  async function performReorder (
    orderRef: string,
    mode?: 'replace' | 'append',
    idempotencyKey = newRemoteMutationKey(`web-reorder-${orderRef}`),
    action?: SurfaceActionProjection | null
  ): Promise<boolean> {
    pending.value = true
    rateLimitRecovery.value = null
    const href = action?.href || `/api/v1/orders/${encodeURIComponent(orderRef)}/reorder/`
    const method = action?.method || 'POST'
    try {
      const response = await $fetch<ReorderResponse>(apiPath(href), {
        method,
        headers: { ...(await csrfHeaders()), 'Idempotency-Key': idempotencyKey },
        body: mode ? { mode, idempotency_key: idempotencyKey } : { idempotency_key: idempotencyKey },
        credentials: 'include'
      })
      setFromServer(response.cart)
      conflict.value = null
      skippedItems.value = normalizeSkippedItems(response)
      const skipped = response.skipped || []
      if (skipped.length) {
        toast.add({
          icon: 'i-lucide-info',
          color: 'info',
          title: 'Pedido recriado, com ajustes',
          description: skippedDescription(skipped)
        })
      } else {
        toast.add({
          icon: 'i-lucide-circle-check',
          color: 'success',
          title: 'Pedido recriado',
          description: 'Os itens disponíveis do pedido anterior foram adicionados ao carrinho.'
        })
      }
      await navigateTo('/cart')
      return true
    } catch (err: any) {
      const status = err?.response?.status
      const data = err?.data
      if (status === 409 && data?.error_code === 'cart_not_empty') {
        conflict.value = {
          orderRef: data.order_ref || orderRef,
          href,
          method,
          items: Array.isArray(data.items) ? data.items : [],
          actions: Array.isArray(data.actions) ? data.actions : []
        }
        return false
      }
      if (status === 429 || data?.error_code === 'rate_limited') {
        rateLimitRecovery.value = {
          detail: data?.detail || operationalCopy.recovery.reorderRateLimit,
          retryAfterSeconds: typeof data?.retry_after_seconds === 'number' ? data.retry_after_seconds : null,
          orderRef,
          href,
          method,
          mode,
          idempotencyKey
        }
        return false
      }
      toast.add({
        icon: 'i-lucide-circle-x',
        color: 'error',
        title: 'Não foi possível repetir o pedido',
        description: data?.detail || ''
      })
      return false
    } finally {
      pending.value = false
    }
  }

  async function performReorderAction (
    action: SurfaceActionProjection,
    orderRef: string,
    mode?: 'replace' | 'append'
  ): Promise<boolean> {
    return await performReorder(orderRef, mode, undefined, action)
  }

  function dismissConflict () {
    conflict.value = null
  }

  function dismissSkippedItems () {
    skippedItems.value = []
  }

  function dismissRateLimitRecovery () {
    rateLimitRecovery.value = null
  }

  async function resolveConflict (mode: 'replace' | 'append') {
    if (!conflict.value) return
    const action = conflict.value.actions.find(candidate => candidate.ref === `reorder_${mode}` && candidate.enabled !== false)
    await performReorder(
      conflict.value.orderRef,
      mode,
      undefined,
      action || {
        ref: `reorder_${mode}`,
        kind: 'mutation',
        label: mode === 'replace' ? 'Substituir o carrinho' : 'Adicionar ao carrinho atual',
        priority: mode === 'replace' ? 'danger' : 'secondary',
        enabled: true,
        reason: '',
        href: conflict.value.href,
        method: conflict.value.method,
        payload_schema: {},
        idempotency: 'required',
        confirmation: {}
      }
    )
  }

  async function retryRateLimitedReorder () {
    const recovery = rateLimitRecovery.value
    if (!recovery) return
    rateLimitRecovery.value = null
    await performReorder(
      recovery.orderRef,
      recovery.mode,
      recovery.idempotencyKey,
      {
        ref: 'reorder_retry',
        kind: 'mutation',
        label: 'Tentar novamente',
        priority: 'primary',
        enabled: true,
        reason: '',
        href: recovery.href,
        method: recovery.method,
        payload_schema: {},
        idempotency: 'required',
        confirmation: {}
      }
    )
  }

  return {
    performReorder,
    performReorderAction,
    dismissConflict,
    dismissSkippedItems,
    dismissRateLimitRecovery,
    resolveConflict,
    retryRateLimitedReorder,
    conflict,
    skippedItems,
    rateLimitRecovery,
    pending
  }
}
