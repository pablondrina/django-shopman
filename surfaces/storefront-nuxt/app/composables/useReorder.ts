import type { CartProjection, ReorderConflictProjection, Action } from '~/types/shopman'

export function useReorder () {
  const apiPath = useShopmanApiPath()
  const csrfHeaders = useShopmanCsrfHeaders()
  const { setFromServer } = useCartState()
  const pending = useState<Record<string, boolean>>('storefront-reorder-pending', () => ({}))
  const conflict = useState<ReorderConflictProjection | null>('storefront-reorder-conflict', () => null)

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
      if (import.meta.client) useSonner.success('Itens adicionados ao carrinho.')
      if (import.meta.client) await navigateTo('/sacola')
      conflict.value = null
      return response
    } catch (e) {
      const { status, data } = httpError(e)
      if (status === 409 && data) {
        conflict.value = data as unknown as ReorderConflictProjection
      } else if (import.meta.client) {
        useSonner.error(errorDetail(e, 'Não foi possível refazer este pedido.'))
      }
      throw e
    } finally {
      pending.value = omitKey(pending.value, orderRef)
    }
  }

  function orderRefFromAction (action: Action): string {
    const match = action.href.match(/\/orders\/([^/]+)\/reorder\/?/)
    return match?.[1] || ''
  }

  async function performAction (action: Action, mode: 'append' | 'replace' = 'append') {
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
