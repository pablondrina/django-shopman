// StarRating (S8): 5 estrelas acessíveis; clicar emite a nota; a estrela marcada
// reflete o v-model.
import { describe, it, expect } from 'vitest'
import { mountSuspended } from '@nuxt/test-utils/runtime'
import StarRating from '~/components/Ui/StarRating.vue'

describe('StarRating', () => {
  it('renders max radio stars with the current value checked', async () => {
    const wrapper = await mountSuspended(StarRating, { props: { modelValue: 3, max: 5 } })
    const stars = wrapper.findAll('[role="radio"]')
    expect(stars).toHaveLength(5)
    expect(stars[2]!.attributes('aria-checked')).toBe('true')
  })

  it('emits the chosen rating on click', async () => {
    const wrapper = await mountSuspended(StarRating, { props: { modelValue: 5, max: 5 } })
    await wrapper.findAll('[role="radio"]')[1]!.trigger('click')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([2])
  })

  it('is inert when readonly', async () => {
    const wrapper = await mountSuspended(StarRating, { props: { modelValue: 4, max: 5, readonly: true } })
    await wrapper.findAll('[role="radio"]')[0]!.trigger('click')
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
  })
})
