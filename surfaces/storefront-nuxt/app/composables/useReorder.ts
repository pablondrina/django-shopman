import type { CartProjection } from '~/types/shopman'

interface ReorderConflict {
  orderRef: string
  items: Array<{ sku: string, name: string, qty: number }>
}

interface ReorderResponse {
  ok: true
  skipped: string[]
  cart: CartProjection
}

const conflictState = () => useState<ReorderConflict | null>('shopman-reorder-conflict', () => null)

export function useReorder () {
  const apiPath = useShopmanApiPath()
  const { setFromServer } = useCartState()
  const conflict = conflictState()
  const pending = useState<boolean>('shopman-reorder-pending', () => false)
  const toast = useToast()

  async function performReorder (orderRef: string, mode?: 'replace' | 'append'): Promise<boolean> {
    pending.value = true
    try {
      const response = await $fetch<ReorderResponse>(apiPath(`/api/v1/orders/${encodeURIComponent(orderRef)}/reorder/`), {
        method: 'POST',
        body: mode ? { mode } : {},
        credentials: 'include'
      })
      setFromServer(response.cart)
      conflict.value = null
      const skipped = response.skipped || []
      if (skipped.length) {
        toast.add({
          icon: 'i-lucide-info',
          color: 'info',
          title: 'Pedido recriado, com ajustes',
          description: `${skipped.length} item(ns) ficaram fora desta vez.`
        })
      } else {
        toast.add({
          icon: 'i-lucide-circle-check',
          color: 'success',
          title: 'Pedido recriado',
          description: 'Tudo do seu último pedido voltou pro carrinho.'
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
          items: Array.isArray(data.items) ? data.items : []
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

  function dismissConflict () {
    conflict.value = null
  }

  async function resolveConflict (mode: 'replace' | 'append') {
    if (!conflict.value) return
    await performReorder(conflict.value.orderRef, mode)
  }

  return { performReorder, dismissConflict, resolveConflict, conflict, pending }
}
