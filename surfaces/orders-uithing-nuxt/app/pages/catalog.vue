<script setup lang="ts">
// Catalog matrix — produto × superfície. The catalog side of the Gestor hub:
// read the matrix projection, pause/resume + reprice a cell with one click, and
// act in bulk scoped to a collection (the collection axis). Desktop-first grid,
// responsive (horizontal scroll on narrow screens). The backend owns availability
// rules; this page renders intent and reconciles via refresh.
import {
  capabilityLabel,
  cellView,
  filterRows,
  syncBadge,
} from "~/presentation/catalog";
import type { CatalogRowProjection, SurfaceCellProjection } from "~/types/catalog";

const collectionRef = ref("");
const { matrix, pending, error, refresh, isBusy, cellKey, setCell, bulkSet, bulkBusy } =
  useCatalogMatrix(collectionRef);

const surfaces = computed(() => matrix.value?.surfaces ?? []);
const collections = computed(() => matrix.value?.collections ?? []);
const query = ref("");
const rows = computed<CatalogRowProjection[]>(() =>
  filterRows(matrix.value?.rows ?? [], query.value),
);

const activeCollection = computed(() =>
  collections.value.find((c) => c.ref === collectionRef.value) ?? null,
);

// ── bulk (collection axis) ────────────────────────────────────────────────────
const bulkSurface = ref("");
watchEffect(() => {
  if (!bulkSurface.value && surfaces.value.length) bulkSurface.value = surfaces.value[0]!.ref;
});
async function bulkPause(sellable: boolean) {
  if (!collectionRef.value || !bulkSurface.value) return;
  await bulkSet(bulkSurface.value, { collection_ref: collectionRef.value }, { is_sellable: sellable });
}

// ── cell pause/resume ─────────────────────────────────────────────────────────
function toggleCell(row: CatalogRowProjection, cell: SurfaceCellProjection) {
  if (!cell.in_listing) return;
  setCell(row.sku, cell.surface_ref, { is_sellable: !cell.is_sellable });
}

// ── inline price edit ─────────────────────────────────────────────────────────
const editing = ref<{ sku: string; surface: string } | null>(null);
const priceInput = ref("");
function startEdit(row: CatalogRowProjection, cell: SurfaceCellProjection) {
  if (!cell.in_listing) return;
  editing.value = { sku: row.sku, surface: cell.surface_ref };
  priceInput.value = ((cell.price_q ?? 0) / 100).toFixed(2).replace(".", ",");
}
function isEditing(sku: string, surface: string) {
  return editing.value?.sku === sku && editing.value?.surface === surface;
}
function parseBrl(text: string): number | null {
  const cleaned = text.replace(/[^0-9,.-]/g, "").replace(/\./g, "").replace(",", ".");
  const value = Number.parseFloat(cleaned);
  if (!Number.isFinite(value) || value < 0) return null;
  return Math.round(value * 100);
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
  <main class="flex min-h-screen flex-col gap-4 p-4 lg:p-6">
    <!-- header -->
    <header class="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
      <div class="flex flex-col gap-1">
        <h1 class="text-lg font-semibold text-foreground">Catálogo</h1>
        <p class="text-xs text-muted-foreground">
          {{ rows.length }} produto(s) · {{ surfaces.length }} superfície(s)
        </p>
      </div>
      <div class="flex items-center gap-2">
        <input
          v-model="query"
          type="search"
          placeholder="Buscar produto…"
          class="h-9 w-56 rounded-md border border-border bg-background px-3 text-sm outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
        />
        <UiButton variant="outline" size="sm" :loading="pending" @click="refresh()">
          Atualizar
        </UiButton>
      </div>
    </header>

    <!-- collection axis: chips -->
    <div v-if="collections.length" class="flex flex-wrap items-center gap-1.5">
      <button
        class="h-9 rounded-full border px-3 text-sm transition-colors"
        :class="collectionRef === '' ? 'border-primary bg-primary/5 text-foreground' : 'border-border text-muted-foreground hover:bg-muted'"
        @click="collectionRef = ''"
      >
        Todas
      </button>
      <button
        v-for="c in collections"
        :key="c.ref"
        class="h-9 rounded-full border px-3 text-sm transition-colors"
        :class="collectionRef === c.ref ? 'border-primary bg-primary/5 text-foreground' : 'border-border text-muted-foreground hover:bg-muted'"
        @click="collectionRef = c.ref"
      >
        {{ c.name }}
        <span class="ml-1 text-xs text-muted-foreground">{{ c.product_count }}</span>
        <span v-if="c.is_smart" class="ml-1 text-xs" title="Coleção por regra">✦</span>
      </button>
    </div>

    <!-- bulk bar (collection axis) -->
    <div
      v-if="activeCollection"
      class="flex flex-wrap items-center gap-2 rounded-md border border-border bg-card p-3"
    >
      <span class="text-sm text-muted-foreground">
        Em lote na coleção <strong class="text-foreground">{{ activeCollection.name }}</strong>:
      </span>
      <select
        v-model="bulkSurface"
        class="h-9 rounded-md border border-border bg-background px-2 text-sm outline-none"
      >
        <option v-for="s in surfaces" :key="s.ref" :value="s.ref">{{ s.name }}</option>
      </select>
      <UiButton variant="outline" size="sm" :loading="bulkBusy" @click="bulkPause(false)">
        Pausar tudo
      </UiButton>
      <UiButton variant="outline" size="sm" :loading="bulkBusy" @click="bulkPause(true)">
        Reativar tudo
      </UiButton>
    </div>

    <p v-if="error" class="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
      Não foi possível carregar o catálogo.
    </p>

    <!-- matrix -->
    <div v-if="rows.length" class="overflow-x-auto rounded-md border border-border">
      <table class="w-full border-collapse text-sm">
        <thead>
          <tr class="border-b border-border bg-muted/50">
            <th class="sticky left-0 z-10 min-w-[220px] bg-muted/50 p-3 text-left font-medium">
              Produto
            </th>
            <th v-for="s in surfaces" :key="s.ref" class="min-w-[140px] p-3 text-left font-medium">
              <div class="flex flex-col gap-0.5">
                <span class="text-foreground">{{ s.name }}</span>
                <span class="text-xs font-normal text-muted-foreground">
                  {{ capabilityLabel(s.capability) }}
                  <template v-if="s.content_source">· ← {{ s.content_source }}</template>
                </span>
                <span
                  v-if="syncBadge(s.sync_status)"
                  class="text-xs font-normal"
                  :class="syncBadge(s.sync_status)!.toneClass"
                >
                  {{ syncBadge(s.sync_status)!.label }}
                </span>
              </div>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.sku" class="border-b border-border last:border-0 hover:bg-muted/30">
            <!-- product row header -->
            <td class="sticky left-0 z-10 bg-background p-3">
              <div class="flex items-center gap-2">
                <img
                  v-if="row.image_url"
                  :src="row.image_url"
                  :alt="row.name"
                  class="size-9 shrink-0 rounded-md object-cover"
                />
                <div class="flex flex-col">
                  <span class="font-medium text-foreground">{{ row.name }}</span>
                  <span class="text-xs text-muted-foreground">
                    {{ row.sku }} · {{ row.base_price_display }}
                    <template v-if="row.primary_collection_name">· {{ row.primary_collection_name }}</template>
                  </span>
                  <span v-if="!row.is_sellable || !row.is_published" class="text-xs text-amber-600 dark:text-amber-400">
                    {{ !row.is_published ? "produto despublicado" : "produto pausado" }} (afeta todas)
                  </span>
                </div>
              </div>
            </td>
            <!-- cells -->
            <td v-for="cell in row.cells" :key="cell.surface_ref" class="p-2 align-top">
              <template v-if="cell.in_listing">
                <div class="flex flex-col gap-1">
                  <button
                    class="inline-flex h-9 items-center justify-between gap-1 rounded-md border px-2 text-xs transition-opacity disabled:opacity-50"
                    :class="cellView(row, cell).toneClass"
                    :disabled="isBusy(cellKey(row.sku, cell.surface_ref))"
                    :title="`Clique para ${cell.is_sellable ? 'pausar' : 'reativar'}`"
                    @click="toggleCell(row, cell)"
                  >
                    <span>{{ cellView(row, cell).label }}</span>
                    <Icon :name="cell.is_sellable ? 'lucide:pause' : 'lucide:play'" class="size-3.5" />
                  </button>
                  <!-- price -->
                  <input
                    v-if="isEditing(row.sku, cell.surface_ref)"
                    v-model="priceInput"
                    type="text"
                    inputmode="decimal"
                    class="h-8 w-full rounded-md border border-primary bg-background px-2 text-xs outline-none"
                    autofocus
                    @keyup.enter="commitPrice(row, cell)"
                    @blur="commitPrice(row, cell)"
                  />
                  <button
                    v-else
                    class="text-left text-xs text-muted-foreground hover:text-foreground"
                    title="Clique para editar o preço"
                    @click="startEdit(row, cell)"
                  >
                    {{ cell.price_display }}
                  </button>
                </div>
              </template>
              <span v-else class="inline-flex h-9 items-center px-2 text-xs text-muted-foreground/50">—</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- empty -->
    <div v-else-if="!pending" class="rounded-md border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
      Nenhum produto {{ activeCollection ? `na coleção ${activeCollection.name}` : "no catálogo" }}.
    </div>
  </main>
</template>
