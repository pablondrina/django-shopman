import type { POSAddressAutocompleteProjection } from "~/types/pos";
import type { GoogleNamespace, GooglePlacesLibrary } from "~/types/googleMaps";

declare global {
  interface Window {
    google?: GoogleNamespace;
    __shopman_pos_maps_loading?: Promise<GooglePlacesLibrary>;
    __shopman_pos_places_library?: GooglePlacesLibrary;
  }
}

export function usePosGoogleMaps(capability: Ref<POSAddressAutocompleteProjection | null | undefined>) {
  const isReady = ref(false);
  const isAvailable = computed(() => {
    const config = capability.value;
    return Boolean(config?.enabled && config.public_api_key && config.provider === "google_places");
  });

  async function ensurePlacesLibrary(): Promise<GooglePlacesLibrary> {
    const cached = window.__shopman_pos_places_library;
    if (cached?.Autocomplete) return cached;
    const maps = window.google?.maps;
    if (maps?.places?.Autocomplete) {
      window.__shopman_pos_places_library = maps.places;
      return maps.places;
    }
    if (maps?.importLibrary) {
      const library = await maps.importLibrary("places");
      window.__shopman_pos_places_library = library || maps.places;
    }
    if (!window.__shopman_pos_places_library?.Autocomplete && maps?.places?.Autocomplete) {
      window.__shopman_pos_places_library = maps.places;
    }
    const resolved = window.__shopman_pos_places_library;
    if (!resolved?.Autocomplete) {
      throw new Error("Google Places library unavailable");
    }
    return resolved;
  }

  function ensureLoaded(): Promise<GooglePlacesLibrary> {
    const config = capability.value;
    if (!config?.public_api_key) return Promise.reject(new Error("Google Maps API key not configured"));
    if (typeof window === "undefined") return Promise.reject(new Error("SSR"));
    const existing = window.__shopman_pos_places_library ?? window.google?.maps?.places;
    if (existing?.Autocomplete) {
      isReady.value = true;
      return Promise.resolve(existing);
    }
    if (window.__shopman_pos_maps_loading) return window.__shopman_pos_maps_loading;

    const language = encodeURIComponent(config.language || "pt-BR");
    const region = encodeURIComponent(config.region || "BR");
    const key = encodeURIComponent(config.public_api_key);

    window.__shopman_pos_maps_loading = new Promise<GooglePlacesLibrary>((resolve, reject) => {
      const script = document.createElement("script");
      script.src = `https://maps.googleapis.com/maps/api/js?key=${key}&libraries=places&language=${language}&region=${region}&loading=async`;
      script.async = true;
      script.defer = true;
      script.onload = () => {
        ensurePlacesLibrary()
          .then((places) => {
            isReady.value = true;
            resolve(places);
          })
          .catch(reject);
      };
      script.onerror = () => reject(new Error("Failed to load Google Maps"));
      document.head.appendChild(script);
    }).catch((error) => {
      window.__shopman_pos_maps_loading = undefined;
      throw error;
    });

    return window.__shopman_pos_maps_loading;
  }

  return { isReady, isAvailable, ensureLoaded };
}
