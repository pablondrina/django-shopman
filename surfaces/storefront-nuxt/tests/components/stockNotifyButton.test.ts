// StockNotifyButton (WP-S6): estado confirmado persiste da projeção; logado assina
// em 1 clique (telefone da conta); a confirmação vira estado calmo e desabilitado.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { nextTick } from 'vue'
import { mountSuspended, mockNuxtImport } from '@nuxt/test-utils/runtime'
import StockNotifyButton from '~/components/StockNotifyButton.vue'

mockNuxtImport('useSonner', () => {
  const fn: any = () => {}
  fn.success = () => {}
  fn.error = () => {}
  return () => fn
})

async function setAuthenticated (value: boolean) {
  const { useShopSession } = await import('~/composables/useShopSession')
  const s = useShopSession()
  s.reset()
  if (value) s.setFromAuthSession({ is_authenticated: true, customer_name: 'Ana', customer_phone: '43999' })
}

describe('StockNotifyButton', () => {
  beforeEach(() => {
    document.cookie = 'csrftoken=testtoken'
    vi.unstubAllGlobals()
  })

  it('shows the calm confirmed state when already subscribed', async () => {
    await setAuthenticated(true)
    vi.stubGlobal('$fetch', vi.fn())
    const wrapper = await mountSuspended(StockNotifyButton, {
      props: { sku: 'PAO', name: 'Pão', subscribed: true }
    })
    expect(wrapper.text()).toContain('Avisaremos você')
    expect(wrapper.get('button').attributes('disabled')).toBeDefined()
  })

  it('authenticated one-click subscribe hits the notify endpoint and confirms', async () => {
    await setAuthenticated(true)
    const $fetch = vi.fn().mockResolvedValue({})
    vi.stubGlobal('$fetch', $fetch)
    const wrapper = await mountSuspended(StockNotifyButton, {
      props: { sku: 'PAO', name: 'Pão', subscribed: false }
    })

    await wrapper.get('button').trigger('click')
    await new Promise(r => setTimeout(r, 0))
    await nextTick()

    expect($fetch).toHaveBeenCalledOnce()
    expect($fetch.mock.calls[0]?.[0]).toContain('/availability/PAO/notify/')
    expect(wrapper.text()).toContain('Avisaremos você') // virou estado confirmado
  })

  it('renders the notify affordance with an accessible label when not subscribed', async () => {
    await setAuthenticated(true)
    vi.stubGlobal('$fetch', vi.fn())
    const wrapper = await mountSuspended(StockNotifyButton, {
      props: { sku: 'PAO', name: 'Pão', pill: true, subscribed: false }
    })
    expect(wrapper.get('button').attributes('aria-label')).toBe('Avise quando Pão voltar')
  })
})
