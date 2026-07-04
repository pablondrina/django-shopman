// Sinal offline (WP-S3): o banner aparece só quando offline, e watchConnectivity
// dispara a reconciliação ao reconectar (queda → volta). VueUse seta o estado
// direto nos eventos window online/offline → dirigível no happy-dom.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { defineComponent, nextTick, h } from 'vue'
import { mountSuspended } from '@nuxt/test-utils/runtime'
import OfflineBanner from '~/components/OfflineBanner.vue'

async function setOnlineState (value: boolean) {
  const { useConnectivity } = await import('~/composables/useConnectivity')
  useConnectivity().isOnline.value = value
}

describe('OfflineBanner', () => {
  beforeEach(async () => { await setOnlineState(true) })

  it('stays hidden while online', async () => {
    const wrapper = await mountSuspended(OfflineBanner)
    expect(wrapper.find('[data-testid="offline-banner"]').exists()).toBe(false)
  })

  it('appears with a calm status message when offline', async () => {
    await setOnlineState(false)
    const wrapper = await mountSuspended(OfflineBanner)
    await nextTick()
    const banner = wrapper.find('[data-testid="offline-banner"]')
    expect(banner.exists()).toBe(true)
    expect(banner.attributes('role')).toBe('status')
    expect(banner.attributes('aria-live')).toBe('polite')
    expect(wrapper.text()).toContain('Sem conexão')
  })
})

describe('useConnectivity.watchConnectivity', () => {
  it('reconciles on reconnect (offline → online) and tracks isOnline', async () => {
    const onReconnect = vi.fn()
    const { useConnectivity } = await import('~/composables/useConnectivity')

    const Harness = defineComponent({
      setup () {
        const conn = useConnectivity()
        conn.watchConnectivity(onReconnect)
        return () => h('div', conn.isOnline.value ? 'on' : 'off')
      }
    })

    const wrapper = await mountSuspended(Harness)

    window.dispatchEvent(new Event('offline'))
    await nextTick()
    expect(wrapper.text()).toBe('off')
    expect(onReconnect).not.toHaveBeenCalled() // ainda offline

    window.dispatchEvent(new Event('online'))
    await nextTick()
    expect(wrapper.text()).toBe('on')
    expect(onReconnect).toHaveBeenCalledTimes(1) // reconexão dispara reconciliação
  })
})
