// Contrato do seletor de colunas (ColumnPicker) — genérico, sem domínio.
// O app hospedeiro descreve as colunas OPCIONAIS (as que podem sumir) e guarda a
// lista de ocultas; o componente só edita esse estado.
//
// Chaves em inglês (id), rótulos em pt-BR (label) — convenção do projeto.

export interface ColumnOption {
  id: string;
  label: string;
}

/**
 * Colunas OCULTAS, por id. Guardamos o que está escondido (e não o que está
 * visível) de propósito: coluna nova que aparece no servidor — um canal ou feed
 * recém-criado — nasce VISÍVEL, sem precisar que o operador vá marcá-la. Com a
 * lista de visíveis seria o contrário: a coluna nova nasceria invisível e ninguém
 * saberia que ela existe.
 */
export type HiddenColumns = string[];
