// CartQuantityAction (WP-S6): o botão de adicionar só age depois de hidratado,
// dispara a mutação real (via useCartState → $fetch) e emite `changed`; com qty>0
// entrega o controle de quantidade em vez do botão.
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { nextTick } from 'vue'
import { mountSuspended, mockNuxtImport } from '@nuxt/test-utils/runtime'
import CartQuantityAction from '~/components/CartQuantityAction.vue'
import type { ProductMutationMeta } from '~/types/shopman'

mockNuxtImport('useSonner', () => {
  const fn: any = () => {}
  fn.success = () => {}
  fn.error = () => {}
  return () => fn
})

const meta: ProductMutationMeta = {
  sku: 'CROISSANT', name: 'Croissant', price_q: 500, price_display: 'R$ 5,00', image_url: null
}

describe('CartQuantityAction', () => {
  beforeEach(() => {
    document.cookie = 'csrftoken=testtoken'
    vi.unstubAllGlobals()
  })

  it('renders an add button with an accessible label when qty is 0', async () => {
    vi.stubGlobal('$fetch', vi.fn())
    const wrapper = await mountSuspended(CartQuantityAction, {
      props: { meta, qty: 0, addIconOnly: true }
    })
    const btn = wrapper.get('button')
    expect(btn.attributes('aria-label')).toBe('Adicionar Croissant')
  })

  it('adds to the cart and emits changed on click (after hydration)', async () => {
    const $fetch = vi.fn().mockResolvedValue({ cart: { items: [{ sku: 'CROISSANT', qty: 1 }], items_count: 1, is_empty: false } })
    vi.stubGlobal('$fetch', $fetch)
    const wrapper = await mountSuspended(CartQuantityAction, {
      props: { meta, qty: 0, addTargetQty: 3 }
    })
    await nextTick() // onMounted → hydrated

    await wrapper.get('button').trigger('click')
    await new Promise(r => setTimeout(r, 0)) // deixa a fila de mutação drenar

    expect($fetch).toHaveBeenCalledOnce()
    expect($fetch.mock.calls[0]?.[0]).toContain('/cart/skus/CROISSANT/')
    expect($fetch.mock.calls[0]?.[1]?.body).toEqual({ qty: 3 })
    expect(wrapper.emitted('changed')?.[0]).toEqual([3])
  })

  it('does not fire when disabled', async () => {
    const $fetch = vi.fn()
    vi.stubGlobal('$fetch', $fetch)
    const wrapper = await mountSuspended(CartQuantityAction, {
      props: { meta, qty: 0, disabled: true }
    })
    await nextTick()
    await wrapper.get('button').trigger('click')
    expect($fetch).not.toHaveBeenCalled()
  })
})
