/**
 * Toggle browser fullscreen for the body. Useful for KDS displays.
 */
export function useFullscreen () {
  const isFullscreen = ref(false)

  function update () {
    if (typeof document === 'undefined') return
    isFullscreen.value = !!document.fullscreenElement
  }

  async function toggle () {
    if (typeof document === 'undefined') return
    if (document.fullscreenElement) {
      await document.exitFullscreen()
    } else {
      await document.documentElement.requestFullscreen().catch(() => {})
    }
  }

  if (import.meta.client) {
    onMounted(() => {
      update()
      document.addEventListener('fullscreenchange', update)
    })
    onBeforeUnmount(() => {
      document.removeEventListener('fullscreenchange', update)
    })
  }

  return { isFullscreen, toggle }
}
