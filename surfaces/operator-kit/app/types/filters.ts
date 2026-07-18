// Contrato do recorte por dimensões (FilterBar) — genérico, sem domínio.
// O app hospedeiro descreve as dimensões (o QUE se pode filtrar) e guarda os
// filtros ativos; o componente só edita esse estado. Quem interpreta o valor é o
// app (a barra não sabe o que é "sync" ou "estoque").
//
// Chaves em inglês (id/value), rótulos em pt-BR (label) — convenção do projeto.

export type FilterType = "single-select" | "multi-select" | "boolean";

export interface FilterOption {
  value: string;
  label: string;
  count?: number; // quantos itens casariam esta opção (opcional; some quando indefinido)
}

export interface FilterDimension {
  id: string;
  label: string;
  type: FilterType;
  options: FilterOption[];
}

// Valor por dimensão: string (single-select), string[] (multi-select) ou boolean.
// Dimensão AUSENTE do registro = sem recorte (não existe "todos" como valor).
export type ActiveFilters = Record<string, string | string[] | boolean>;
