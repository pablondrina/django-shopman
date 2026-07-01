// Catalog matrix read/write. Single source for the produto × superfície grid:
//   - useFetch the canonical matrix projection (GET /api/v1/backstage/catalog/);
//   - poll every 60s as a light fallback (catalog changes less often than orders);
//   - cell + bulk mutations POST through the django proxy (CSRF handled there),
//     then reconcile via refresh (the backend owns the availability rules).
import type { CatalogMatrixProjection, CatalogMatrixResponse } from "~/types/catalog";

export interface CellPatch {
  is_published?: boolean;
  is_sellable?: boolean;
  price_q?: number;
}

export function useCatalogMatrix(collectionRef?: Ref<string>) {
  const path = "/api/v1/backstage/catalog/";
  // Reactive collection filter → server-side row scoping (smart-aware via
  // product_queryset). Changing the ref refetches the matrix.
  const collection = collectionRef ?? ref("");
  const { data, pending, error, refresh } = useFetch<CatalogMatrixResponse>(path, {
    key: "catalog-matrix",
    server: true,
    query: { collection },
  });

  const matrix = computed<CatalogMatrixProjection | null>(() => data.value?.matrix ?? null);

  let pollTimer: ReturnType<typeof setInterval> | null = null;
  onMounted(() => {
    pollTimer = setInterval(() => refresh(), 60_000);
  });
  onBeforeUnmount(() => {
    if (pollTimer) clearInterval(pollTimer);
  });

  // Per-cell in-flight guard: a cell key is `${sku}@${surface}`.
  const busy = ref<Set<string>>(new Set());
  const isBusy = (key: string) => busy.value.has(key);
  const cellKey = (sku: string, surface: string) => `${sku}@${surface}`;

  const errorMsg = ref("");
  const clearError = () => (errorMsg.value = "");

  async function setCell(sku: string, surface: string, patch: CellPatch): Promise<boolean> {
    const key = cellKey(sku, surface);
    if (busy.value.has(key)) return false;
    clearError();
    busy.value = new Set(busy.value).add(key);
    try {
      await $fetch("/api/v1/backstage/catalog/cell/", {
        method: "POST",
        body: { sku, surface_ref: surface, ...patch },
      });
      await refresh();
      return true;
    } catch (err: any) {
      errorMsg.value = err?.data?.detail || "Falha ao atualizar. Tente de novo.";
      useSonner.error(errorMsg.value);
      return false;
    } finally {
      const next = new Set(busy.value);
      next.delete(key);
      busy.value = next;
    }
  }

  // Bulk over a surface, scoped by collection ref OR an explicit sku list.
  const bulkBusy = ref(false);
  async function bulkSet(
    surface: string,
    scope: { collection_ref?: string; skus?: string[] },
    patch: Pick<CellPatch, "is_published" | "is_sellable">,
  ): Promise<number> {
    if (bulkBusy.value) return 0;
    clearError();
    bulkBusy.value = true;
    try {
      const res = await $fetch<{ count: number }>("/api/v1/backstage/catalog/bulk/", {
        method: "POST",
        body: { surface_ref: surface, ...scope, ...patch },
      });
      await refresh();
      const count = res?.count ?? 0;
      useSonner.success(`${count} item(ns) atualizado(s).`);
      return count;
    } catch (err: any) {
      errorMsg.value = err?.data?.detail || "Falha na ação em lote.";
      useSonner.error(errorMsg.value);
      return 0;
    } finally {
      bulkBusy.value = false;
    }
  }

  // Materialize a collection-fed surface: sync its ListingItems to the source
  // collection (add missing, remove non-members). Server owns the resolution.
  const materializing = ref<Set<string>>(new Set());
  const isMaterializing = (surface: string) => materializing.value.has(surface);
  async function materialize(surface: string): Promise<boolean> {
    if (materializing.value.has(surface)) return false;
    clearError();
    materializing.value = new Set(materializing.value).add(surface);
    try {
      const res = await $fetch<{ added: number; removed: number; total: number }>(
        "/api/v1/backstage/catalog/materialize/",
        { method: "POST", body: { surface_ref: surface } },
      );
      await refresh();
      useSonner.success(`Sincronizado: +${res.added} / −${res.removed} (${res.total} itens).`);
      return true;
    } catch (err: any) {
      errorMsg.value = err?.data?.detail || "Falha ao sincronizar da coleção.";
      useSonner.error(errorMsg.value);
      return false;
    } finally {
      const next = new Set(materializing.value);
      next.delete(surface);
      materializing.value = next;
    }
  }

  return {
    matrix, pending, error, refresh, isBusy, cellKey, errorMsg, clearError,
    setCell, bulkSet, bulkBusy, materialize, isMaterializing,
  };
}
