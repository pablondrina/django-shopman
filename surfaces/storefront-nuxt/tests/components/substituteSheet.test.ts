// SubstituteSheet (WP-S6): o aviso acionável do 409 sobe quando há cartIssue e
// adapta a copy — "esgotou" com alternativas vs "ajuste a quantidade" quando
// ainda há saldo. Dirigido pelo estado global cartIssue (useState).
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { nextTick } from 'vue'
import { mountSuspended, mockNuxtImport } from '@nuxt/test-utils/runtime'
import SubstituteSheet from '~/components/SubstituteSheet.vue'

mockNuxtImport('useSonner', () => {
  const fn: any = () => {}
  fn.success = () => {}
  fn.error = () => {}
  return () => fn
})

async function setIssue (issue: unknown) {
  const { useCartState } = await import('~/composables/useCartState')
  const store = useCartState()
  store.cartIssue.value = issue as never
}

const OUT_OF_STOCK = {
  title: 'Esgotou', detail: 'x', error_code: 'insufficient_stock',
  sku: 'CROISSANT', name: 'Croissant', requested_qty: 2, available_qty: 0,
  is_paused: false, is_planned: false, actions: [], items: [],
  substitutes: [{ sku: 'PAO', name: 'Pão', price_q: 400, price_display: 'R$ 4,00', image_url: null, available_qty: 5, can_order: true, target_qty: 2, reason: undefined }]
}

describe('SubstituteSheet', () => {
  beforeEach(async () => {
    document.cookie = 'csrftoken=testtoken'
    vi.unstubAllGlobals()
    vi.stubGlobal('$fetch', vi.fn().mockResolvedValue({ cart: { items: [], items_count: 0, is_empty: true } }))
    await setIssue(null)
  })

  it('stays closed when there is no cart issue', async () => {
    await mountSuspended(SubstituteSheet)
    expect(document.body.textContent).not.toContain('Esgotou enquanto você escolhia')
  })

  it('surfaces the out-of-stock copy and the substitute when an issue is present', async () => {
    await setIssue(OUT_OF_STOCK)
    await mountSuspended(SubstituteSheet)
    await nextTick()
    const body = document.body.textContent || ''
    expect(body).toContain('Esgotou enquanto você escolhia')
    expect(body).toContain('Pão')
  })

  it('offers "adjust quantity" copy when there is still available stock', async () => {
    await setIssue({ ...OUT_OF_STOCK, available_qty: 3, substitutes: [] })
    await mountSuspended(SubstituteSheet)
    await nextTick()
    const body = document.body.textContent || ''
    expect(body).toContain('Ajuste a quantidade')
    expect(body).toContain('Levar 3 unidades')
  })
})
