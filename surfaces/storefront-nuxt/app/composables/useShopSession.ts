import type { OmotenashiProjection, PublicConfigProjection, ShopProjection, ShopStatusProjection } from '~/types/shopman'

interface ShopSessionState {
  customerName: string | null
  customerPhone: string | null
  isAuthenticated: boolean
  lastOrderRef: string | null
  shop: ShopProjection | null
  shopStatus: ShopStatusProjection | null
  omotenashi: OmotenashiProjection | null
  publicConfig: PublicConfigProjection | null
}

function emptyState (): ShopSessionState {
  return {
    customerName: null,
    customerPhone: null,
    isAuthenticated: false,
    lastOrderRef: null,
    shop: null,
    shopStatus: null,
    omotenashi: null,
    publicConfig: null
  }
}

export function useShopSession () {
  const state = useState<ShopSessionState>('shopman-session', emptyState)

  function setFromHome (home: {
    omotenashi: OmotenashiProjection
    shop: ShopProjection
    shop_status: ShopStatusProjection
    last_order_ref: string | null
    public_config?: PublicConfigProjection
  } | null | undefined) {
    if (!home) return
    state.value = {
      ...state.value,
      customerName: home.omotenashi.customer_name,
      isAuthenticated: home.omotenashi.audience !== 'anon',
      lastOrderRef: home.last_order_ref,
      shop: home.shop,
      shopStatus: home.shop_status,
      omotenashi: home.omotenashi,
      publicConfig: home.public_config || state.value.publicConfig
    }
  }

  function setIdentity (next: { name?: string | null, phone?: string | null, isAuthenticated?: boolean }) {
    state.value = {
      ...state.value,
      customerName: next.name ?? state.value.customerName,
      customerPhone: next.phone ?? state.value.customerPhone,
      isAuthenticated: next.isAuthenticated ?? state.value.isAuthenticated
    }
  }

  function reset () {
    state.value = emptyState()
  }

  const customerName = computed(() => state.value.customerName)
  const isAuthenticated = computed(() => state.value.isAuthenticated)
  const lastOrderRef = computed(() => state.value.lastOrderRef)
  const shop = computed(() => state.value.shop)
  const shopStatus = computed(() => state.value.shopStatus)
  const omotenashi = computed(() => state.value.omotenashi)
  const publicConfig = computed(() => state.value.publicConfig)

  return {
    state,
    customerName,
    isAuthenticated,
    lastOrderRef,
    shop,
    shopStatus,
    omotenashi,
    publicConfig,
    setFromHome,
    setIdentity,
    reset
  }
}
