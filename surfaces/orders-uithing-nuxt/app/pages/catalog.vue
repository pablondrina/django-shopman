<script setup lang="ts">
// Catalog matrix — produto × superfície. The catalog side of the Gestor hub.
// Design: a glanceable availability heatmap (tinted cells) with one-click pause and
// inline reprice per cell; the collection axis (chips) scopes the view; selection +
// a floating bulk bar act on the active recorte. Desktop-first, horizontal scroll on
// narrow screens. The backend owns availability rules; this renders intent + reconciles.
import { cellDot, cellState, cellTint, cellView, filterRows, syncBadge } from "~/presentation/catalog";
import type { CatalogRowProjection, SurfaceCellProjection } from "~/types/catalog";

const collectionRef = ref("");
const {
  matrix, pending, error, refresh, isBusy, cellKey, setCell, bulkSet, bulkBusy,
} = useCatalogMatrix(collectionRef);

const surfaces = computed(() => matrix.value?.surfaces ?? []);
const collections = computed(() => matrix.value?.collections ?? []);
const query = ref("");
const rows = computed<CatalogRowProjection[]>(() => filterRows(matrix.value?.rows ?? [], query.value));
const activeCollection = computed(() => collections.value.find((c) => c.ref === collectionRef.value) ?? null);
const loading = computed(() => pending.value && !matrix.value);

// ── selection + floating bulk bar (acts on the active recorte) ─────────────────
const selected = ref<Set<string>>(new Set());
const isSelected = (sku: string) => selected.value.has(sku);
function toggleSelect(sku: string) {
  const next = new Set(selected.value);
  next.has(sku) ? next.delete(sku) : next.add(sku);
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
async function bulk(patch: { is_sellable?: boolean; is_published?: boolean }) {
  if (!bulkSurface.value || selected.value.size === 0) return;
  await bulkSet(bulkSurface.value, { skus: [...selected.value] }, patch);
  clearSelection();
}

// ── cell pause/resume + inline reprice ─────────────────────────────────────────
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

useHead({ title: "Catálogo · Gestor" });
</script>

<template>
  <main class="mx-auto flex min-h-screen w-full max-w-[1600px] flex-col gap-5 p-4 lg:p-8">
    <!-- header -->
    <header class="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div class="flex flex-col gap-1">
        <h1 class="text-2xl font-semibold tracking-tight text-foreground">Catálogo</h1>
        <p class="text-sm text-muted-foreground">
          <span class="tabular-nums">{{ rows.length }}</span> produto{{ rows.length === 1 ? "" : "s" }}
          <span class="text-muted-foreground/50">·</span>
          <span class="tabular-nums">{{ surfaces.length }}</span> superfície{{ surfaces.length === 1 ? "" : "s" }}
        </p>
      </div>
      <div class="flex items-center gap-2">
        <div class="relative">
          <Icon name="lucide:search" class="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <input
            v-model="query" type="search" placeholder="Buscar produto ou SKU…"
            class="h-10 w-64 rounded-lg border border-border bg-card pl-9 pr-3 text-sm outline-none transition-colors focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/40"
          />
        </div>
        <UiButton variant="outline" size="default" class="h-10" :loading="pending" @click="refresh()">
          <Icon name="lucide:refresh-cw" class="size-4" /> Atualizar
        </UiButton>
      </div>
    </header>

    <!-- collection axis -->
    <div v-if="collections.length" class="flex flex-wrap items-center gap-1.5">
      <button
        class="inline-flex h-8 items-center rounded-full border px-3 text-sm font-medium transition-colors"
        :class="collectionRef === '' ? 'border-transparent bg-foreground text-background' : 'border-border text-muted-foreground hover:bg-muted hover:text-foreground'"
        @click="collectionRef = ''"
      >Todas</button>
      <button
        v-for="c in collections" :key="c.ref"
        class="inline-flex h-8 items-center gap-1.5 rounded-full border px-3 text-sm font-medium transition-colors"
        :class="collectionRef === c.ref ? 'border-transparent bg-foreground text-background' : 'border-border text-muted-foreground hover:bg-muted hover:text-foreground'"
        @click="collectionRef = c.ref"
      >
        <Icon v-if="c.is_smart" name="lucide:sparkles" class="size-3.5 opacity-70" :title="'Coleção por regra'" />
        {{ c.name }}
        <span class="tabular-nums opacity-50">{{ c.product_count }}</span>
      </button>
    </div>

    <p v-if="error" class="rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
      Não foi possível carregar o catálogo. <button class="underline" @click="refresh()">Tentar de novo</button>
    </p>

    <!-- matrix -->
    <div v-if="loading" class="overflow-hidden rounded-xl border border-border bg-card">
      <div v-for="i in 8" :key="i" class="flex items-center gap-3 border-b border-border px-4 py-3 last:border-0">
        <div class="size-10 animate-pulse rounded-md bg-muted"></div>
        <div class="h-4 w-40 animate-pulse rounded bg-muted"></div>
        <div class="ml-auto flex gap-2">
          <div v-for="j in 4" :key="j" class="h-8 w-24 animate-pulse rounded-md bg-muted"></div>
        </div>
      </div>
    </div>

    <div v-else-if="rows.length" class="overflow-x-auto rounded-xl border border-border bg-card shadow-xs">
      <table class="w-full border-separate border-spacing-0 text-sm">
        <thead>
          <tr>
            <th class="sticky left-0 z-20 border-b border-border bg-card px-4 py-3 text-left">
              <label class="flex items-center gap-3">
                <input type="checkbox" :checked="allSelected" class="size-4 rounded border-border accent-foreground" @change="toggleSelectAll" />
                <span class="text-xs font-medium uppercase tracking-wide text-muted-foreground">Produto</span>
              </label>
            </th>
            <th v-for="s in surfaces" :key="s.ref" class="min-w-[132px] border-b border-l border-border px-3 py-2.5 text-left align-top">
              <div class="flex flex-col gap-1">
                <span class="font-medium text-foreground">{{ s.name }}</span>
                <span v-if="syncBadge(s.sync_status)" class="text-[10px] font-medium" :class="syncBadge(s.sync_status)!.toneClass">
                  ● {{ syncBadge(s.sync_status)!.label }}
                </span>
              </div>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.sku" class="group">
            <!-- product -->
            <td class="sticky left-0 z-10 border-b border-border bg-card px-4 py-2.5 group-hover:bg-muted/40" :class="{ 'bg-muted/40': isSelected(row.sku) }">
              <label class="flex items-center gap-3">
                <input type="checkbox" :checked="isSelected(row.sku)" class="size-4 shrink-0 rounded border-border accent-foreground" @change="toggleSelect(row.sku)" />
                <img v-if="row.image_url" :src="row.image_url" :alt="row.name" class="size-10 shrink-0 rounded-md object-cover ring-1 ring-border" />
                <div v-else class="grid size-10 shrink-0 place-items-center rounded-md bg-muted text-muted-foreground"><Icon name="lucide:image-off" class="size-4" /></div>
                <div class="flex min-w-0 flex-col">
                  <span class="truncate font-medium text-foreground">{{ row.name }}</span>
                  <span class="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <span class="font-mono">{{ row.sku }}</span>
                    <span class="text-muted-foreground/40">·</span>
                    <span class="tabular-nums">{{ row.base_price_display }}</span>
                    <span v-if="row.primary_collection_name" class="truncate rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">{{ row.primary_collection_name }}</span>
                  </span>
                  <span v-if="!row.is_sellable || !row.is_published" class="mt-0.5 inline-flex w-fit items-center gap-1 text-[11px] text-amber-600 dark:text-amber-400">
                    <Icon name="lucide:triangle-alert" class="size-3" />
                    {{ !row.is_published ? "produto despublicado" : "produto pausado" }} — afeta todas
                  </span>
                </div>
              </label>
            </td>
            <!-- cells (heatmap) -->
            <td v-for="cell in row.cells" :key="cell.surface_ref" class="border-b border-l border-border px-1.5 py-1.5 group-hover:bg-muted/20">
              <div
                v-if="cell.in_listing"
                class="flex h-9 items-center gap-1.5 rounded-md px-1.5 transition-colors"
                :class="cellTint(cellState(row, cell))"
              >
                <button
                  class="group/t relative inline-flex size-6 shrink-0 items-center justify-center rounded transition-colors hover:bg-background/60 disabled:opacity-40"
                  :disabled="isBusy(cellKey(row.sku, cell.surface_ref))"
                  :title="cell.is_sellable ? `${cellView(row, cell).label} — clique para pausar` : `${cellView(row, cell).label} — clique para reativar`"
                  @click="toggleCell(row, cell)"
                >
                  <span class="size-2 rounded-full transition-opacity group-hover/t:opacity-0" :class="cellDot(cellState(row, cell))"></span>
                  <Icon :name="cell.is_sellable ? 'lucide:pause' : 'lucide:play'" class="absolute size-3.5 text-foreground opacity-0 transition-opacity group-hover/t:opacity-100" />
                </button>
                <input
                  v-if="isEditing(row.sku, cell.surface_ref)"
                  v-model="priceInput" type="text" inputmode="decimal" autofocus
                  class="h-7 w-full rounded border border-ring bg-background px-1.5 text-xs tabular-nums outline-none"
                  @keyup.enter="commitPrice(row, cell)" @blur="commitPrice(row, cell)"
                />
                <button
                  v-else class="ml-auto rounded px-1 text-xs tabular-nums transition-colors hover:bg-background/60"
                  :class="cell.is_sellable ? 'text-foreground' : 'text-muted-foreground line-through'"
                  title="Clique para editar o preço" @click="startEdit(row, cell)"
                >{{ cell.price_display }}</button>
              </div>
              <div v-else class="grid h-9 place-items-center rounded-md text-xs text-muted-foreground/30">—</div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-else-if="!pending" class="grid place-items-center rounded-xl border border-dashed border-border py-16 text-center">
      <Icon name="lucide:package-search" class="mb-2 size-8 text-muted-foreground/40" />
      <p class="text-sm text-muted-foreground">Nenhum produto {{ activeCollection ? `na coleção ${activeCollection.name}` : "no catálogo" }}.</p>
    </div>

    <!-- floating bulk bar (selection-scoped) -->
    <Transition
      enter-active-class="transition duration-150 ease-out" enter-from-class="translate-y-3 opacity-0" enter-to-class="translate-y-0 opacity-100"
      leave-active-class="transition duration-100 ease-in" leave-from-class="translate-y-0 opacity-100" leave-to-class="translate-y-3 opacity-0"
    >
      <div v-if="selected.size" class="fixed inset-x-0 bottom-5 z-30 mx-auto flex w-fit max-w-[95vw] flex-wrap items-center gap-2 rounded-xl border border-border bg-card px-3 py-2 shadow-lg">
        <span class="px-1 text-sm font-medium text-foreground"><span class="tabular-nums">{{ selected.size }}</span> selecionado{{ selected.size === 1 ? "" : "s" }}</span>
        <div class="flex items-center gap-1 rounded-lg bg-muted px-2 py-1 text-sm text-muted-foreground">
          <span class="text-xs">em</span>
          <select v-model="bulkSurface" class="bg-transparent text-sm font-medium text-foreground outline-none">
            <option v-for="s in surfaces" :key="s.ref" :value="s.ref">{{ s.name }}</option>
          </select>
        </div>
        <div class="h-5 w-px bg-border"></div>
        <UiButton variant="outline" size="sm" :loading="bulkBusy" @click="bulk({ is_sellable: false })"><Icon name="lucide:pause" class="size-3.5" /> Pausar</UiButton>
        <UiButton variant="outline" size="sm" :loading="bulkBusy" @click="bulk({ is_sellable: true })"><Icon name="lucide:play" class="size-3.5" /> Reativar</UiButton>
        <UiButton variant="ghost" size="sm" :loading="bulkBusy" @click="bulk({ is_published: false })">Despublicar</UiButton>
        <UiButton variant="ghost" size="sm" :loading="bulkBusy" @click="bulk({ is_published: true })">Publicar</UiButton>
        <button class="rounded p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground" title="Limpar seleção" @click="clearSelection"><Icon name="lucide:x" class="size-4" /></button>
      </div>
    </Transition>
  </main>
</template>
