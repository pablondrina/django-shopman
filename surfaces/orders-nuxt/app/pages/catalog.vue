<script setup lang="ts">
// Catalog matrix — produto × canal. The catalog side of the Gestor hub.
// Design: a glanceable availability heatmap (tinted cells) with one-click pause and
// inline reprice per cell; the collection axis (chips) scopes the view; selection +
// a floating bulk bar act on the active recorte. Desktop-first, horizontal scroll on
// narrow screens. The backend owns availability rules; this renders intent + reconciles.
import { cellPrice, cellSyncView, cellView, filterRows, rowStatus, surfaceDisplayIcon, surfaceKindLabel, syncBadge, syncErrorCount } from "~/presentation/catalog";
import { catalogDimensions, filterByDimensions } from "~/presentation/catalogFilters";
import { keepVisible, reconcile } from "../../../operator-kit/app/presentation/columnPicker";
import type { HiddenColumns } from "../../../operator-kit/app/types/columns";
import type { ActiveFilters } from "../../../operator-kit/app/types/filters";
import type {
  AssistableField,
  CatalogRowProjection,
  CollectionProjection,
  ProductDetailPatch,
  ProductDetailProjection,
  SurfaceCellProjection,
} from "~/types/catalog";

const collectionRef = ref("");
const {
  matrix, pending, error, refresh, isBusy, cellKey, productKey, detailKey, setCell, setProduct, bulkSet, bulkPrice,
  resync, fetchProductDetail, saveProductDetail, reorderCollections, reorderItems, bulkBusy,
  aiAssist, aiAssistKey,
} = useCatalogMatrix(collectionRef);

const surfaces = computed(() => matrix.value?.surfaces ?? []);
const collections = computed(() => matrix.value?.collections ?? []);
// Superfícies = canais (transacionam) + feeds (só empurram dados). Índice p/ a
// célula saber o papel da coluna e onde começa a banda de feeds. No backend o model
// do feed chama-se ``Showcase`` — daí os nomes internos aqui.
const surfaceByRef = computed(() => new Map(surfaces.value.map((s) => [s.ref, s])));
const isCellTransactional = (cell: SurfaceCellProjection) => surfaceByRef.value.get(cell.surface_ref)?.transactional ?? true;

// ── colunas visíveis (ColumnPicker) ────────────────────────────────────────────
// A escolha é do operador e vale por estação. Cookie (não localStorage) pelo mesmo
// motivo do rail: a matriz é renderizada no servidor (`server: true` no useFetch),
// então o servidor já precisa saber quais colunas desenhar — senão a tela nasce com
// todas e pisca ao hidratar. Guardamos as OCULTAS: canal/feed novo nasce visível.
const hiddenColumns = useCookie<HiddenColumns>("catalog-hidden-columns", {
  default: () => [],
  sameSite: "lax",
  maxAge: 60 * 60 * 24 * 365,
  path: "/",
});
// Só as superfícies entram no seletor — a coluna do produto não é declarada, e é por
// isso que ela não tem como ser ocultada.
const columnOptions = computed(() => surfaces.value.map((s) => ({ id: s.ref, label: s.name })));
// Higieniza contra superfície que sumiu do servidor (senão o registro vira lixo).
const hidden = computed<HiddenColumns>(() => reconcile(columnOptions.value, hiddenColumns.value));
const visibleSurfaces = computed(() => keepVisible(surfaces.value, hidden.value, (s) => s.ref));
const visibleCells = (row: CatalogRowProjection) => keepVisible(row.cells, hidden.value, (c) => c.surface_ref);
// A divisória da banda de feeds acompanha o recorte: cai no primeiro feed VISÍVEL.
const firstShowcaseRef = computed(() => visibleSurfaces.value.find((s) => !s.transactional)?.ref ?? "");
const channelsCount = computed(() => surfaces.value.filter((s) => s.transactional).length);
const showcasesCount = computed(() => surfaces.value.filter((s) => !s.transactional).length);
const query = ref("");
// Recorte por dimensões (envio, canal, publicação, venda, estoque, PIM). A coleção
// fica FORA: é o eixo primário, mora nas pills (que também reordenam) e recorta no
// servidor. Aqui é tudo client-side — a matriz já veio inteira.
const filters = ref<ActiveFilters>({});
const searched = computed<CatalogRowProjection[]>(() => filterRows(matrix.value?.rows ?? [], query.value));
// As contagens das opções são lidas sobre o resultado da BUSCA (antes dos filtros),
// senão marcar uma opção zeraria as contagens das outras.
const dimensions = computed(() => catalogDimensions(surfaces.value, searched.value));
const rows = computed<CatalogRowProjection[]>(
  () => filterByDimensions(searched.value, surfaces.value, filters.value),
);
// status por linha (esmaecer/foto P&B/selo) computado uma vez por refresh.
const rowStatuses = computed(() => Object.fromEntries(rows.value.map((r) => [r.sku, rowStatus(r)])));
// há alguma superfície que projeta? (iFood/Meta/…) — gateia a UI de sync/PIM.
const hasProjectionTargets = computed(() => surfaces.value.some((s) => s.is_projection_target));
const activeCollection = computed(() => collections.value.find((c) => c.ref === collectionRef.value) ?? null);
const loading = computed(() => pending.value && !matrix.value);

// zoom da foto (clique na thumbnail amplia num lightbox)
const zoom = ref<{ url: string; name: string } | null>(null);

// ── reordenar coleções (pills arrastáveis) ─────────────────────────────────────
// Override = null → ordem do servidor (determinístico p/ SSR); só é setado durante o
// drag otimista, e zerado após o POST+refresh (que já vem reordenado).
function reorderView<T extends { ref?: string; sku?: string }>(
  server: T[], override: string[] | null, key: (t: T) => string,
): T[] {
  if (!override) return server;
  const byKey = new Map(server.map((t) => [key(t), t]));
  const out = override.map((k) => byKey.get(k)).filter(Boolean) as T[];
  return out.length === server.length ? out : server;
}

const collectionOverride = ref<string[] | null>(null);
const orderedCollections = computed(
  () => reorderView<CollectionProjection>(collections.value, collectionOverride.value, (c) => c.ref),
);
const {
  dragKey: collDragKey, onPointerDown: collPointerDown,
} = useDragReorder(
  () => orderedCollections.value.map((c) => c.ref),
  (order) => {
    collectionOverride.value = order;
    reorderCollections(order).finally(() => { collectionOverride.value = null; });
  },
);

// ── reordenar produtos (handle na linha) — só numa coleção MANUAL, sem busca ────
// Arrastar só faz sentido sobre a coleção INTEIRA: com busca ou filtro ativo a lista
// é um recorte, e a ordem gravada sairia errada.
const canReorderRows = computed(
  () => collectionRef.value !== ""
    && !activeCollection.value?.is_smart
    && query.value.trim() === ""
    && Object.keys(filters.value).length === 0,
);
const rowOverride = ref<string[] | null>(null);
const orderedRows = computed(
  () => reorderView<CatalogRowProjection>(rows.value, rowOverride.value, (r) => r.sku),
);
const displayRows = computed(() => (canReorderRows.value ? orderedRows.value : rows.value));
const {
  dragKey: rowDragKey, overKey: rowOverKey, onPointerDown: rowPointerDown,
} = useDragReorder(
  () => displayRows.value.map((r) => r.sku),
  (order) => {
    rowOverride.value = order;
    reorderItems(collectionRef.value, order).finally(() => { rowOverride.value = null; });
  },
);

// ── selection + floating bulk bar (acts on the active recorte) ─────────────────
const selected = ref<Set<string>>(new Set());
const isSelected = (sku: string) => selected.value.has(sku);
function toggleSelect(sku: string) {
  const next = new Set(selected.value);
  if (next.has(sku)) next.delete(sku);
  else next.add(sku);
  selected.value = next;
}
const visibleSkus = computed(() => rows.value.map((r) => r.sku));
const allSelected = computed(() => visibleSkus.value.length > 0 && visibleSkus.value.every((s) => selected.value.has(s)));
function toggleSelectAll() {
  selected.value = allSelected.value ? new Set() : new Set(visibleSkus.value);
}
function clearSelection() { selected.value = new Set(); }
watch(collectionRef, clearSelection);

const bulkSurface = ref("");
watchEffect(() => { if (!bulkSurface.value && surfaces.value.length) bulkSurface.value = surfaces.value[0]!.ref; });
// Feed só pausa/reativa em lote — sem publicar/reprecificar (não transaciona).
const bulkSurfaceIsShowcase = computed(() => {
  const s = surfaceByRef.value.get(bulkSurface.value);
  return !!s && !s.transactional;
});
const channelSurfaces = computed(() => surfaces.value.filter((s) => s.transactional));
const showcaseSurfaces = computed(() => surfaces.value.filter((s) => !s.transactional));
async function bulk(patch: { is_sellable?: boolean; is_published?: boolean }) {
  if (!bulkSurface.value || selected.value.size === 0) return;
  await bulkSet(bulkSurface.value, { skus: [...selected.value] }, patch);
  clearSelection();
}

// ── reprecificação em lote (popover) ───────────────────────────────────────────
const priceOpen = ref(false);
const priceOp = ref<"set" | "pct" | "delta">("pct");
const priceOps = [
  { k: "set", l: "Definir" },
  { k: "pct", l: "Ajustar %" },
  { k: "delta", l: "Ajustar R$" },
] as const;
const priceInputBulk = ref("");
const surfaceLabel = (ref_: string) =>
  ref_ === "*" ? "Todos os canais" : (surfaces.value.find((s) => s.ref === ref_)?.name ?? ref_);
// número digitado (aceita vírgula/percentual/negativo); em centavos p/ set/delta.
function parsedPriceValue(): number | null {
  const raw = priceInputBulk.value.replace(/[^0-9,.-]/g, "").replace(/\./g, "").replace(",", ".");
  const n = Number.parseFloat(raw);
  if (!Number.isFinite(n)) return null;
  return priceOp.value === "pct" ? Math.round(n) : Math.round(n * 100);
}
const priceValid = computed(() => {
  const v = parsedPriceValue();
  return v !== null && (priceOp.value !== "set" || v >= 0);
});
async function applyBulkPrice() {
  const value = parsedPriceValue();
  if (value === null || !bulkSurface.value || selected.value.size === 0) return;
  await bulkPrice(bulkSurface.value, { skus: [...selected.value] }, { op: priceOp.value, value });
  priceOpen.value = false;
  priceInputBulk.value = "";
  clearSelection();
}

// ── product-level actions ("globalzinho" + publish) — via menu ⋯ da linha ───────
function toggleProduct(row: CatalogRowProjection) {
  setProduct(row.sku, { is_sellable: !row.is_sellable });
  menuOpen.value = null;
}
function toggleProductPublish(row: CatalogRowProjection) {
  setProduct(row.sku, { is_published: !row.is_published });
  menuOpen.value = null;
}

// row actions menu (⋯) — casa das ações menos corriqueiras (editar, pausar tudo,
// (des)publicar). Um menu por vez; keyed por sku.
const menuOpen = ref<string | null>(null);

// host do Django (não o do Gestor) — usado nos deep-links de saída dos feeds.
const djangoBase = useRuntimeConfig().public.djangoPublicBaseUrl as string;

// ── cell pause/resume + inline reprice ─────────────────────────────────────────
// A pausa por célula vale para canal (vende) e feed (só exibe). No feed o backend
// grava em Showcase.options[paused_skus]; aqui é o mesmo gesto.
const surfaceWord = (cell: SurfaceCellProjection) => (isCellTransactional(cell) ? "canal" : "feed");
function toggleCell(row: CatalogRowProjection, cell: SurfaceCellProjection) {
  if (!cell.in_listing) return;
  setCell(row.sku, cell.surface_ref, { is_sellable: !cell.is_sellable });
}
const editing = ref<{ sku: string; surface: string } | null>(null);
const priceInput = ref("");
function startEdit(row: CatalogRowProjection, cell: SurfaceCellProjection) {
  if (!cell.in_listing) return;
  editing.value = { sku: row.sku, surface: cell.surface_ref };
  priceInput.value = ((cell.price_q ?? 0) / 100).toFixed(2).replace(".", ",");
}
const isEditing = (sku: string, surface: string) => editing.value?.sku === sku && editing.value?.surface === surface;
function parseBrl(text: string): number | null {
  const cleaned = text.replace(/[^0-9,.-]/g, "").replace(/\./g, "").replace(",", ".");
  const value = Number.parseFloat(cleaned);
  return Number.isFinite(value) && value >= 0 ? Math.round(value * 100) : null;
}
async function commitPrice(row: CatalogRowProjection, cell: SurfaceCellProjection) {
  const price_q = parseBrl(priceInput.value);
  editing.value = null;
  if (price_q === null || price_q === cell.price_q) return;
  await setCell(row.sku, cell.surface_ref, { price_q });
}

// nome do canal (para o rótulo do popover de preço) + tooltip do valor no ícone $.
const surfaceName = (ref: string) => surfaces.value.find((s) => s.ref === ref)?.name ?? ref;
function priceTitle(row: CatalogRowProjection, cell: SurfaceCellProjection): string {
  const p = cellPrice(row, cell);
  return p.differs
    ? `${cell.price_display} · ${p.delta === "up" ? "acima" : "abaixo"} do base`
    : cell.price_display;
}

// ── sync por célula + PIM (Arc H) ──────────────────────────────────────────────
// Selo de sync por (produto × plataforma): resolve a superfície p/ saber se projeta.
const cellSync = (cell: SurfaceCellProjection) => cellSyncView(surfaceByRef.value.get(cell.surface_ref), cell);
const rowSyncErrors = (row: CatalogRowProjection) => syncErrorCount(row, surfaces.value);
function resyncCell(row: CatalogRowProjection, cell: SurfaceCellProjection) {
  resync(row.sku, cell.surface_ref);
}
function resyncRow(row: CatalogRowProjection) {
  resync(row.sku);
  menuOpen.value = null;
}

// painel de produto (edição completa) — abre pelo menu ⋯ da linha. A matriz não
// carrega os campos longos: buscamos o detalhe sob demanda ao abrir. Os dados
// sociais (PIM) são uma ABA daqui: o produto é um só, e antes eram dois painéis
// que salvavam pedaços diferentes do mesmo registro.
const detailSku = ref<string | null>(null);
const detail = ref<ProductDetailProjection | null>(null);
const detailLoading = ref(false);
const detailTab = ref("geral");
async function openDetail(row: CatalogRowProjection, tab = "geral") {
  menuOpen.value = null;
  detailTab.value = tab;
  detailSku.value = row.sku;
  detail.value = null;
  detailLoading.value = true;
  try {
    detail.value = await fetchProductDetail(row.sku);
  } finally {
    detailLoading.value = false;
  }
}
function closeDetail() {
  detailSku.value = null;
  detail.value = null;
}
async function saveDetail(patch: ProductDetailPatch) {
  if (!detailSku.value) return;
  const ok = await saveProductDetail(detailSku.value, patch);
  if (ok) closeDetail();
}

// assist de IA — o painel é presentacional, então a página injeta a chamada e o
// predicado de ocupado.
function assistFor(sku: Ref<string | null>) {
  return {
    assist: (field: AssistableField, currentValue: string) =>
      sku.value ? aiAssist(sku.value, field, currentValue) : Promise.resolve(""),
    assistBusy: (field: AssistableField) => (sku.value ? isBusy(aiAssistKey(sku.value, field)) : false),
  };
}
const detailAssist = assistFor(detailSku);

useHead({ title: "Catálogo · Gestor" });
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col">
    <!-- work toolbar: search · collection chips · counts/refresh -->
    <UiToolbar>
      <UiSearchInput v-model="query" placeholder="Buscar produto ou SKU…" aria-label="Buscar produto ou SKU" />
      <!-- recorte por dimensões (envio, canal, publicação, venda, estoque, PIM) —
           ao lado da busca; a coleção continua nas pills, que também reordenam. -->
      <FilterBar v-model="filters" :dimensions="dimensions" />
      <!-- quais canais/feeds aparecem como coluna; a do produto nunca some (não é
           declarada no seletor). A escolha persiste por estação. -->
      <ColumnPicker v-if="surfaces.length" v-model="hiddenColumns" :columns="columnOptions" />
      <!-- coleções: arraste os chips para reordenar as seções da vitrine (Collection.sort_order) -->
      <TransitionGroup v-if="collections.length" name="chip" tag="div" class="flex flex-wrap items-center gap-1.5">
        <UiFilterChip key="__all" :active="collectionRef === ''" @click="collectionRef = ''">Todas</UiFilterChip>
        <UiFilterChip
          v-for="c in orderedCollections"
          :key="c.ref"
          :data-dragkey="c.ref"
          class="cursor-grab touch-none transition-[opacity,box-shadow] active:cursor-grabbing"
          :class="collDragKey === c.ref ? 'opacity-50 shadow-md' : ''"
          :active="collectionRef === c.ref"
          :count="c.product_count"
          @click="collectionRef = c.ref"
          @pointerdown="collPointerDown(c.ref, $event)"
        >
          <template v-if="c.is_smart" #icon>
            <Icon name="lucide:sparkles" class="size-3.5 opacity-70" title="Coleção por regra" />
          </template>
          {{ c.name }}
        </UiFilterChip>
      </TransitionGroup>

      <template #end>
        <p class="hidden text-xs text-muted-foreground sm:block">
          <span class="tabular-nums">{{ rows.length }}</span> produto{{ rows.length === 1 ? "" : "s" }}
          <span class="text-muted-foreground/50">·</span>
          <span class="tabular-nums">{{ channelsCount }}</span> {{ channelsCount === 1 ? "canal" : "canais" }}
          <template v-if="showcasesCount">
            <span class="text-muted-foreground/50">·</span>
            <span class="tabular-nums">{{ showcasesCount }}</span> feed{{ showcasesCount === 1 ? "" : "s" }}
          </template>
        </p>
        <UiIconButton icon="lucide:refresh-cw" label="Atualizar" :spinning="pending" @click="refresh()" />
      </template>
    </UiToolbar>

    <section class="flex min-h-0 flex-1 flex-col gap-4 p-4">
      <p v-if="error" class="rounded-xl border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
        Não foi possível carregar o catálogo. <button class="underline" @click="refresh()">Tentar de novo</button>
      </p>

      <!-- matrix -->
      <div v-if="loading" class="overflow-hidden rounded-xl border border-border bg-card">
      <div v-for="i in 8" :key="i" class="flex items-center gap-3 border-b border-border px-4 py-3 last:border-0">
        <div class="size-10 animate-pulse rounded-md bg-muted"></div>
        <div class="h-4 w-40 animate-pulse rounded bg-muted"></div>
        <div class="ml-auto flex gap-2">
          <div v-for="j in 6" :key="j" class="h-8 w-[76px] animate-pulse rounded-md bg-muted"></div>
        </div>
      </div>
    </div>

    <div v-else-if="rows.length" class="min-h-0 flex-1 overflow-auto rounded-xl border border-border bg-card shadow-xs">
      <!-- `table-fixed`: sem ele o conteúdo do cabeçalho (nome longo do canal, rótulo
           do feed) estica a coluna e a matriz fica desalinhada. Fixo, toda superfície
           tem a MESMA largura e o nome trunca com o title inteiro. O `min-w` faz a
           tabela rolar em tela estreita em vez de espremer a coluna do produto. -->
      <table class="w-full min-w-[1024px] table-fixed border-separate border-spacing-0 text-sm">
        <thead>
          <tr>
            <!-- Produto: `w-full` faz esta coluna absorver toda a folga da tabela, então
                 as colunas de superfície ficam no seu tamanho fixo (uniformes).
                 `border-r` fecha a coluna fixa: no scroll horizontal é essa linha que
                 diz onde o painel parado termina e a matriz que corre começa. -->
            <th class="sticky left-0 top-0 z-30 w-full min-w-[260px] border-b border-r border-border bg-card px-4 py-3 text-left">
              <label class="flex items-center gap-3">
                <input type="checkbox" :checked="allSelected" class="size-4 rounded border-border accent-foreground" @change="toggleSelectAll" />
                <span class="text-xs font-medium uppercase tracking-wide text-muted-foreground">Produto</span>
              </label>
            </th>
            <!-- Superfícies: largura fixa e uniforme (canais + feeds). O que faz caberem
                 num desktop sem scroll é o NOME CURTO vindo do backend (short_name:
                 "Site", "Meta", "TV1"); o nome completo fica no title. -->
            <th
              v-for="s in visibleSurfaces"
              :key="s.ref"
              class="sticky top-0 z-20 w-[114px] border-b border-border bg-card px-2 py-2 text-left align-top"
              :class="firstShowcaseRef === s.ref ? 'border-l-2 border-l-primary/40' : 'border-l border-l-border'"
            >
              <div class="flex flex-col gap-0.5" :class="{ 'opacity-45': !s.transactional && !s.is_active }">
                <span class="flex items-center gap-1 font-medium text-foreground" :title="s.transactional ? s.name : `${s.name} — feed (não vende)`">
                  <Icon :name="surfaceDisplayIcon(s)" class="size-3.5 shrink-0" :class="s.transactional ? 'text-muted-foreground' : 'text-primary/70'" />
                  <span class="truncate text-xs">{{ s.short_name }}</span>
                </span>
                <span class="flex items-center gap-1">
                  <span
                    v-if="syncBadge(s.sync_status)" class="truncate text-[11px] font-medium leading-tight"
                    :class="syncBadge(s.sync_status)!.toneClass" :title="syncBadge(s.sync_status)!.title"
                  >● {{ syncBadge(s.sync_status)!.label }}</span>
                  <span v-else-if="!s.transactional" class="truncate text-[11px] font-medium leading-tight text-primary/60">
                    {{ surfaceKindLabel(s) }}{{ s.is_active ? "" : " · pausado" }}
                  </span>
                  <a
                    v-if="s.output_path"
                    :href="`${djangoBase}${s.output_path}`" target="_blank" rel="noopener"
                    class="ml-auto shrink-0 text-muted-foreground/50 transition hover:text-foreground"
                    :title="`Abrir ${s.name}`" @click.stop
                  ><Icon name="lucide:external-link" class="size-3" /></a>
                </span>
              </div>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in displayRows"
            :key="row.sku"
            :data-dragkey="row.sku"
            class="group transition-[opacity,box-shadow]"
            :class="[
              rowDragKey === row.sku ? 'opacity-40' : '',
              rowDragKey && rowOverKey === row.sku && rowDragKey !== row.sku ? 'shadow-[inset_0_2px_0_0_var(--color-primary)]' : '',
            ]"
          >
            <!-- product -->
            <!-- Fundo OPACO, sempre: a coluna fica parada enquanto as células passam por
                 baixo, e tinta translúcida (bg-muted/40) deixaria o conteúdo em trânsito
                 aparecer através dela. Um único utilitário de fundo por estado — dois na
                 mesma célula competem na folha de estilo, não na ordem do atributo. -->
            <td
              class="sticky left-0 z-10 border-b border-r border-border px-4 py-2.5"
              :class="isSelected(row.sku) ? 'bg-muted' : 'bg-card group-hover:bg-muted'"
            >
              <div class="flex items-center gap-3">
                <!-- handle de arrastar (pointer events): aparece só quando a coleção ativa é reordenável -->
                <span
                  v-if="canReorderRows"
                  role="button" tabindex="0"
                  class="-ml-1 grid size-6 shrink-0 cursor-grab touch-none select-none place-items-center rounded text-muted-foreground/50 transition hover:text-foreground active:cursor-grabbing"
                  aria-label="Arrastar para reordenar"
                  title="Arrastar para reordenar nesta coleção"
                  @pointerdown="rowPointerDown(row.sku, $event)"
                  @click.stop
                >
                  <Icon name="lucide:grip-vertical" class="pointer-events-none size-4" />
                </span>
                <label class="flex min-w-0 flex-1 items-center gap-3">
                  <input type="checkbox" :checked="isSelected(row.sku)" class="size-4 shrink-0 rounded border-border accent-foreground" @change="toggleSelect(row.sku)" />
                  <!-- thumbnail: esmaece + P&B quando "fora"; clique amplia a foto -->
                  <img
                    v-if="row.image_url" :src="row.image_url" :alt="row.name"
                    class="size-10 shrink-0 cursor-zoom-in rounded-md object-cover ring-1 ring-border transition hover:ring-2 hover:ring-primary/50"
                    :class="rowStatuses[row.sku]?.off ? 'opacity-50 grayscale' : ''"
                    @click.stop.prevent="zoom = { url: row.image_url, name: row.name }"
                  />
                  <div v-else class="grid size-10 shrink-0 place-items-center rounded-md bg-muted text-muted-foreground"><Icon name="lucide:image-off" class="size-4" /></div>
                  <div class="flex min-w-0 flex-col">
                    <span class="flex items-center gap-1.5 truncate font-medium" :class="rowStatuses[row.sku]?.off ? 'text-muted-foreground' : 'text-foreground'">
                      <span class="truncate" :class="rowStatuses[row.sku]?.off ? 'line-through decoration-1' : ''">{{ row.name }}</span>
                      <span
                        v-if="rowStatuses[row.sku]?.label"
                        class="shrink-0 rounded-full px-1.5 py-0.5 text-xs font-medium"
                        :class="{
                          'bg-destructive/10 text-destructive': rowStatuses[row.sku]?.tone === 'danger',
                          'bg-warning/15 text-amber-600 dark:text-amber-400': rowStatuses[row.sku]?.tone === 'amber',
                          'bg-muted text-muted-foreground': rowStatuses[row.sku]?.tone === 'muted',
                        }"
                      >{{ rowStatuses[row.sku]?.label }}</span>
                      <!-- esgotado que repõe por produção: a próxima fornada reativa sozinha -->
                      <span v-if="row.sold_out && row.replenish_qty" class="shrink-0 text-xs font-normal text-muted-foreground">repõe {{ row.replenish_qty }} na fornada</span>
                      <!-- estoque baixo (produto ainda ativo): aviso discreto -->
                      <span v-else-if="!rowStatuses[row.sku]?.off && row.low_stock" class="shrink-0 rounded-full bg-warning/15 px-1.5 py-0.5 text-xs font-medium text-amber-600 dark:text-amber-400">resta {{ row.stock_qty }}</span>
                      <!-- sync com erro em N plataforma(s): salta à vista + atalho p/ reenviar tudo -->
                      <button
                        v-if="rowSyncErrors(row)"
                        type="button"
                        class="inline-flex shrink-0 items-center gap-1 rounded-full bg-destructive/10 px-1.5 py-0.5 text-xs font-medium text-destructive transition hover:bg-destructive/20 disabled:opacity-50"
                        :disabled="isBusy(productKey(row.sku))"
                        :title="`Erro de sync em ${rowSyncErrors(row)} plataforma(s) — reenviar tudo`"
                        @click.stop="resyncRow(row)"
                      >
                        <Icon name="lucide:triangle-alert" class="size-3" /> {{ rowSyncErrors(row) }}
                      </button>
                    </span>
                    <!-- uma linha só: com a coluna em largura fixa, sem `nowrap` o SKU +
                         preço + coleção quebram e a linha da matriz cresce. -->
                    <span class="flex items-center gap-1.5 overflow-hidden whitespace-nowrap text-xs text-muted-foreground">
                      <span class="shrink-0 font-mono">{{ row.sku }}</span>
                      <span class="shrink-0 text-muted-foreground/40">·</span>
                      <span class="shrink-0 tabular-nums">{{ row.base_price_display }}</span>
                      <span v-if="row.primary_collection_name" class="truncate rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">{{ row.primary_collection_name }}</span>
                    </span>
                  </div>
                </label>
                <!-- menu ⋯ da linha: casa das ações menos corriqueiras (editar, pausar tudo, publicar) -->
                <UiPopover :open="menuOpen === row.sku" @update:open="(v) => (menuOpen = v ? row.sku : null)">
                  <UiPopoverTrigger as-child>
                    <button
                      type="button"
                      class="grid size-8 shrink-0 place-items-center rounded-md text-muted-foreground transition hover:bg-accent hover:text-foreground"
                      :class="menuOpen === row.sku ? 'bg-accent text-foreground' : ''"
                      :aria-label="`Ações de ${row.name}`"
                    >
                      <Icon name="lucide:ellipsis-vertical" class="size-4" />
                    </button>
                  </UiPopoverTrigger>
                  <UiPopoverContent align="end" :side-offset="4" class="w-56 p-1">
                    <button
                      type="button"
                      class="flex w-full items-center gap-2 rounded px-3 py-2 text-left text-sm transition hover:bg-accent"
                      @click="openDetail(row)"
                    >
                      <Icon name="lucide:pencil" class="size-4 text-muted-foreground" /> Editar detalhes
                    </button>
                    <button
                      type="button" :disabled="isBusy(productKey(row.sku))"
                      class="flex w-full items-center gap-2 rounded px-3 py-2 text-left text-sm transition hover:bg-accent disabled:opacity-50"
                      @click="toggleProduct(row)"
                    >
                      <Icon :name="row.is_sellable ? 'lucide:pause' : 'lucide:play'" class="size-4 text-muted-foreground" />
                      {{ row.is_sellable ? "Pausar em todos os canais" : "Reativar em todos os canais" }}
                    </button>
                    <button
                      type="button" :disabled="isBusy(productKey(row.sku))"
                      class="flex w-full items-center gap-2 rounded px-3 py-2 text-left text-sm transition hover:bg-accent disabled:opacity-50"
                      @click="toggleProductPublish(row)"
                    >
                      <Icon :name="row.is_published ? 'lucide:eye-off' : 'lucide:eye'" class="size-4 text-muted-foreground" />
                      {{ row.is_published ? "Despublicar do catálogo" : "Publicar no catálogo" }}
                    </button>
                    <!-- PIM + sync (só quando há plataforma que projeta) -->
                    <template v-if="hasProjectionTargets">
                    <div class="my-1 h-px bg-border"></div>
                    <button
                      type="button"
                      class="flex w-full items-center gap-2 rounded px-3 py-2 text-left text-sm transition hover:bg-accent"
                      @click="openDetail(row, 'social')"
                    >
                      <Icon name="lucide:sparkles" class="size-4 text-muted-foreground" />
                      Dados para redes sociais
                      <span
                        v-if="!row.pim_complete"
                        class="ml-auto rounded-full bg-warning/15 px-1.5 py-0.5 text-xs font-medium text-amber-600 dark:text-amber-400"
                      >incompleto</span>
                    </button>
                    <button
                      type="button" :disabled="isBusy(productKey(row.sku))"
                      class="flex w-full items-center gap-2 rounded px-3 py-2 text-left text-sm transition hover:bg-accent disabled:opacity-50"
                      @click="resyncRow(row)"
                    >
                      <Icon name="lucide:refresh-cw" class="size-4 text-muted-foreground" />
                      Reenviar às plataformas
                    </button>
                    </template>
                  </UiPopoverContent>
                </UiPopover>
              </div>
            </td>
            <!-- cells (heatmap). Banda de feeds começa com uma divisória mais forte.
                 Toggle · preço · selo de sync ficam LADO A LADO numa linha só: são três
                 coisas que o operador lê de relance, e empilhar não é o jeito de ganhar
                 largura — quem resolve isso é o nome curto da coluna (surface.short_name). -->
            <td
              v-for="cell in visibleCells(row)"
              :key="cell.surface_ref"
              class="border-b border-border px-1 py-1.5 group-hover:bg-muted/20"
              :class="firstShowcaseRef === cell.surface_ref ? 'border-l-2 border-l-primary/40' : 'border-l border-l-border'"
            >
              <div
                v-if="cell.in_listing"
                class="flex h-10 items-center justify-center gap-1"
              >
                <!-- ÁREA 1 — toggle: verde=ligado&disponível · cinza=pausado (posição off) OU
                     linha "fora" (esgotado/etc.: mantém a POSIÇÃO ligada, mas dessatura p/ cinza).
                     Vale para canal (vende) E feed (só exibe) — a mesma pausa por item. -->
                <button
                  type="button" role="switch" :aria-checked="cell.is_sellable"
                  class="relative inline-flex h-4 w-7 shrink-0 items-center rounded-full transition-colors disabled:opacity-40"
                  :class="cell.is_sellable && !rowStatuses[row.sku]?.off ? 'bg-success' : 'bg-muted-foreground/30'"
                  :disabled="isBusy(cellKey(row.sku, cell.surface_ref))"
                  :aria-label="cell.is_sellable ? `${cellView(row, cell).label} — pausar neste ${surfaceWord(cell)}` : `Reativar neste ${surfaceWord(cell)}`"
                  :title="cell.is_sellable ? `${cellView(row, cell).label} — pausar neste ${surfaceWord(cell)}` : `Pausado — reativar neste ${surfaceWord(cell)}`"
                  @click="toggleCell(row, cell)"
                >
                  <span class="inline-block size-3 rounded-full bg-white shadow-sm transition-transform" :class="cell.is_sellable ? 'translate-x-3.5' : 'translate-x-0.5'"></span>
                </button>

                <!-- Feed não vende: sem divisória nem preço — só a pausa por item. -->
                <template v-if="isCellTransactional(cell)">
                <!-- divisória: deixa claro que toggle e preço são controles distintos -->
                <div class="h-5 w-px shrink-0 bg-border"></div>

                <!-- ÁREA 2 — preço, ao lado do toggle: base = ícone $ apagado; ALTERADO =
                     seta ↑/↓ colorida + valor. title = valor; clique = popover. -->
                <UiPopover :open="isEditing(row.sku, cell.surface_ref)" @update:open="(v) => { if (!v) editing = null }">
                  <UiPopoverAnchor as-child>
                    <button
                      type="button"
                      class="flex items-center rounded px-0.5 py-0.5 leading-none transition hover:bg-muted disabled:opacity-40"
                      :disabled="isBusy(cellKey(row.sku, cell.surface_ref))"
                      :title="priceTitle(row, cell)"
                      :aria-label="`Preço em ${surfaceName(cell.surface_ref)}: ${cell.price_display} — editar`"
                      @click="startEdit(row, cell)"
                    >
                      <span v-if="cellPrice(row, cell).differs" class="flex items-center gap-0.5">
                        <Icon
                          :name="cellPrice(row, cell).delta === 'up' ? 'lucide:arrow-up' : 'lucide:arrow-down'"
                          class="size-2.5 shrink-0"
                          :class="rowStatuses[row.sku]?.off
                            ? 'text-muted-foreground/60'
                            : (cellPrice(row, cell).delta === 'up' ? 'text-amber-600 dark:text-amber-400' : 'text-success dark:text-lime-400')"
                        />
                        <span class="text-[11px] font-semibold tabular-nums" :class="cell.is_sellable ? 'text-foreground' : 'text-muted-foreground line-through'">{{ cell.price_display.replace("R$ ", "") }}</span>
                      </span>
                      <Icon v-else name="lucide:circle-dollar-sign" class="size-3.5 text-muted-foreground/40" />
                    </button>
                  </UiPopoverAnchor>
                  <UiPopoverContent align="center" :side-offset="6" class="w-52 p-3">
                    <p class="mb-2 text-xs font-medium text-muted-foreground">Preço · {{ surfaceName(cell.surface_ref) }}</p>
                    <input
                      v-model="priceInput" type="text" inputmode="decimal" autofocus
                      class="h-9 w-full rounded-md border bg-background px-2.5 text-sm tabular-nums outline-none focus:ring-1 focus:ring-ring"
                      @keyup.enter="commitPrice(row, cell)" @keyup.esc="editing = null"
                    />
                    <p class="mt-1 text-xs text-muted-foreground">Base do produto: {{ row.base_price_display }}</p>
                    <div class="mt-2.5 flex justify-end gap-1.5">
                      <button type="button" class="rounded-md border px-2.5 py-1.5 text-xs font-medium transition hover:bg-accent" @click="editing = null">Cancelar</button>
                      <button type="button" class="rounded-md border border-transparent bg-primary px-2.5 py-1.5 text-xs font-semibold text-primary-foreground transition hover:bg-primary/90" @click="commitPrice(row, cell)">Salvar</button>
                    </div>
                  </UiPopoverContent>
                </UiPopover>
                </template>

                <!-- ÁREA 3 — selo de SYNC (produto × plataforma), inline ao lado do preço,
                     só em superfície que projeta. Acionável (erro/sincronizando/nunca) =
                     botão "reenviar agora"; senão só informa. Vem por último para não
                     empurrar o toggle de lugar nas colunas em que não aparece. -->
                <template v-if="cellSync(cell).show">
                  <button
                    v-if="cellSync(cell).actionable"
                    type="button"
                    class="grid size-4 shrink-0 place-items-center rounded-full text-[10px] leading-none transition hover:scale-125 disabled:opacity-40"
                    :class="cellSync(cell).toneClass"
                    :disabled="isBusy(cellKey(row.sku, cell.surface_ref))"
                    :title="`${cellSync(cell).label}${cell.sync_error ? ' · ' + cell.sync_error : ''} — reenviar agora`"
                    :aria-label="`${cellSync(cell).label} em ${surfaceName(cell.surface_ref)} — reenviar agora`"
                    @click="resyncCell(row, cell)"
                  >{{ cellSync(cell).dot }}</button>
                  <span
                    v-else
                    class="shrink-0 text-[10px] leading-none"
                    :class="cellSync(cell).toneClass"
                    :title="cellSync(cell).label"
                    :aria-label="`${cellSync(cell).label} em ${surfaceName(cell.surface_ref)}`"
                  >{{ cellSync(cell).dot }}</span>
                </template>
              </div>
              <div v-else class="grid h-10 place-items-center rounded-md text-xs text-muted-foreground/30">—</div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

      <div v-else-if="!pending" class="grid place-items-center rounded-xl border border-dashed border-border py-16 text-center">
        <Icon name="lucide:package-search" class="mb-2 size-8 text-muted-foreground/40" />
        <p v-if="Object.keys(filters).length || query.trim()" class="text-sm text-muted-foreground">
          Nenhum produto com esses filtros.
          <button v-if="Object.keys(filters).length" class="underline" @click="filters = {}">Limpar filtros</button>
        </p>
        <p v-else class="text-sm text-muted-foreground">Nenhum produto {{ activeCollection ? `na coleção ${activeCollection.name}` : "no catálogo" }}.</p>
      </div>
    </section>

    <!-- floating bulk bar (selection-scoped) -->
    <Transition
      enter-active-class="transition duration-150 ease-out" enter-from-class="translate-y-3 opacity-0" enter-to-class="translate-y-0 opacity-100"
      leave-active-class="transition duration-100 ease-in" leave-from-class="translate-y-0 opacity-100" leave-to-class="translate-y-3 opacity-0"
    >
      <!-- inverted surface: bg-foreground → preta no claro, branca no escuro (alto contraste,
           destaca a ação em curso sobre a matriz). Controles internos usam background/* p/ inverter junto. -->
      <div v-if="selected.size" class="fixed inset-x-0 bottom-5 z-30 mx-auto flex w-fit max-w-[95vw] flex-wrap items-center gap-2 rounded-xl bg-foreground px-3 py-2 text-background shadow-lg">
        <span class="flex items-center gap-1.5 px-1 text-sm font-medium">
          <Icon v-if="bulkBusy" name="line-md:loading-loop" class="size-4" />
          <span class="tabular-nums">{{ selected.size }}</span> selecionado{{ selected.size === 1 ? "" : "s" }}
        </span>
        <div class="flex items-center gap-1 rounded-lg bg-background/10 px-2 py-1 text-sm">
          <span class="text-xs opacity-70">em</span>
          <select v-model="bulkSurface" class="bg-transparent text-sm font-medium text-background outline-none [&>option]:text-foreground [&>optgroup]:text-foreground">
            <option value="*">Todos os canais</option>
            <optgroup v-if="channelSurfaces.length" label="Canais">
              <option v-for="s in channelSurfaces" :key="s.ref" :value="s.ref">{{ s.name }}</option>
            </optgroup>
            <optgroup v-if="showcaseSurfaces.length" label="Feeds">
              <option v-for="s in showcaseSurfaces" :key="s.ref" :value="s.ref">{{ s.name }}</option>
            </optgroup>
          </select>
        </div>
        <div class="h-5 w-px bg-background/20"></div>
        <button :disabled="bulkBusy" class="inline-flex h-9 items-center gap-1.5 rounded-md border border-background/25 px-3 text-sm font-medium transition hover:bg-background/10 disabled:opacity-50" @click="bulk({ is_sellable: false })"><Icon name="lucide:pause" class="size-3.5" /> Pausar</button>
        <button :disabled="bulkBusy" class="inline-flex h-9 items-center gap-1.5 rounded-md border border-background/25 px-3 text-sm font-medium transition hover:bg-background/10 disabled:opacity-50" @click="bulk({ is_sellable: true })"><Icon name="lucide:play" class="size-3.5" /> Reativar</button>

        <!-- Preço e publicação só para canais (transacionam). Feed só pausa/reativa. -->
        <template v-if="!bulkSurfaceIsShowcase">
        <!-- reprecificação em lote: popover ancorado (superfície normal, legível sobre a barra invertida) -->
        <UiPopover :open="priceOpen" @update:open="(v) => (priceOpen = v)">
          <UiPopoverTrigger as-child>
            <button :disabled="bulkBusy" class="inline-flex h-9 items-center gap-1.5 rounded-md border border-background/25 px-3 text-sm font-medium transition hover:bg-background/10 disabled:opacity-50">
              <Icon name="lucide:tag" class="size-3.5" /> Preço…
            </button>
          </UiPopoverTrigger>
          <UiPopoverContent align="center" :side-offset="10" class="w-64 p-3">
            <p class="mb-2 text-xs font-medium text-muted-foreground"><span class="tabular-nums">{{ selected.size }}</span> selecionado{{ selected.size === 1 ? "" : "s" }} em {{ surfaceLabel(bulkSurface) }}</p>
            <div class="mb-2 inline-flex w-full rounded-md border p-0.5 text-xs">
              <button
                v-for="o in priceOps" :key="o.k" type="button"
                class="flex-1 rounded px-2 py-1 font-medium transition"
                :class="priceOp === o.k ? 'bg-accent text-foreground' : 'text-muted-foreground hover:text-foreground'"
                @click="priceOp = o.k"
              >{{ o.l }}</button>
            </div>
            <div class="flex items-center gap-1.5">
              <span class="w-5 shrink-0 text-center text-sm text-muted-foreground">{{ priceOp === "pct" ? "%" : "R$" }}</span>
              <input
                v-model="priceInputBulk" type="text" inputmode="decimal" autofocus
                :placeholder="priceOp === 'set' ? '15,00' : priceOp === 'pct' ? '+10 ou -20' : '+1,00 ou -0,50'"
                class="h-9 w-full rounded-md border bg-background px-2.5 text-sm tabular-nums outline-none focus:ring-1 focus:ring-ring"
                @keyup.enter="applyBulkPrice"
              />
            </div>
            <p class="mt-1.5 text-xs leading-tight text-muted-foreground">
              {{ priceOp === "set" ? "Define o preço de todos os selecionados." : priceOp === "pct" ? "Aumenta (+) ou reduz (−) por porcentagem." : "Soma (+) ou subtrai (−) do preço atual." }}
              Permanente — para promo, use as regras.
            </p>
            <div class="mt-2.5 flex justify-end gap-1.5">
              <button type="button" class="rounded-md border px-2.5 py-1.5 text-xs font-medium transition hover:bg-accent" @click="priceOpen = false">Cancelar</button>
              <button type="button" :disabled="!priceValid || bulkBusy" class="rounded-md border border-transparent bg-primary px-2.5 py-1.5 text-xs font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50" @click="applyBulkPrice">Aplicar</button>
            </div>
          </UiPopoverContent>
        </UiPopover>

        <button :disabled="bulkBusy" class="inline-flex h-9 items-center rounded-md px-3 text-sm font-medium text-background/80 transition hover:bg-background/10 hover:text-background disabled:opacity-50" @click="bulk({ is_published: false })">Despublicar</button>
        <button :disabled="bulkBusy" class="inline-flex h-9 items-center rounded-md px-3 text-sm font-medium text-background/80 transition hover:bg-background/10 hover:text-background disabled:opacity-50" @click="bulk({ is_published: true })">Publicar</button>
        </template>
        <button class="grid size-9 place-items-center rounded-md text-background/70 transition hover:bg-background/10 hover:text-background" title="Limpar seleção" @click="clearSelection"><Icon name="lucide:x" class="size-4" /></button>
      </div>
    </Transition>

    <!-- painel de produto (edição completa, incluindo dados sociais e fiscais) —
         slide-over à direita -->
    <CatalogProductPanel
      :open="detailSku !== null"
      :sku="detailSku"
      :detail="detail"
      :loading="detailLoading"
      :busy="detailSku !== null && isBusy(detailKey(detailSku))"
      :assist="detailAssist.assist"
      :assist-busy="detailAssist.assistBusy"
      :initial-tab="detailTab"
      @update:open="(v) => { if (!v) closeDetail(); }"
      @save="saveDetail"
    />

    <!-- lightbox: foto ampliada (clique em qualquer lugar fecha) -->
    <Transition
      enter-active-class="transition duration-150 ease-out" enter-from-class="opacity-0" enter-to-class="opacity-100"
      leave-active-class="transition duration-100 ease-in" leave-from-class="opacity-100" leave-to-class="opacity-0"
    >
      <div v-if="zoom" class="fixed inset-0 z-50 grid cursor-zoom-out place-items-center bg-black/70 p-8" role="dialog" aria-modal="true" @click="zoom = null" @keydown.esc="zoom = null">
        <figure class="flex flex-col items-center gap-3">
          <img :src="zoom.url" :alt="zoom.name" class="max-h-[80vh] max-w-[85vw] rounded-xl object-contain shadow-2xl" />
          <figcaption class="rounded-full bg-black/40 px-3 py-1 text-sm font-medium text-white">{{ zoom.name }}</figcaption>
        </figure>
      </div>
    </Transition>
  </main>
</template>

<style>
/* FLIP: os chips deslizam suavemente para a nova posição ao reordenar (não é um
   "pulo") — dá o feedback de que a intenção do operador está acontecendo. */
.chip-move {
  transition: transform 0.24s cubic-bezier(0.2, 0, 0, 1);
}
</style>
