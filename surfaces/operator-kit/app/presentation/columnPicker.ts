// ColumnPicker — transformações puras do estado de colunas. O componente só renderiza
// o que sai daqui, então "o que está visível" e "o que acontece ao clicar" é testável
// sem montar Vue.
//
// A coluna obrigatória (no catálogo, a do produto) simplesmente NÃO entra na lista de
// opções: o app não a declara, então não há como ocultá-la. A regra é estrutural, não
// um `if` de guarda que alguém pode esquecer de replicar.
import type { ColumnOption, HiddenColumns } from "../types/columns";

export function isVisible(hidden: HiddenColumns, id: string): boolean {
  return !hidden.includes(id);
}

/** Recorta uma lista qualquer (colunas, células) pelas ocultas, preservando a ordem. */
export function keepVisible<T>(items: T[], hidden: HiddenColumns, id: (item: T) => string): T[] {
  return items.filter((item) => isVisible(hidden, id(item)));
}

export function toggleColumn(hidden: HiddenColumns, id: string): HiddenColumns {
  return hidden.includes(id) ? hidden.filter((h) => h !== id) : [...hidden, id];
}

export function showAll(): HiddenColumns {
  return [];
}

export function hideAll(columns: ColumnOption[]): HiddenColumns {
  return columns.map((c) => c.id);
}

export function visibleCount(columns: ColumnOption[], hidden: HiddenColumns): number {
  return columns.filter((c) => isVisible(hidden, c.id)).length;
}

/**
 * Ocultas higienizadas contra a lista viva de colunas: id que não existe mais (canal
 * removido, feed renomeado) é descartado. Sem isso o registro persistido acumularia
 * lixo para sempre e o "esconder todas" ficaria eternamente parecendo ativo.
 */
export function reconcile(columns: ColumnOption[], hidden: HiddenColumns): HiddenColumns {
  const known = new Set(columns.map((c) => c.id));
  return hidden.filter((id) => known.has(id));
}
