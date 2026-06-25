// Production planning read-side. Single source for the planning matrix:
//   - useFetch the production board projection (GET /api/v1/backstage/production/);
//   - poll every 60s (planning changes slowly, manager-paced).
// Writes (plan / start) go through the django proxy (CSRF handled there) and
// reconcile via refresh. Order-coverage shortage surfaces as a structured error.
import type { ProductionBoardProjection, ProductionBoardResponse, ProductionShortageError } from "~/types/production";
import { parseShortage } from "~/presentation/production";

export interface BoardActResult {
  ok: boolean;
  shortage?: ProductionShortageError;
}

export function useProductionBoard() {
  const path = "/api/v1/backstage/production/";

  const { data, pending, error, refresh } = useFetch<ProductionBoardResponse>(path, {
    key: "production-board",
    server: true,
  });

  const board = computed<ProductionBoardProjection | null>(() => data.value?.board ?? null);
  const rows = computed(() => board.value?.matrix_rows ?? []);
  const counts = computed(() => board.value?.counts ?? null);
  const dateDisplay = computed(() => board.value?.selected_date_display ?? "");

  let pollTimer: ReturnType<typeof setInterval> | null = null;
  onMounted(() => { pollTimer = setInterval(() => refresh(), 60_000); });
  onBeforeUnmount(() => { if (pollTimer) clearInterval(pollTimer); });

  // a planning POST keys on the output_sku row (one in-flight per row).
  const busy = ref<Set<string>>(new Set());
  const isBusy = (key: string) => busy.value.has(key);

  async function post(key: string, url: string, body: Record<string, unknown>): Promise<BoardActResult> {
    if (busy.value.has(key)) return { ok: false };
    busy.value = new Set(busy.value).add(key);
    try {
      await $fetch(url, { method: "POST", body });
      await refresh();
      return { ok: true };
    } catch (err: any) {
      const shortage = parseShortage(err?.data);
      if (shortage) return { ok: false, shortage };
      useSonner.error(err?.data?.detail || "Falha na ação. Tente de novo.");
      return { ok: false };
    } finally {
      const next = new Set(busy.value);
      next.delete(key);
      busy.value = next;
    }
  }

  function plan(
    key: string,
    payload: { recipe_id: number; quantity: string; target_date: string; position_ref?: string; source?: string; force?: boolean },
  ): Promise<BoardActResult> {
    return post(key, "/api/v1/backstage/production/plan/", payload);
  }

  function start(key: string, woPk: number, quantity: string): Promise<BoardActResult> {
    return post(key, `/api/v1/backstage/production/${woPk}/start/`, { quantity });
  }

  return { board, rows, counts, dateDisplay, pending, error, refresh, isBusy, plan, start };
}
