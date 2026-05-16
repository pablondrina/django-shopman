import type { CartProjection, ReorderConflictProjection, SurfaceActionProjection } from '~/types/shopman'

export function useReorder () {
  const apiPath = useShopmanApiPath()
  const csrfHeaders = useShopmanCsrfHeaders()
  const { setFromServer, drawerOpen } = useCartState()
  const pending = useState<Record<string, boolean>>('shopman-thing-reorder-pending', () => ({}))
  const conflict = useState<ReorderConflictProjection | null>('shopman-thing-reorder-conflict', () => null)

  async function submit (orderRef: string, mode: 'append' | 'replace' = 'append') {
    pending.value = { ...pending.value, [orderRef]: true }
    try {
      const response = await $fetch<{ ok?: true, cart?: CartProjection }>(apiPath(`/api/v1/orders/${encodeURIComponent(orderRef)}/reorder/`), {
        method: 'POST',
        headers: {
          ...(await csrfHeaders()),
          'x-idempotency-key': newRemoteMutationKey(`reorder-${mode}`)
        },
        credentials: 'include',
        body: { mode }
      })
      if (response.cart) setFromServer(response.cart)
      drawerOpen.value = true
      if (import.meta.client) useSonner.success('Itens adicionados ao carrinho.')
      conflict.value = null
      return response
    } catch (e: any) {
      if (e?.response?.status === 409 && e?.data) {
        conflict.value = e.data as ReorderConflictProjection
      } else if (import.meta.client) {
        useSonner.error(e?.data?.detail || 'Nao foi possivel refazer este pedido.')
      }
      throw e
    } finally {
      const next = { ...pending.value }
      delete next[orderRef]
      pending.value = next
    }
  }

  function orderRefFromAction (action: SurfaceActionProjection): string {
    const match = action.href.match(/\/orders\/([^/]+)\/reorder\/?/)
    return match?.[1] || ''
  }

  async function performAction (action: SurfaceActionProjection, mode: 'append' | 'replace' = 'append') {
    const orderRef = orderRefFromAction(action)
    if (!orderRef) return null
    return submit(orderRef, mode)
  }

  return {
    pending,
    conflict,
    submit,
    performAction
  }
}
