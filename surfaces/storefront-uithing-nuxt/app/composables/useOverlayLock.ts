import type { MaybeRefOrGetter, Ref } from 'vue'

interface OverlayLockOptions {
  /**
   * Elementos (ou seletores) marcados como `inert` enquanto a overlay está aberta.
   * É o trap de foco: o teclado/leitor de tela não alcança o conteúdo inerte por trás.
   * O painel teleportado p/ o `body` fica fora dessas árvores, então permanece ativo.
   */
  inert?: Array<string | HTMLElement | null | undefined>
  /** Chamado quando Esc é pressionado com a overlay aberta. */
  onEscape?: () => void
  /**
   * Painel que recebe foco ao abrir (pulado se já contém o foco — ex.: a busca foca
   * o próprio input dentro do gesto, para o teclado do iOS). Ao fechar, o foco volta
   * para o elemento que abriu a overlay.
   */
  focus?: MaybeRefOrGetter<HTMLElement | null | undefined>
}

const FOCUSABLE =
  '[autofocus], a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

/**
 * Comportamento canônico de overlay artesanal (busca fullscreen, gaveta de menu):
 * trava o scroll do corpo, fecha no Esc e prende o foco no painel via `inert`.
 * Concentra a lógica que antes vivia duplicada em cada overlay.
 */
export function useOverlayLock (isOpen: Ref<boolean>, options: OverlayLockOptions = {}) {
  const isLocked = useScrollLock(import.meta.client ? document.body : null)
  let lastActive: HTMLElement | null = null
  const inertEls: HTMLElement[] = []

  function resolveInert (): HTMLElement[] {
    if (!import.meta.client) return []
    const out: HTMLElement[] = []
    for (const target of options.inert ?? []) {
      if (!target) continue
      const el = typeof target === 'string' ? document.querySelector<HTMLElement>(target) : target
      if (el) out.push(el)
    }
    return out
  }

  function release () {
    isLocked.value = false
    for (const el of inertEls) el.inert = false
    inertEls.length = 0
  }

  useEventListener('keydown', (event: KeyboardEvent) => {
    if (isOpen.value && event.key === 'Escape') options.onEscape?.()
  })

  watch(isOpen, open => {
    if (!import.meta.client) return
    isLocked.value = open
    if (open) {
      lastActive = document.activeElement as HTMLElement | null
      for (const el of resolveInert()) {
        el.inert = true
        inertEls.push(el)
      }
      nextTick(() => {
        const panel = toValue(options.focus)
        if (panel && !panel.contains(document.activeElement)) {
          ;(panel.querySelector<HTMLElement>(FOCUSABLE) ?? panel).focus?.()
        }
      })
    } else {
      release()
      lastActive?.focus?.()
      lastActive = null
    }
  })

  onScopeDispose(release)
}
