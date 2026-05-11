/**
 * Helper for POST/PUT/DELETE actions against the backstage API.
 * Handles CSRF token + cookies + error toast in one place.
 */
export function useBackstageAction () {
  const apiPath = useBackstageApiPath()
  const toast = useToast()

  function csrfHeader (): Record<string, string> {
    const token = useCookie('csrftoken').value || ''
    return token ? { 'X-CSRFToken': token } : {}
  }

  async function call<T = unknown> (
    path: string,
    options: { method?: 'POST' | 'PUT' | 'PATCH' | 'DELETE', body?: Record<string, unknown>, successTitle?: string } = {}
  ): Promise<T | null> {
    const { method = 'POST', body, successTitle } = options
    try {
      const result = await $fetch<T>(apiPath(path), {
        method,
        credentials: 'include',
        headers: csrfHeader(),
        body
      })
      if (successTitle) {
        toast.add({ icon: 'i-lucide-circle-check', color: 'success', title: successTitle })
      }
      return result
    } catch (e: any) {
      toast.add({
        icon: 'i-lucide-circle-x',
        color: 'error',
        title: 'Falha na ação',
        description: e?.data?.detail || e?.message || ''
      })
      return null
    }
  }

  return { call, csrfHeader }
}
