// Presentation — relatórios e gestão de produção (página /reports, persona
// GESTOR). Transforms puras sobre as projections servidas por
// shopman/backstage/projections/production.py via a API de relatórios; as
// linhas já chegam prontas de tela (qty_*, yield_rate, duration pré-formatados)
// — esta camada só deriva rótulos, a query dos filtros e o link do CSV.

export type ReportKind = "history" | "operator_productivity" | "recipe_waste";

export const REPORT_KINDS: readonly { kind: ReportKind; label: string }[] = [
  { kind: "history", label: "Histórico" },
  { kind: "operator_productivity", label: "Produtividade" },
  { kind: "recipe_waste", label: "Desperdício" },
] as const;

export function reportKindLabel(kind: ReportKind): string {
  return REPORT_KINDS.find((entry) => entry.kind === kind)?.label ?? "Histórico";
}

/** Filtros da página de relatórios — espelham os query params da API. */
export interface ReportFiltersQuery {
  report_kind: ReportKind;
  date_from: string;
  date_to: string;
  recipe_ref: string;
  position_ref: string;
  operator_ref: string;
}

/** Query object da API de relatórios — omite filtros vazios (URLs limpas). */
export function reportsQuery(
  filters: ReportFiltersQuery,
): Record<string, string> {
  const query: Record<string, string> = {};
  for (const [key, value] of Object.entries(filters)) {
    if (value) query[key] = value;
  }
  return query;
}

/** Link direto do download CSV (mesmo endpoint, `format=csv`). O clique é um
 *  `<a href>` comum: o navegador baixa via BFF com a sessão do operador. */
export function reportsCsvUrl(filters: ReportFiltersQuery): string {
  const params = new URLSearchParams({ ...reportsQuery(filters), format: "csv" });
  return `/api/v1/backstage/production/reports/?${params.toString()}`;
}

/** Capacidade do dia em rótulo calmo: null = sem capacidade configurada. */
export function capacityLabel(capacityPercent: number | null): string {
  if (capacityPercent === null || capacityPercent === undefined) return "";
  return `${capacityPercent}%`;
}
