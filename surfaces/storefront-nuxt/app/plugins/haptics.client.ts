export default defineNuxtPlugin(() => {
  const { triggerHaptic } = useHaptics()

  document.addEventListener('click', (event) => {
    const target = event.target instanceof Element
      ? event.target.closest<HTMLElement>('[data-haptic]')
      : null
    if (!target || target.hasAttribute('disabled') || target.getAttribute('aria-disabled') === 'true') return

    triggerHaptic(target.dataset.haptic || 'light')
  }, { passive: true })
})
