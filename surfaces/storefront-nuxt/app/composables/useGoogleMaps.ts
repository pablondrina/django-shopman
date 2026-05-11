declare global {
  interface Window {
    google?: any
    __shopman_maps_loading?: Promise<void>
  }
}

export function useGoogleMaps () {
  const { publicConfig } = useShopSession()

  const apiKey = computed(() => publicConfig.value?.google_maps_api_key || '')
  const isReady = ref(false)
  const isAvailable = computed(() => !!apiKey.value)

  function ensureLoaded (): Promise<void> {
    if (!apiKey.value) return Promise.reject(new Error('Google Maps API key not configured'))
    if (typeof window === 'undefined') return Promise.reject(new Error('SSR'))
    if (window.google?.maps?.places) {
      isReady.value = true
      return Promise.resolve()
    }
    if (window.__shopman_maps_loading) return window.__shopman_maps_loading

    window.__shopman_maps_loading = new Promise<void>((resolve, reject) => {
      const script = document.createElement('script')
      script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(apiKey.value)}&libraries=places&language=pt-BR&region=BR&loading=async`
      script.async = true
      script.defer = true
      script.onload = () => {
        isReady.value = true
        resolve()
      }
      script.onerror = () => reject(new Error('Failed to load Google Maps'))
      document.head.appendChild(script)
    })

    return window.__shopman_maps_loading
  }

  return { isReady, isAvailable, ensureLoaded }
}
