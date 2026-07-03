// Mise en place read-side. Single source for the day's aggregated ingredient
// list (GET /api/v1/backstage/production/mise-en-place/):
//   - expand=false (default): immediate ingredients with per-recipe breakdown;
//   - expand=true: sub-recipes exploded down to raw materials.
// The "separado" checkmark is shift-local state (localStorage), never persisted
// server-side — zero migrations, resets naturally when the list changes date.
import type { MiseEnPlaceLineProjection, MiseEnPlaceResponse } from "~/types/production";

export function useMiseEnPlace() {
  const expand = ref(false);

  const { data, pending, error, refresh } = useFetch<MiseEnPlaceResponse>(
    "/api/v1/backstage/production/mise-en-place/",
    {
      key: "production-mise-en-place",
      server: true,
      query: computed(() => ({ expand: expand.value ? "1" : "" })),
    },
  );

  const projection = computed(() => data.value?.mise_en_place ?? null);
  const lines = computed<MiseEnPlaceLineProjection[]>(() => projection.value?.lines ?? []);

  useAdaptivePoll(refresh, () => 60_000);

  // "Separado" por turno: chaveado por data — virou o dia, lista limpa.
  const checkedKey = computed(() => `mise-en-place:${projection.value?.selected_date ?? ""}`);
  const checked = ref<Set<string>>(new Set());

  function loadChecked() {
    if (!import.meta.client || !projection.value) return;
    try {
      const raw = localStorage.getItem(checkedKey.value);
      checked.value = new Set(raw ? (JSON.parse(raw) as string[]) : []);
    } catch {
      checked.value = new Set();
    }
  }
  watch(checkedKey, loadChecked, { immediate: true });

  function toggleChecked(sku: string) {
    const next = new Set(checked.value);
    if (next.has(sku)) next.delete(sku);
    else next.add(sku);
    checked.value = next;
    if (import.meta.client) {
      try {
        localStorage.setItem(checkedKey.value, JSON.stringify([...next]));
      } catch {
        // storage cheio/indisponível: o check vive só na sessão.
      }
    }
  }
  const isChecked = (sku: string) => checked.value.has(sku);
  const checkedCount = computed(
    () => lines.value.filter((line) => checked.value.has(line.sku)).length,
  );

  return {
    projection,
    lines,
    expand,
    pending,
    error,
    refresh,
    isChecked,
    toggleChecked,
    checkedCount,
  };
}
