import type { HubTileProjection } from "~/types/hub";

// Presentation pura da Central — sem estado, sem Nuxt; testável isolada.

/** O ícone do tile vem sem prefixo do Django; o <Icon> do @nuxt/icon quer `lucide:x`. */
export function tileIcon(icon: string): string {
  return icon.startsWith("lucide:") ? icon : `lucide:${icon}`;
}

/** Launch (superfície de operador) fica na mesma aba; external (loja do cliente) abre em nova. */
export function tileTarget(tile: Pick<HubTileProjection, "kind">): "_self" | "_blank" {
  return tile.kind === "external" ? "_blank" : "_self";
}

/** Grade vazia = operador autenticado sem nenhum app liberado (estado acolhedor). */
export function hubIsEmpty(tiles: HubTileProjection[]): boolean {
  return tiles.length === 0;
}

/** Saudação sóbria (sem hora do dia — o operador entra em qualquer turno). */
export function hubGreeting(operatorName: string): string {
  const name = (operatorName || "").trim();
  return name ? `Olá, ${name}` : "Central de Apps";
}
