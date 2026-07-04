// Reproduz o clique nas estrelas DENTRO do BottomSheet (contexto real do overlay
// de avaliação) — o usuário relatou que não respondiam ao clique ali.
import { describe, it, expect } from 'vitest'
import { defineComponent, h, ref, nextTick } from 'vue'
import { mountSuspended } from '@nuxt/test-utils/runtime'
import BottomSheet from '~/components/BottomSheet.vue'
import UiStarRating from '~/components/Ui/StarRating.vue'

describe('StarRating dentro do BottomSheet', () => {
  it('responde ao clique quando o sheet está aberto', async () => {
    const rating = ref(5)
    const Harness = defineComponent({
      setup () {
        return () => h(BottomSheet, { open: true, title: 'Avaliar' }, {
          default: () => h(UiStarRating, {
            modelValue: rating.value,
            'onUpdate:modelValue': (v: number) => { rating.value = v }
          })
        })
      }
    })
    await mountSuspended(Harness)
    await nextTick()
    // O conteúdo do sheet é teleportado para o body.
    const stars = document.body.querySelectorAll('[role="radio"]')
    expect(stars.length).toBe(5)
    ;(stars[1] as HTMLElement).click()
    await nextTick()
    expect(rating.value).toBe(2)
  })
})
