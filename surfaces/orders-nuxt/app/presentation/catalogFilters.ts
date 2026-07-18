// Recorte da matriz por dimensões (FilterBar) — puro e determinístico.
//
// A matriz já vem inteira do servidor (a coleção é o único recorte server-side, nas
// pills), então filtrar aqui é instantâneo e não custa request. Cada dimensão é um
// OU interno (marcar "erro" e "nunca" mostra os dois); entre dimensões é E.
import type { ActiveFilters, FilterDimension, FilterOption } from "../../../operator-kit/app/types/filters";
import type { CatalogRowProjection, SurfaceProjection } from "~/types/catalog";

// Ids das dimensões — chaves em inglês, rótulos em pt-BR (convenção do projeto).
export const FILTER_SYNC = "sync_status";
export const FILTER_SURFACE = "surface";
export const FILTER_PUBLISHED = "is_published";
export const FILTER_SELLABLE = "is_sellable";
export const FILTER_STOCK = "stock";
export const FILTER_PIM = "pim_complete";

// ── sync (produto × plataforma) ────────────────────────────────────────────────
// "never" = alvo de projeção que nunca recebeu push (sync_status vazio na célula).
export type SyncBucket = "synced" | "pending" | "error" | "never";

const SYNC_OPTIONS: { value: SyncBucket; label: string }[] = [
  { value: "synced", label: "Sincronizado" },
  { value: "pending", label: "Sincronizando" },
  { value: "error", label: "Com erro" },
  { value: "never", label: "Nunca enviado" },
];

function projectionRefs(surfaces: SurfaceProjection[]): Set<string> {
  return new Set(surfaces.filter((s) => s.is_projection_target).map((s) => s.ref));
}

function matchesSync(row: CatalogRowProjection, targets: Set<string>, buckets: string[]): boolean {
  return row.cells.some((cell) => {
    if (!cell.in_listing || !targets.has(cell.surface_ref)) return false;
    const bucket: SyncBucket = cell.sync_status === "" ? "never" : (cell.sync_status as SyncBucket);
    return buckets.includes(bucket);
  });
}

// ── estoque ────────────────────────────────────────────────────────────────────
// Um balde por linha (o produto está num estado só), do pior ao melhor.
export type StockBucket = "out" | "low" | "ok";

const STOCK_OPTIONS: { value: StockBucket; label: string }[] = [
  { value: "ok", label: "Em estoque" },
  { value: "low", label: "Estoque baixo" },
  { value: "out", label: "Esgotado" },
];

export function stockBucket(row: CatalogRowProjection): StockBucket {
  if (row.sold_out) return "out";
  if (row.low_stock) return "low";
  return "ok";
}

// ── dimensões ──────────────────────────────────────────────────────────────────
// As contagens são por opção ISOLADA, sobre as linhas já recortadas pela coleção e
// pela busca: dizem "quantos existem aqui", não "quantos sobram se eu marcar isto".

function counted<T extends string>(
  options: { value: T; label: string }[],
  rows: CatalogRowProjection[],
  matches: (row: CatalogRowProjection, value: T) => boolean,
): FilterOption[] {
  return options.map((o) => ({
    value: o.value,
    label: o.label,
    count: rows.filter((r) => matches(r, o.value)).length,
  }));
}

/**
 * Dimensões oferecidas no catálogo. NÃO inclui coleção: essa é o eixo primário e
 * vive nas pills (que também reordenam). Sync e PIM só aparecem quando há alguma
 * plataforma que projeta — sem iFood/Meta ligado, não há o que sincronizar.
 */
export function catalogDimensions(
  surfaces: SurfaceProjection[],
  rows: CatalogRowProjection[],
): FilterDimension[] {
  const targets = projectionRefs(surfaces);
  const hasTargets = targets.size > 0;
  const dimensions: FilterDimension[] = [];

  if (hasTargets) {
    dimensions.push({
      id: FILTER_SYNC,
      label: "Status de envio",
      type: "multi-select",
      options: counted(SYNC_OPTIONS, rows, (row, value) => matchesSync(row, targets, [value])),
    });
  }

  dimensions.push({
    id: FILTER_SURFACE,
    label: "Canal ou feed",
    type: "multi-select",
    options: surfaces.map((s) => ({
      value: s.ref,
      label: s.name,
      count: rows.filter((r) => r.cells.some((c) => c.surface_ref === s.ref && c.in_listing)).length,
    })),
  });

  dimensions.push(
    { id: FILTER_PUBLISHED, label: "Publicado", type: "boolean", options: [] },
    { id: FILTER_SELLABLE, label: "À venda", type: "boolean", options: [] },
    {
      id: FILTER_STOCK,
      label: "Estoque",
      type: "multi-select",
      options: counted(STOCK_OPTIONS, rows, (row, value) => stockBucket(row) === value),
    },
  );

  if (hasTargets) {
    dimensions.push({ id: FILTER_PIM, label: "Dados sociais completos", type: "boolean", options: [] });
  }

  return dimensions;
}

// ── aplicação ──────────────────────────────────────────────────────────────────

function asList(value: unknown): string[] {
  return Array.isArray(value) ? (value as string[]) : [];
}

export function matchesFilters(
  row: CatalogRowProjection,
  targets: Set<string>,
  filters: ActiveFilters,
): boolean {
  const sync = asList(filters[FILTER_SYNC]);
  if (sync.length && !matchesSync(row, targets, sync)) return false;

  const surfaceRefs = asList(filters[FILTER_SURFACE]);
  if (surfaceRefs.length && !row.cells.some((c) => c.in_listing && surfaceRefs.includes(c.surface_ref))) return false;

  const stock = asList(filters[FILTER_STOCK]);
  if (stock.length && !stock.includes(stockBucket(row))) return false;

  if (typeof filters[FILTER_PUBLISHED] === "boolean" && row.is_published !== filters[FILTER_PUBLISHED]) return false;
  if (typeof filters[FILTER_SELLABLE] === "boolean" && row.is_sellable !== filters[FILTER_SELLABLE]) return false;
  if (typeof filters[FILTER_PIM] === "boolean" && row.pim_complete !== filters[FILTER_PIM]) return false;

  return true;
}

export function filterByDimensions(
  rows: CatalogRowProjection[],
  surfaces: SurfaceProjection[],
  filters: ActiveFilters,
): CatalogRowProjection[] {
  const targets = projectionRefs(surfaces);
  return rows.filter((row) => matchesFilters(row, targets, filters));
}
