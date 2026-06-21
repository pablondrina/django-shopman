/**
 * Cor do canvas (área revelada no overscroll/rubber-band do iOS) acompanha
 * DINAMICAMENTE o elemento de borda da tela:
 *   - topo  → cor do elemento no topo da página (status bar, ou navbar quando a
 *             status colapsar, ou um topo colorido) — amostrada ao vivo, sem
 *             assumir uma cor fixa. Assim não há diferença entre a navbar e o
 *             scrollover superior, aconteça o que acontecer no topo.
 *   - base  → bottom-nav no mobile (--shop-bottomnav) · rodapé no desktop (--shop-footer)
 *
 * CSS puro não consegue topo ≠ base (o overscroll pinta uma cor única do canvas),
 * então pintamos o background do <html> por posição de scroll. O <body> é
 * transparente, e o <html> só aparece no overscroll. Client-only.
 */
export default defineNuxtPlugin(() => {
  if (!import.meta.client) return

  const root = document.documentElement
  const mobile = window.matchMedia('(max-width: 767px)')
  let ticking = false
  // Cache da cor do topo: o rubber-band superior leva scrollY a negativo e desloca
  // o layout, então só re-amostramos com o layout estável (scrollY >= 0) e usamos
  // o cache durante o overscroll.
  let topColor = 'var(--shop-ink)'

  // Sobe da posição (centro, y) até achar um background sólido (não-transparente).
  function solidBgAt (y: number): string | null {
    let el = document.elementFromPoint(Math.floor(window.innerWidth / 2), y) as HTMLElement | null
    while (el && el !== root) {
      const bg = getComputedStyle(el).backgroundColor
      if (bg && bg !== 'rgba(0, 0, 0, 0)' && bg !== 'transparent') return bg
      el = el.parentElement
    }
    return null
  }

  function paint () {
    ticking = false
    const atBottom = window.innerHeight + window.scrollY >= root.scrollHeight - 4
    if (atBottom) {
      root.style.backgroundColor = mobile.matches ? 'var(--shop-bottomnav)' : 'var(--shop-footer)'
      return
    }
    // Topo dinâmico: 2px abaixo da borda cai dentro do elemento do topo (header sticky).
    if (window.scrollY >= 0) {
      const sampled = solidBgAt(2)
      if (sampled) topColor = sampled
    }
    root.style.backgroundColor = topColor
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
  // Primeira amostragem após o paint inicial do layout.
  requestAnimationFrame(paint)
})
