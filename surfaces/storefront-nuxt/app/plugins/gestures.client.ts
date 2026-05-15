const EDGE_THRESHOLD = 28
const SWIPE_THRESHOLD = 84
const SWIPE_VELOCITY = 0.32
const PULL_THRESHOLD = 72
const DISMISS_THRESHOLD = 72
const EDGE_BACK_PATHS = ['/', '/menu', '/como-funciona', '/offline']
const EDGE_BACK_PREFIXES = ['/produto/']

function matchesPath (pathname: string, prefixes: string[]) {
  return prefixes.some(prefix => pathname.startsWith(prefix))
}

function canUseEdgeBack () {
  const path = window.location.pathname
  return window.history.length > 1 && (EDGE_BACK_PATHS.includes(path) || matchesPath(path, EDGE_BACK_PREFIXES))
}

function hasOpenDialog () {
  return Boolean(document.querySelector('[role="dialog"], [aria-modal="true"]'))
}

function isInteractiveTarget (target: EventTarget | null) {
  if (!(target instanceof Element)) return true
  return Boolean(target.closest([
    'a',
    'button',
    'input',
    'textarea',
    'select',
    'summary',
    '[role="button"]',
    '[role="link"]',
    '[contenteditable="true"]',
    '[data-gesture-ignore]'
  ].join(',')))
}

export default defineNuxtPlugin(() => {
  const { light } = useHaptics()
  let startX = 0
  let startY = 0
  let startAt = 0
  let edgeSwipe = false
  let pullTarget: HTMLElement | null = null
  let dismissTarget: HTMLElement | null = null

  document.addEventListener('touchstart', (event) => {
    if (event.touches.length !== 1 || isInteractiveTarget(event.target)) return
    const target = event.target instanceof Element ? event.target : null
    const swipeDismissTarget = target?.closest<HTMLElement>('[data-swipe-dismiss]') || null
    if (hasOpenDialog() && !swipeDismissTarget) return

    const touch = event.touches[0]
    startX = touch.clientX
    startY = touch.clientY
    startAt = Date.now()
    dismissTarget = swipeDismissTarget
    edgeSwipe = !dismissTarget && startX <= EDGE_THRESHOLD && canUseEdgeBack()
    pullTarget = !dismissTarget && window.scrollY <= 0
      ? document.querySelector<HTMLElement>('[data-pull-refresh]')
      : null
  }, { passive: true })

  document.addEventListener('touchend', (event) => {
    const touch = event.changedTouches[0]
    if (!touch) return

    const deltaX = touch.clientX - startX
    const deltaY = touch.clientY - startY
    const elapsed = Math.max(1, Date.now() - startAt)

    if (edgeSwipe && deltaX > SWIPE_THRESHOLD && Math.abs(deltaY) < deltaX * 0.5 && deltaX / elapsed > SWIPE_VELOCITY) {
      event.preventDefault()
      light()
      window.history.back()
    } else if (pullTarget && window.scrollY <= 0 && deltaY > PULL_THRESHOLD && Math.abs(deltaX) < 48) {
      pullTarget.dispatchEvent(new CustomEvent('shopman-pull-refresh', { bubbles: true }))
      light()
    } else if (dismissTarget && deltaY > DISMISS_THRESHOLD && Math.abs(deltaX) < 56) {
      dismissTarget.dispatchEvent(new CustomEvent('shopman-swipe-dismiss', { bubbles: true }))
      dismissTarget.querySelector<HTMLElement>('[data-dismiss]')?.click()
      light()
    }

    edgeSwipe = false
    pullTarget = null
    dismissTarget = null
  }, { passive: false })
})
