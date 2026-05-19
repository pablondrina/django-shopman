import type { OmotenashiProjection, OpeningHoursEntry, PublicConfigProjection, ShopProjection, ShopStatusProjection } from '~/types/shopman'

interface ShopSessionState {
  customerName: string | null
  customerPhone: string | null
  isAuthenticated: boolean
  requiresWelcome: boolean
  welcomeSuggestedName: string | null
  lastOrderRef: string | null
  shop: ShopProjection | null
  shopStatus: ShopStatusProjection | null
  openingHours: OpeningHoursEntry[]
  omotenashi: OmotenashiProjection | null
  publicConfig: PublicConfigProjection | null
}

interface AuthSessionProjection {
  is_authenticated: boolean
  customer_ref?: string
  customer_name?: string
  customer_phone?: string
  customer_email?: string
  requires_welcome?: boolean
  welcome_suggested_name?: string
}

function cleanOptionalText (value: unknown): string | null {
  if (typeof value !== 'string') return null
  const trimmed = value.trim()
  if (!trimmed || trimmed.toLowerCase() === 'null') return null
  return trimmed
}

function emptyState (): ShopSessionState {
  return {
    customerName: null,
    customerPhone: null,
    isAuthenticated: false,
    requiresWelcome: false,
    welcomeSuggestedName: null,
    lastOrderRef: null,
    shop: null,
    shopStatus: null,
    openingHours: [],
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
    opening_hours?: OpeningHoursEntry[]
    last_order_ref: string | null
    public_config?: PublicConfigProjection
  } | null | undefined) {
    if (!home) return
    const homeAuthenticated = home.omotenashi.audience !== 'anon'
    state.value = {
      ...state.value,
      customerName: homeAuthenticated ? cleanOptionalText(home.omotenashi.customer_name) : null,
      customerPhone: homeAuthenticated ? state.value.customerPhone : null,
      isAuthenticated: homeAuthenticated,
      requiresWelcome: homeAuthenticated ? state.value.requiresWelcome : false,
      welcomeSuggestedName: homeAuthenticated ? state.value.welcomeSuggestedName : null,
      lastOrderRef: homeAuthenticated ? home.last_order_ref : null,
      shop: home.shop,
      shopStatus: home.shop_status,
      openingHours: home.opening_hours || [],
      omotenashi: home.omotenashi,
      publicConfig: home.public_config || state.value.publicConfig
    }
  }

  function setFromAuthSession (session: AuthSessionProjection | null | undefined) {
    if (!session) return
    if (!session.is_authenticated) {
      state.value = {
        ...state.value,
        customerName: null,
        customerPhone: null,
        isAuthenticated: false,
        requiresWelcome: false,
        welcomeSuggestedName: null,
        lastOrderRef: null
      }
      return
    }
    state.value = {
      ...state.value,
      customerName: cleanOptionalText(session.customer_name),
      customerPhone: cleanOptionalText(session.customer_phone) || state.value.customerPhone,
      isAuthenticated: true,
      requiresWelcome: !!session.requires_welcome,
      welcomeSuggestedName: cleanOptionalText(session.welcome_suggested_name)
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
  const customerPhone = computed(() => state.value.customerPhone)
  const isAuthenticated = computed(() => state.value.isAuthenticated)
  const requiresWelcome = computed(() => state.value.requiresWelcome)
  const welcomeSuggestedName = computed(() => state.value.welcomeSuggestedName)
  const lastOrderRef = computed(() => state.value.lastOrderRef)
  const shop = computed(() => state.value.shop)
  const shopStatus = computed(() => state.value.shopStatus)
  const openingHours = computed(() => state.value.openingHours)
  const omotenashi = computed(() => state.value.omotenashi)
  const publicConfig = computed(() => state.value.publicConfig)

  return {
    state,
    customerName,
    customerPhone,
    isAuthenticated,
    requiresWelcome,
    welcomeSuggestedName,
    lastOrderRef,
    shop,
    shopStatus,
    openingHours,
    omotenashi,
    publicConfig,
    setFromHome,
    setFromAuthSession,
    setIdentity,
    reset
  }
}
