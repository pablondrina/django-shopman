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
  /** "launch" = superfície de operador (mesma aba); "external" = fora da zona, nova aba (ex.: loja do cliente). */
  kind: "launch" | "external";
}

export interface OperatorHubProjection {
  operator_name: string;
  tiles: HubTileProjection[];
}

export interface HubResponse {
  hub: OperatorHubProjection;
}
