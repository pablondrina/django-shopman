// Push instantâneo do acompanhamento (G1): o composable abre um EventSource
// same-origin no BFF e chama onPush a cada evento. Testado isoladamente
// (connect/close manuais — fora de componente, os hooks de ciclo de vida não
// registram) com um EventSource fake.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mockNuxtImport } from '@nuxt/test-utils/runtime'

mockNuxtImport('useShopmanApiPath', () => () => (path: string) => path)

class FakeEventSource {
  static instances: FakeEventSource[] = []
  url: string
  withCredentials: boolean
  listeners: Record<string, Array<() => void>> = {}
  onerror: ((e?: unknown) => void) | null = null
  closed = false

  constructor (url: string, init?: { withCredentials?: boolean }) {
    this.url = url
    this.withCredentials = Boolean(init?.withCredentials)
    FakeEventSource.instances.push(this)
  }

  addEventListener (name: string, handler: () => void) {
    ;(this.listeners[name] ||= []).push(handler)
  }

  emit (name: string) {
    ;(this.listeners[name] || []).forEach(h => h())
  }

  close () { this.closed = true }
}

async function loadComposable () {
  const mod = await import('~/composables/useOrderTrackingStream')
  return mod.useOrderTrackingStream
}

describe('useOrderTrackingStream', () => {
  beforeEach(() => {
    FakeEventSource.instances = []
    vi.stubGlobal('EventSource', FakeEventSource as unknown as typeof EventSource)
  })

  it('conecta same-origin em /sse/pedido/<ref> com withCredentials', async () => {
    const useOrderTrackingStream = await loadComposable()
    const { connect } = useOrderTrackingStream(() => 'ORD-42', () => {})
    connect()

    expect(FakeEventSource.instances).toHaveLength(1)
    const es = FakeEventSource.instances[0]!
    expect(es.url).toBe('/sse/pedido/ORD-42')
    expect(es.withCredentials).toBe(true)
  })

  it('chama onPush nos eventos order-update e message', async () => {
    const useOrderTrackingStream = await loadComposable()
    const onPush = vi.fn()
    const { connect } = useOrderTrackingStream(() => 'ORD-1', onPush)
    connect()

    const es = FakeEventSource.instances[0]!
    es.emit('order-update')
    es.emit('message')
    expect(onPush).toHaveBeenCalledTimes(2)
  })

  it('encoda o ref na URL', async () => {
    const useOrderTrackingStream = await loadComposable()
    const { connect } = useOrderTrackingStream(() => 'ORD/42 A', () => {})
    connect()
    expect(FakeEventSource.instances[0]!.url).toBe('/sse/pedido/ORD%2F42%20A')
  })

  it('não conecta sem ref', async () => {
    const useOrderTrackingStream = await loadComposable()
    const { connect } = useOrderTrackingStream(() => '', () => {})
    connect()
    expect(FakeEventSource.instances).toHaveLength(0)
  })

  it('não abre uma segunda conexão em connect() repetido', async () => {
    const useOrderTrackingStream = await loadComposable()
    const { connect } = useOrderTrackingStream(() => 'ORD-1', () => {})
    connect()
    connect()
    expect(FakeEventSource.instances).toHaveLength(1)
  })

  it('close() fecha o EventSource e permite reconectar depois', async () => {
    const useOrderTrackingStream = await loadComposable()
    const { connect, close } = useOrderTrackingStream(() => 'ORD-1', () => {})
    connect()
    const first = FakeEventSource.instances[0]!
    close()
    expect(first.closed).toBe(true)

    connect()
    expect(FakeEventSource.instances).toHaveLength(2)
  })

  it('degrada em silêncio se o construtor do EventSource lançar', async () => {
    vi.stubGlobal('EventSource', class {
      constructor () { throw new Error('no SSE') }
      close () {}
    } as unknown as typeof EventSource)
    const useOrderTrackingStream = await loadComposable()
    const { connect, close } = useOrderTrackingStream(() => 'ORD-1', () => {})
    expect(() => connect()).not.toThrow()
    expect(() => close()).not.toThrow()
  })
})
