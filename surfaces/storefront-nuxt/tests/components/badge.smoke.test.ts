// Smoke do harness de component tests (env `nuxt` + mountSuspended): valida que
// componentes reais montam com auto-imports do Nuxt (tv/reka-ui) resolvidos.
import { describe, it, expect } from 'vitest'
import { mountSuspended } from '@nuxt/test-utils/runtime'
import UiBadge from '~/components/Ui/Badge.vue'

describe('UiBadge (component harness smoke)', () => {
  it('renders slot content', async () => {
    const wrapper = await mountSuspended(UiBadge, {
      slots: { default: () => 'Ambiente de teste' }
    })
    expect(wrapper.text()).toContain('Ambiente de teste')
  })

  it('applies the destructive variant classes', async () => {
    const wrapper = await mountSuspended(UiBadge, {
      props: { variant: 'destructive' },
      slots: { default: () => 'Erro' }
    })
    expect(wrapper.html()).toContain('bg-destructive')
  })
})
