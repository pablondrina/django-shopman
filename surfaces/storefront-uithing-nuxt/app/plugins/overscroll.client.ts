/**
 * Cor do canvas (área revelada no overscroll/rubber-band) acompanha DINAMICAMENTE
 * o elemento de borda — nos DOIS sentidos:
 *   - topo → cor do elemento no topo da página (status bar quando expandida, navbar
 *            quando a status colapsa, etc.)
 *   - base → cor do elemento na base (bottom-nav no mobile, rodapé no desktop, …)
 *
 * Amostra ao vivo via elementFromPoint (sobe até um bg sólido), a cada frame de
 * scroll + um repintar tardio quando o scroll/transições assentam (a status bar
 * colapsa em ~200ms; sem isso a cor "travava" ao voltar ao topo). Não amostra
 * DENTRO do próprio overscroll (layout deslocado) — usa o último valor estável.
 *
 * CSS puro não consegue topo ≠ base (o overscroll pinta uma cor única do canvas),
 * então pintamos o background do <html> por posição de scroll. O <body> é
 * transparente, e o <html> só aparece no overscroll. Client-only.
 */
export default defineNuxtPlugin(() => {
  if (!import.meta.client) return

  const root = document.documentElement
  let ticking = false
  let settleTimer = 0
  let topColor = 'var(--shop-ink)'
  let bottomColor = 'var(--shop-bottomnav)'

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

  function sample () {
    // Topo: só fora do overscroll de topo (scrollY >= 0); senão o layout está deslocado.
    if (window.scrollY >= 0) {
      const t = solidBgAt(2)
      if (t) topColor = t
    }
    // Base: só fora do overscroll de base.
    const maxScroll = root.scrollHeight - window.innerHeight
    if (window.scrollY <= maxScroll + 1) {
      const b = solidBgAt(window.innerHeight - 2)
      if (b) bottomColor = b
    }
  }

  function paint () {
    ticking = false
    sample()
    const atBottom = window.innerHeight + window.scrollY >= root.scrollHeight - 4
    root.style.backgroundColor = atBottom ? bottomColor : topColor
  }

  function schedule () {
    if (ticking) return
    ticking = true
    requestAnimationFrame(paint)
    // Re-amostra depois que o scroll + transições (status bar 200ms) assentam —
    // senão a cor do topo fica presa na navbar ao retornar ao topo.
    clearTimeout(settleTimer)
    settleTimer = window.setTimeout(paint, 300)
  }

  window.addEventListener('scroll', schedule, { passive: true })
  window.addEventListener('resize', schedule, { passive: true })
  window.addEventListener('scrollend', paint, { passive: true })
  window.addEventListener('touchend', schedule, { passive: true })
  requestAnimationFrame(paint)
})
