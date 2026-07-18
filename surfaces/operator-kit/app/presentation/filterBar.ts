// FilterBar — transformações puras do estado de filtros. O componente só renderiza
// o que sai daqui, então a lógica de "o que está ativo", "como se lê o chip" e "o
// que acontece ao clicar numa opção" é testável sem montar Vue.
import type { ActiveFilters, FilterDimension, FilterOption } from "../types/filters";

// Boolean é a única dimensão cujas opções não vêm do app: é sempre sim/não. Ter o
// par aqui evita que cada superfície reinvente o rótulo.
export const BOOLEAN_OPTIONS: FilterOption[] = [
  { value: "true", label: "Sim" },
  { value: "false", label: "Não" },
];

export function optionsFor(dimension: FilterDimension): FilterOption[] {
  return dimension.type === "boolean" ? BOOLEAN_OPTIONS : dimension.options;
}

// Uma dimensão só conta como ativa quando tem valor útil: multi-select com lista
// vazia é o mesmo que não filtrar (e não deve virar chip).
export function isActive(filters: ActiveFilters, id: string): boolean {
  const value = filters[id];
  if (value === undefined) return false;
  if (Array.isArray(value)) return value.length > 0;
  return true;
}

export function isSelected(filters: ActiveFilters, dimension: FilterDimension, value: string): boolean {
  const current = filters[dimension.id];
  if (current === undefined) return false;
  if (dimension.type === "boolean") return String(current) === value;
  if (Array.isArray(current)) return current.includes(value);
  return current === value;
}

/** Rótulo do chip: "Estoque: baixo, esgotado" (multi) · "Publicado: sim" (boolean). */
export function chipLabel(dimension: FilterDimension, filters: ActiveFilters): string {
  const current = filters[dimension.id];
  const options = optionsFor(dimension);
  const labelOf = (value: string) => options.find((o) => o.value === value)?.label ?? value;
  if (dimension.type === "boolean") return `${dimension.label}: ${labelOf(String(current))}`;
  if (Array.isArray(current)) return `${dimension.label}: ${current.map(labelOf).join(", ")}`;
  return `${dimension.label}: ${labelOf(String(current))}`;
}

/** Dimensões com recorte ativo, na ordem em que o app as declarou (chips estáveis). */
export function activeDimensions(dimensions: FilterDimension[], filters: ActiveFilters): FilterDimension[] {
  return dimensions.filter((d) => isActive(filters, d.id));
}

/**
 * Clique numa opção → próximo estado. Multi-select acumula/remove; single-select e
 * boolean trocam o valor, e reclicar o valor já escolhido LIMPA a dimensão (o mesmo
 * gesto que ligou desliga — não há botão "todos").
 */
export function toggleOption(
  filters: ActiveFilters,
  dimension: FilterDimension,
  value: string,
): ActiveFilters {
  const next = { ...filters };
  if (dimension.type === "multi-select") {
    const current = Array.isArray(next[dimension.id]) ? (next[dimension.id] as string[]) : [];
    const picked = current.includes(value) ? current.filter((v) => v !== value) : [...current, value];
    if (picked.length) next[dimension.id] = picked;
    else delete next[dimension.id];
    return next;
  }
  const parsed: string | boolean = dimension.type === "boolean" ? value === "true" : value;
  if (isSelected(filters, dimension, value)) delete next[dimension.id];
  else next[dimension.id] = parsed;
  return next;
}

export function clearDimension(filters: ActiveFilters, id: string): ActiveFilters {
  const next = { ...filters };
  delete next[id];
  return next;
}
