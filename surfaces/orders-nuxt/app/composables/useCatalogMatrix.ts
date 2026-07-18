// Catalog matrix read/write. Single source for the produto × superfície grid:
//   - useFetch the canonical matrix projection (GET /api/v1/backstage/catalog/);
//   - poll every 60s as a light fallback (catalog changes less often than orders);
//   - cell + bulk mutations POST through the django proxy (CSRF handled there),
//     then reconcile via refresh (the backend owns the availability rules).
import type { CatalogMatrixProjection, CatalogMatrixResponse, ProductSocial } from "~/types/catalog";

export interface CellPatch {
  is_published?: boolean;
  is_sellable?: boolean;
  price_q?: number;
}

// Escrita PIM: um subconjunto dos campos sociais (merge parcial no backend).
export type SocialPatch = Partial<Omit<ProductSocial, "has_data">>;

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
    } catch (error) {
      errorMsg.value = httpErrorMessage(error, "Falha ao atualizar. Tente de novo.");
      useSonner.error(errorMsg.value);
      return false;
    } finally {
      const next = new Set(busy.value);
      next.delete(key);
      busy.value = next;
    }
  }

  // Product-level pause/publish ("globalzinho") — flips the produto-level switch,
  // which gates every channel at once. Busy key namespaced apart from cell keys.
  const productKey = (sku: string) => `product@${sku}`;
  async function setProduct(
    sku: string,
    patch: Pick<CellPatch, "is_published" | "is_sellable">,
  ): Promise<boolean> {
    const key = productKey(sku);
    if (busy.value.has(key)) return false;
    clearError();
    busy.value = new Set(busy.value).add(key);
    try {
      await $fetch("/api/v1/backstage/catalog/product/", {
        method: "POST",
        body: { sku, ...patch },
      });
      await refresh();
      return true;
    } catch (error) {
      errorMsg.value = httpErrorMessage(error, "Falha ao atualizar. Tente de novo.");
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
    } catch (error) {
      errorMsg.value = httpErrorMessage(error, "Falha na ação em lote.");
      useSonner.error(errorMsg.value);
      return 0;
    } finally {
      bulkBusy.value = false;
    }
  }

  // Reprecificação em lote: op set|pct|delta, value em centavos (set/delta) ou
  // pontos percentuais (pct). Escopo por coleção OU lista de skus.
  async function bulkPrice(
    surface: string,
    scope: { collection_ref?: string; skus?: string[] },
    patch: { op: "set" | "pct" | "delta"; value: number },
  ): Promise<number> {
    if (bulkBusy.value) return 0;
    clearError();
    bulkBusy.value = true;
    try {
      const res = await $fetch<{ count: number }>("/api/v1/backstage/catalog/bulk-price/", {
        method: "POST",
        body: { surface_ref: surface, ...scope, ...patch },
      });
      await refresh();
      const count = res?.count ?? 0;
      useSonner.success(`${count} preço(s) atualizado(s).`);
      return count;
    } catch (error) {
      errorMsg.value = httpErrorMessage(error, "Falha ao reprecificar.");
      useSonner.error(errorMsg.value);
      return 0;
    } finally {
      bulkBusy.value = false;
    }
  }

  // ── sync por plataforma (Arc H) ────────────────────────────────────────────
  // Re-enfileira a projeção de um SKU numa plataforma (ou em todas, sem platform).
  // Otimista no selo? Não — o push é async (Directive); marca a célula como ocupada
  // e refaz o fetch canônico, que já traz o estado atualizado quando o worker roda.
  async function resync(sku: string, platform?: string): Promise<boolean> {
    const key = platform ? cellKey(sku, platform) : productKey(sku);
    if (busy.value.has(key)) return false;
    clearError();
    busy.value = new Set(busy.value).add(key);
    try {
      await $fetch("/api/v1/backstage/catalog/resync/", {
        method: "POST",
        body: platform ? { sku, platform } : { sku },
      });
      useSonner.success(platform ? "Reenvio agendado." : "Reenvio agendado em todas as plataformas.");
      await refresh();
      return true;
    } catch (error) {
      errorMsg.value = httpErrorMessage(error, "Falha ao reenviar. Tente de novo.");
      useSonner.error(errorMsg.value);
      return false;
    } finally {
      const next = new Set(busy.value);
      next.delete(key);
      busy.value = next;
    }
  }

  // ── PIM social (Arc H) ─────────────────────────────────────────────────────
  // Salva atributos sociais (merge parcial); o backend valida (GTIN/categoria) e
  // re-projeta via o gatilho de Product.save. Retorna false com toast na validação.
  const socialKey = (sku: string) => `social@${sku}`;
  async function saveSocial(sku: string, patch: SocialPatch): Promise<boolean> {
    const key = socialKey(sku);
    if (busy.value.has(key)) return false;
    clearError();
    busy.value = new Set(busy.value).add(key);
    try {
      await $fetch("/api/v1/backstage/catalog/social/", {
        method: "POST",
        body: { sku, ...patch },
      });
      useSonner.success("Dados do produto salvos.");
      await refresh();
      return true;
    } catch (error) {
      errorMsg.value = httpErrorMessage(error, "Falha ao salvar. Confira os campos.");
      useSonner.error(errorMsg.value);
      return false;
    } finally {
      const next = new Set(busy.value);
      next.delete(key);
      busy.value = next;
    }
  }

  // ── reordenação (curadoria) ────────────────────────────────────────────────
  async function reorderCollections(orderedRefs: string[]): Promise<boolean> {
    clearError();
    try {
      await $fetch("/api/v1/backstage/catalog/reorder-collections/", {
        method: "POST",
        body: { ordered_refs: orderedRefs },
      });
      await refresh();
      return true;
    } catch (error) {
      errorMsg.value = httpErrorMessage(error, "Falha ao reordenar.");
      useSonner.error(errorMsg.value);
      await refresh(); // reverte o otimista
      return false;
    }
  }
  async function reorderItems(collectionRef_: string, orderedSkus: string[]): Promise<boolean> {
    clearError();
    try {
      await $fetch("/api/v1/backstage/catalog/reorder-items/", {
        method: "POST",
        body: { collection_ref: collectionRef_, ordered_skus: orderedSkus },
      });
      await refresh();
      return true;
    } catch (error) {
      errorMsg.value = httpErrorMessage(error, "Falha ao reordenar.");
      useSonner.error(errorMsg.value);
      await refresh();
      return false;
    }
  }

  return {
    matrix, pending, error, refresh, isBusy, cellKey, productKey, socialKey, errorMsg, clearError,
    setCell, setProduct, bulkSet, bulkPrice, resync, saveSocial, reorderCollections, reorderItems, bulkBusy,
  };
}
