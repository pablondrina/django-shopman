// Contrato da Central de Apps — espelha `OperatorHubProjection` do Django
// (shopman/backstage/projections/hub.py). Os tiles já vêm FILTRADOS por permissão:
// se está na lista, o operador pode abrir.

export interface HubTileProjection {
  ref: string;
  label: string;
  description: string;
  /** Nome Lucide do ícone forte da superfície (DS §6), sem o prefixo `lucide:`. */
  icon: string;
  url: string;
  /** "launch" = abre a superfície dedicada; "config" = deep-link pro Unfold. */
  kind: "launch" | "config";
}

export interface OperatorHubProjection {
  operator_name: string;
  tiles: HubTileProjection[];
}

export interface HubResponse {
  hub: OperatorHubProjection;
}
