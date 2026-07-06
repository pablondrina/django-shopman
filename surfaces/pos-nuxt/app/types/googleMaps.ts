// Tipos MÍNIMOS da Google Maps JS API que a superfície realmente toca — a SDK é
// carregada dinamicamente por <script> (sem pacote npm/@types), então declaramos só o
// slice usado no autocomplete de endereço. Não é a API inteira, é o contrato de fato.

export interface GoogleAddressComponent {
  types: string[];
  long_name?: string;
  short_name?: string;
}

export interface GooglePlaceResult {
  formatted_address?: string;
  place_id?: string;
  address_components?: GoogleAddressComponent[];
  geometry?: { location?: { lat: () => number; lng: () => number } };
}

export interface GoogleAutocomplete {
  addListener: (event: string, handler: () => void) => void;
  getPlace: () => GooglePlaceResult;
}

export type GoogleAutocompleteCtor = new (
  input: HTMLInputElement,
  options?: Record<string, unknown>,
) => GoogleAutocomplete;

export interface GooglePlacesLibrary {
  Autocomplete?: GoogleAutocompleteCtor;
}

export interface GoogleMapsNamespace {
  places?: GooglePlacesLibrary;
  importLibrary?: (name: string) => Promise<GooglePlacesLibrary | undefined>;
  LatLng?: new (lat: number, lng: number) => unknown;
  Circle?: new (options: { center: unknown; radius: number }) => { getBounds: () => unknown };
  event?: { clearInstanceListeners: (instance: unknown) => void };
}

export interface GoogleNamespace {
  maps?: GoogleMapsNamespace;
}
