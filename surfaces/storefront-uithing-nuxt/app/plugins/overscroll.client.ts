/**
 * Cor do canvas (área revelada no overscroll/rubber-band do iOS) acompanha o
 * elemento de BORDA da tela:
 *   - topo  → status bar / navbar burgundy  (--shop-ink, = bg-ink da status bar)
 *   - base  → bottom-nav no mobile (--shop-bottomnav) · rodapé no desktop (--shop-footer)
 *
 * CSS puro não consegue topo ≠ base (o overscroll pinta uma cor única do canvas),
 * então pintamos o background do <html> por posição de scroll. O <body> mantém
 * bg-background (o conteúdo), e o <html> só aparece no overscroll. Client-only.
 */
export default defineNuxtPlugin(() => {
  if (!import.meta.client) return

  const root = document.documentElement
  const mobile = window.matchMedia('(max-width: 767px)')
  let ticking = false

  function paint () {
    ticking = false
    const atBottom = window.innerHeight + window.scrollY >= root.scrollHeight - 4
    const bottom = mobile.matches ? 'var(--shop-bottomnav)' : 'var(--shop-footer)'
    root.style.backgroundColor = atBottom ? bottom : 'var(--shop-ink)'
  }

  function schedule () {
    if (ticking) return
    ticking = true
    requestAnimationFrame(paint)
  }

  window.addEventListener('scroll', schedule, { passive: true })
  window.addEventListener('resize', schedule, { passive: true })
  // `scrollend`/`touchend` garantem o repintar na posição ASSENTADA (um scroll
  // programático/suave pode não disparar 'scroll' no fim, deixando a base sem virar).
  window.addEventListener('scrollend', paint, { passive: true })
  window.addEventListener('touchend', schedule, { passive: true })
  mobile.addEventListener('change', paint)
  paint()
})
