import type { POSCartItem, POSProductProjection, POSTabPayload, POSTabProjection } from '~/types/backstage'

interface PosCustomer {
  ref: string
  name: string
  phone: string
  loyalty_group: string
  is_staff: boolean
}

interface PosCartState {
  tabCode: string
  tabDisplay: string
  sessionKey: string
  items: POSCartItem[]
  customerPhone: string
  customer: PosCustomer | null
}

const empty = (): PosCartState => ({
  tabCode: '',
  tabDisplay: '',
  sessionKey: '',
  items: [],
  customerPhone: '',
  customer: null
})

const formatBRL = (centavos: number): string => {
  return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(centavos / 100)
}

export function usePosCart () {
  const state = useState<PosCartState>('pos-cart', empty)
  const action = useBackstageAction()
  const apiPath = useBackstageApiPath()
  const toast = useToast()
  const saving = ref(false)
  const closing = ref(false)

  const isOpen = computed(() => !!state.value.sessionKey)
  const totalQ = computed(() => state.value.items.reduce((s, i) => s + i.price_q * i.qty, 0))
  const totalDisplay = computed(() => formatBRL(totalQ.value))
  const itemCount = computed(() => state.value.items.reduce((s, i) => s + i.qty, 0))

  function reset () {
    state.value = empty()
  }

  function setFromTabPayload (payload: POSTabPayload) {
    state.value = {
      tabCode: payload.tab_code,
      tabDisplay: payload.tab_display,
      sessionKey: payload.session_key,
      items: (payload.items || []).map(i => ({ ...i }))
    }
  }

  async function openTab (tab: POSTabProjection): Promise<boolean> {
    const payload = await action.call<POSTabPayload>(`/api/v1/backstage/pos/tabs/${encodeURIComponent(tab.code)}/open/`, {})
    if (!payload) return false
    setFromTabPayload(payload)
    return true
  }

  function addProduct (product: POSProductProjection) {
    const existing = state.value.items.find(i => i.sku === product.sku)
    if (existing) {
      existing.qty += 1
    } else {
      state.value.items.push({
        sku: product.sku,
        name: product.name,
        price_q: product.price_q,
        qty: 1,
        notes: '',
        is_d1: product.is_d1
      })
    }
    toast.add({
      icon: 'i-lucide-plus-circle',
      color: 'success',
      title: product.name,
      description: `+1 · ${formatBRL(product.price_q)}`,
      duration: 1500
    })
  }

  function setQty (sku: string, qty: number) {
    const item = state.value.items.find(i => i.sku === sku)
    if (!item) return
    if (qty <= 0) {
      state.value.items = state.value.items.filter(i => i.sku !== sku)
    } else {
      item.qty = qty
    }
  }

  function removeItem (sku: string) {
    state.value.items = state.value.items.filter(i => i.sku !== sku)
  }

  // Django's build_session_ops expects `unit_price_q`, but the read payload
  // returns `price_q`. Translate when sending so save/close work correctly.
  function itemsForServer () {
    return state.value.items.map(i => ({
      sku: i.sku,
      name: i.name,
      qty: i.qty,
      unit_price_q: i.price_q,
      notes: i.notes,
      is_d1: i.is_d1
    }))
  }

  function customerPayload () {
    const c = state.value.customer
    return c
      ? { customer_name: c.name, customer_phone: c.phone }
      : state.value.customerPhone
        ? { customer_phone: state.value.customerPhone.replace(/\D/g, '') }
        : {}
  }

  async function save (): Promise<boolean> {
    if (!isOpen.value) return false
    saving.value = true
    try {
      const result = await action.call<{ ok: boolean, tab_code: string, tab_display: string, session_key: string }>(
        '/api/v1/backstage/pos/tabs/save/',
        {
          body: {
            tab_code: state.value.tabCode,
            tab_session_key: state.value.sessionKey,
            items: itemsForServer(),
            ...customerPayload()
          },
          successTitle: `Comanda #${state.value.tabDisplay} salva`
        }
      )
      return result?.ok === true
    } finally {
      saving.value = false
    }
  }

  async function closeSale (paymentMethod: string): Promise<{ orderRef?: string } | null> {
    if (!isOpen.value || !state.value.items.length) return null
    closing.value = true
    try {
      const result = await action.call<{ ok: boolean, order_ref?: string, tab_code?: string }>(
        '/api/v1/backstage/pos/sale/close/',
        {
          body: {
            tab_code: state.value.tabCode,
            tab_session_key: state.value.sessionKey,
            items: itemsForServer(),
            payment_method: paymentMethod,
            ...customerPayload()
          },
          successTitle: 'Pedido criado'
        }
      )
      if (result?.ok) {
        const orderRef = result.order_ref
        reset()
        return { orderRef }
      }
      return null
    } finally {
      closing.value = false
    }
  }

  async function clearTab (): Promise<boolean> {
    if (!state.value.sessionKey) return false
    const ok = await action.call(`/api/v1/backstage/pos/tabs/${encodeURIComponent(state.value.sessionKey)}/clear/`, {
      method: 'DELETE',
      successTitle: 'Comanda liberada'
    })
    if (ok) reset()
    return ok !== null
  }

  async function createTab (tabCode: string, label = ''): Promise<boolean> {
    const result = await action.call('/api/v1/backstage/pos/tabs/', {
      body: { tab_code: tabCode, label },
      successTitle: `Comanda #${tabCode} cadastrada`
    })
    return result !== null
  }

  const lookingUpCustomer = ref(false)

  async function lookupCustomer (phone: string): Promise<PosCustomer | null> {
    const cleaned = phone.replace(/\D/g, '')
    state.value.customerPhone = phone
    if (cleaned.length < 10) {
      state.value.customer = null
      return null
    }
    lookingUpCustomer.value = true
    try {
      const result = await $fetch<{ customer: PosCustomer | null }>(
        apiPath('/api/v1/backstage/pos/customer/lookup/'),
        { credentials: 'include', query: { phone: cleaned } }
      )
      state.value.customer = result?.customer || null
      return state.value.customer
    } catch {
      state.value.customer = null
      return null
    } finally {
      lookingUpCustomer.value = false
    }
  }

  function clearCustomer () {
    state.value.customer = null
    state.value.customerPhone = ''
  }

  return {
    state,
    isOpen,
    totalQ,
    totalDisplay,
    itemCount,
    saving,
    closing,
    lookingUpCustomer,
    reset,
    openTab,
    addProduct,
    setQty,
    removeItem,
    save,
    closeSale,
    clearTab,
    createTab,
    lookupCustomer,
    clearCustomer
  }
}
