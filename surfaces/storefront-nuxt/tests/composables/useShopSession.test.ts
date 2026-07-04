// Máquina de estado da sessão do cliente (WP-S1): hidratação por home/auth,
// higienização de texto opcional ("null"/vazio → null) e reset. Sem rede.
import { describe, it, expect, beforeEach } from 'vitest'

async function loadSession () {
  const { useShopSession } = await import('~/composables/useShopSession')
  const s = useShopSession()
  s.reset()
  return s
}

function home (authenticated: boolean) {
  return {
    omotenashi: { audience: authenticated ? 'known' : 'anon', customer_name: authenticated ? 'Ana' : null },
    shop: { name: 'Nelson' },
    shop_status: { is_open: true },
    notices: [{ id: 1 }],
    opening_hours: [{ label: 'seg', hours: '8-18' }],
    last_order_ref: authenticated ? 'ORD-1' : null,
    public_config: { whatsapp_url: 'https://wa.me/1' }
  } as never
}

describe('useShopSession', () => {
  beforeEach(async () => { await loadSession() })

  it('hydrates an authenticated customer from home', async () => {
    const s = await loadSession()
    s.setFromHome(home(true))
    expect(s.isAuthenticated.value).toBe(true)
    expect(s.customerName.value).toBe('Ana')
    expect(s.lastOrderRef.value).toBe('ORD-1')
    expect(s.homeNotices.value).toHaveLength(1)
    expect(s.publicConfig.value?.whatsapp_url).toBe('https://wa.me/1')
  })

  it('anon home clears identity but keeps shop metadata', async () => {
    const s = await loadSession()
    s.setFromHome(home(false))
    expect(s.isAuthenticated.value).toBe(false)
    expect(s.customerName.value).toBeNull()
    expect(s.lastOrderRef.value).toBeNull()
    expect(s.shop.value?.name).toBe('Nelson')
  })

  it('sanitizes the literal string "null" to a real null name', async () => {
    const s = await loadSession()
    s.setFromAuthSession({ is_authenticated: true, customer_name: 'null', customer_phone: '  ' })
    expect(s.customerName.value).toBeNull()
    expect(s.customerPhone.value).toBeNull()
  })

  it('setFromAuthSession with is_authenticated=false wipes the session', async () => {
    const s = await loadSession()
    s.setFromAuthSession({ is_authenticated: true, customer_name: 'Bruno', customer_phone: '43999' })
    expect(s.isAuthenticated.value).toBe(true)
    s.setFromAuthSession({ is_authenticated: false })
    expect(s.isAuthenticated.value).toBe(false)
    expect(s.customerName.value).toBeNull()
    expect(s.customerPhone.value).toBeNull()
  })

  it('setIdentity patches only provided fields', async () => {
    const s = await loadSession()
    s.setFromAuthSession({ is_authenticated: true, customer_name: 'Bruno', customer_phone: '43999' })
    s.setIdentity({ name: 'Bruna' })
    expect(s.customerName.value).toBe('Bruna')
    expect(s.customerPhone.value).toBe('43999') // preservado
  })

  it('requires_welcome flows through and reset clears everything', async () => {
    const s = await loadSession()
    s.setFromAuthSession({ is_authenticated: true, requires_welcome: true, welcome_suggested_name: 'Ana' })
    expect(s.requiresWelcome.value).toBe(true)
    expect(s.welcomeSuggestedName.value).toBe('Ana')
    s.reset()
    expect(s.requiresWelcome.value).toBe(false)
    expect(s.isAuthenticated.value).toBe(false)
  })
})
