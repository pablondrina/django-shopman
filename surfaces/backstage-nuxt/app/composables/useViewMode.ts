/**
 * Persisted grid/list view toggle per panorama page.
 * Stored in localStorage under `view-mode:<key>`.
 */
export type ViewMode = 'grid' | 'list'

export function useViewMode (key: string, fallback: ViewMode = 'grid') {
  const storageKey = `view-mode:${key}`

  const mode = useState<ViewMode>(`view-mode-${key}`, () => fallback)

  if (import.meta.client) {
    onMounted(() => {
      const stored = localStorage.getItem(storageKey) as ViewMode | null
      if (stored === 'grid' || stored === 'list') mode.value = stored
    })

    watch(mode, (next) => {
      localStorage.setItem(storageKey, next)
    })
  }

  function toggle () {
    mode.value = mode.value === 'grid' ? 'list' : 'grid'
  }

  return { mode, toggle }
}
