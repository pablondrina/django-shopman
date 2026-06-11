// Pulso visual compartilhado do carrinho: dispara quando a contagem de itens
// sobe (otimista, então reage no toque) e relaxa sozinho depois de ~900ms.
export function useCartPulse () {
  const { cart } = useCartState()
  const cartPulse = ref(false)
  let cartPulseTimer: ReturnType<typeof setTimeout> | null = null

  watch(() => cart.value.items_count, (next, previous) => {
    if (previous == null || next <= previous) return
    cartPulse.value = true
    if (cartPulseTimer) clearTimeout(cartPulseTimer)
    cartPulseTimer = setTimeout(() => {
      cartPulse.value = false
      cartPulseTimer = null
    }, 900)
  })

  onBeforeUnmount(() => {
    if (cartPulseTimer) clearTimeout(cartPulseTimer)
  })

  return { cartPulse }
}
