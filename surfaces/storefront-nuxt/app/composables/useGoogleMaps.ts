// Loader do Google Maps JS (key pública domain-restricted do public_config).
// Carrega sob demanda — só quando o AddressPicker precisa de Places ou do
// mapa de ajuste — e degrada com dignidade quando a key não está configurada.

let bootstrapPromise: Promise<boolean> | null = null

declare global {
  interface Window {
    google?: typeof google
    __shopmanGoogleMapsReady?: () => void
  }
}

function injectBootstrap (apiKey: string): Promise<boolean> {
  return new Promise(resolve => {
    if (window.google?.maps?.importLibrary) {
      resolve(true)
      return
    }
    const params = new URLSearchParams({
      key: apiKey,
      v: 'weekly',
      loading: 'async',
      language: 'pt-BR',
      region: 'BR',
      callback: '__shopmanGoogleMapsReady'
    })
    window.__shopmanGoogleMapsReady = () => {
      delete window.__shopmanGoogleMapsReady
      resolve(!!window.google?.maps?.importLibrary)
    }
    const script = document.createElement('script')
    script.src = `https://maps.googleapis.com/maps/api/js?${params.toString()}`
    script.async = true
    script.onerror = () => resolve(false)
    document.head.appendChild(script)
  })
}

export function useGoogleMaps () {
  const session = useShopSession()

  const apiKey = computed(() => session.publicConfig.value?.google_maps_api_key || '')
  const enabled = computed(() => !!apiKey.value)
  const shopLocation = computed<{ lat: number, lng: number } | null>(() => {
    const config = session.publicConfig.value
    if (config?.shop_latitude == null || config?.shop_longitude == null) return null
    return { lat: config.shop_latitude, lng: config.shop_longitude }
  })

  async function load (): Promise<boolean> {
    if (!import.meta.client || !apiKey.value) return false
    if (!bootstrapPromise) bootstrapPromise = injectBootstrap(apiKey.value)
    return bootstrapPromise
  }

  // Genérico no call-site: importLibrary<google.maps.PlacesLibrary>('places').
  async function importLibrary<T = unknown> (name: string): Promise<T | null> {
    const ready = await load()
    if (!ready || !window.google) return null
    return window.google.maps.importLibrary(name) as Promise<T>
  }

  return { enabled, shopLocation, load, importLibrary }
}
