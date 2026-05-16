declare global {
  interface Window {
    google?: any
    __shopman_maps_loading?: Promise<void>
  }
}

export function useGoogleMaps () {
  const { publicConfig } = useShopSession()
  const runtimeConfig = useRuntimeConfig()

  const apiKey = computed(() => publicConfig.value?.google_maps_api_key || runtimeConfig.public.googleMapsApiKey || '')
  const isReady = ref(false)
  const isAvailable = computed(() => !!apiKey.value)

  async function ensurePlacesLibrary () {
    if (window.google?.maps?.places) return
    if (window.google?.maps?.importLibrary) {
      await window.google.maps.importLibrary('places')
    }
    if (!window.google?.maps?.places) {
      throw new Error('Google Places library unavailable')
    }
  }

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
        ensurePlacesLibrary()
          .then(() => {
            isReady.value = true
            resolve()
          })
          .catch(reject)
      }
      script.onerror = () => reject(new Error('Failed to load Google Maps'))
      document.head.appendChild(script)
    }).catch((error) => {
      window.__shopman_maps_loading = undefined
      throw error
    })

    return window.__shopman_maps_loading
  }

  return { isReady, isAvailable, ensureLoaded }
}
