// Catalog matrix presentation — pure, deterministic transforms.
// The backend owns availability rules; this layer only groups/filters for display
// and maps semantic cell state → label + functional tone (color only where it means
// something: green = available, amber = paused, muted = absent/unpublished).
import type {
  CatalogRowProjection,
  SurfaceCellProjection,
  SurfaceProjection,
  SurfaceSyncStatus,
} from "~/types/catalog";

export type CellState = "available" | "paused" | "unpublished" | "absent";

export interface CellView {
  state: CellState;
  label: string;
  toneClass: string; // tailwind classes for the cell chip
}

// ── client-side search (rows already collection-scoped server-side) ────────────

export function filterRows(rows: CatalogRowProjection[], query: string): CatalogRowProjection[] {
  const q = query.trim().toLowerCase();
  if (!q) return rows;
  return rows.filter(
    (r) =>
      r.name.toLowerCase().includes(q) ||
      r.sku.toLowerCase().includes(q) ||
      r.keywords.some((k) => k.toLowerCase().includes(q)),
  );
}

// ── cell semantics ─────────────────────────────────────────────────────────────

export function cellState(row: CatalogRowProjection, cell: SurfaceCellProjection): CellState {
  if (!cell.in_listing) return "absent";
  // Product-level switches gate every surface; listing-level gates this one.
  const published = row.is_published && cell.is_published;
  const sellable = row.is_sellable && cell.is_sellable;
  if (published && sellable) return "available";
  if (!published) return "unpublished";
  return "paused";
}

const CELL_TONES: Record<CellState, string> = {
  available: "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  paused: "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300",
  unpublished: "border-border bg-muted text-muted-foreground",
  absent: "border-dashed border-border bg-transparent text-muted-foreground/60",
};

const CELL_LABELS: Record<CellState, string> = {
  available: "Disponível",
  paused: "Pausado",
  unpublished: "Despublicado",
  absent: "Não ofertado",
};

export function cellView(row: CatalogRowProjection, cell: SurfaceCellProjection): CellView {
  const state = cellState(row, cell);
  return { state, label: CELL_LABELS[state], toneClass: CELL_TONES[state] };
}

// ── status do produto (linha) — esmaecer + foto P&B quando está "fora" ─────────
// Um produto está fora quando NÃO está disponível em nenhum canal. `cell.available`
// já cruza produto × listing, então um único predicado cobre os três caminhos:
// despublicado, pausado no nível-produto (globalzinho), OU pausado célula a célula
// em todos os canais. Fonte única do esmaecimento/foto P&B (sem casos especiais).

export function availableAnywhere(row: CatalogRowProjection): boolean {
  return row.cells.some((c) => c.in_listing && c.available);
}

export interface RowStatus {
  off: boolean; // esmaecer a linha + foto P&B + nome tachado
  label: string; // selo (vazio = ativo)
  tone: "" | "muted" | "amber" | "danger";
}

// Escala de estados "fora", do mais deliberado ao mais urgente:
// Despublicado (cinza) · Pausado (âmbar) · Esgotado (vermelho/danger).
export function rowStatus(row: CatalogRowProjection): RowStatus {
  if (!row.is_published) return { off: true, label: "Despublicado", tone: "muted" };
  if (!row.is_sellable) return { off: true, label: "Pausado", tone: "amber" };
  // Esgotado = fato de ESTOQUE, ortogonal à pausa. Danger pra saltar à vista (cliente
  // não consegue comprar agora) e diferenciar do Pausado — mesmo repondo na fornada.
  // Vem antes de "Indisponível" porque o gate de pausa das células não enxerga estoque.
  if (row.sold_out) return { off: true, label: "Esgotado", tone: "danger" };
  const listed = row.cells.some((c) => c.in_listing);
  if (listed && !availableAnywhere(row)) return { off: true, label: "Indisponível", tone: "amber" };
  return { off: false, label: "", tone: "" };
}

// ── preço por célula: só mostra quando DIFERE do base ──────────────────────────
// O preço-base já vive na linha do produto. Repetir "R$ 13,00" em toda célula
// (markup 0) é ruído — a matriz vira um mapa de calor. Quando há override, o preço
// aparece com o sentido do delta (↑ acima / ↓ abaixo do base).

export type PriceDelta = "same" | "up" | "down";

export interface CellPriceView {
  delta: PriceDelta;
  differs: boolean; // preço da célula ≠ base do produto
  display: string; // "R$ 15,00"
}

export function cellPrice(
  row: CatalogRowProjection,
  cell: SurfaceCellProjection,
): CellPriceView {
  const price = cell.price_q ?? row.base_price_q;
  const base = row.base_price_q;
  const delta: PriceDelta = price > base ? "up" : price < base ? "down" : "same";
  return { delta, differs: delta !== "same", display: cell.price_display };
}

// ── ícone do canal (por ref) — header compacto da coluna ───────────────────────
const SURFACE_ICONS: Record<string, string> = {
  pdv: "lucide:store",
  web: "lucide:globe",
  whatsapp: "lucide:message-circle",
  ifood: "lucide:bike",
  delivery: "lucide:truck",
};

export function surfaceIcon(ref: string): string {
  return SURFACE_ICONS[ref] ?? "lucide:radio-tower";
}

// Ícone da coluna considerando o tipo: expositor traz a própria dica (tv/rss); canal
// resolve por ref. Fonte única do ícone de cabeçalho da matriz.
const SHOWCASE_ICONS: Record<string, string> = {
  tv: "lucide:tv",
  rss: "lucide:rss",
  monitor: "lucide:monitor",
};

export function surfaceDisplayIcon(surface: SurfaceProjection): string {
  if (!surface.transactional) return SHOWCASE_ICONS[surface.icon] ?? "lucide:tv";
  return surfaceIcon(surface.ref);
}

// Rótulo curto do papel da superfície (chip no cabeçalho). Canal não recebe chip
// (é o caso comum); expositor deixa explícito que EXIBE e não vende.
export function surfaceKindLabel(surface: SurfaceProjection): string {
  if (surface.transactional) return "";
  return surface.kind === "feed" ? "Feed" : "Expositor";
}

// ── surface metadata ─────────────────────────────────────────────────────────

const SYNC: Record<SurfaceSyncStatus, { label: string; toneClass: string } | null> = {
  ok: { label: "sincronizado", toneClass: "text-emerald-600 dark:text-emerald-400" },
  error: { label: "erro de sync", toneClass: "text-destructive" },
  never: { label: "nunca sincronizado", toneClass: "text-amber-600 dark:text-amber-400" },
  na: null, // não é alvo de projeção → sem badge
};

export function syncBadge(status: SurfaceSyncStatus): { label: string; toneClass: string } | null {
  return SYNC[status];
}
