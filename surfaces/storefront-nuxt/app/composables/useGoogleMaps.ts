declare global {
  interface Window {
    google?: any
    __shopman_maps_loading?: Promise<any>
    __shopman_places_library?: any
  }
}

export function useGoogleMaps () {
  const { publicConfig } = useShopSession()
  const runtimeConfig = useRuntimeConfig()

  const apiKey = computed(() => publicConfig.value?.google_maps_api_key || runtimeConfig.public.googleMapsApiKey || '')
  const isReady = ref(false)
  const isAvailable = computed(() => !!apiKey.value)

  async function ensurePlacesLibrary () {
    if (window.__shopman_places_library?.Autocomplete) return window.__shopman_places_library
    if (window.google?.maps?.places?.Autocomplete) {
      window.__shopman_places_library = window.google.maps.places
      return window.__shopman_places_library
    }
    if (window.google?.maps?.importLibrary) {
      const library = await window.google.maps.importLibrary('places')
      window.__shopman_places_library = library || window.google?.maps?.places
    }
    if (!window.__shopman_places_library?.Autocomplete && window.google?.maps?.places?.Autocomplete) {
      window.__shopman_places_library = window.google.maps.places
    }
    if (!window.__shopman_places_library?.Autocomplete) {
      throw new Error('Google Places library unavailable')
    }
    return window.__shopman_places_library
  }

  function ensureLoaded (): Promise<any> {
    if (!apiKey.value) return Promise.reject(new Error('Google Maps API key not configured'))
    if (typeof window === 'undefined') return Promise.reject(new Error('SSR'))
    if (window.__shopman_places_library?.Autocomplete || window.google?.maps?.places?.Autocomplete) {
      isReady.value = true
      return Promise.resolve(window.__shopman_places_library || window.google.maps.places)
    }
    if (window.__shopman_maps_loading) return window.__shopman_maps_loading

    window.__shopman_maps_loading = new Promise<any>((resolve, reject) => {
      const script = document.createElement('script')
      script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(apiKey.value)}&libraries=places&language=pt-BR&region=BR&loading=async`
      script.async = true
      script.defer = true
      script.onload = () => {
        ensurePlacesLibrary()
          .then((places) => {
            isReady.value = true
            resolve(places)
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
