// Order detail read-side. Reads the expanded operator projection (items, timeline,
// notes, fiscal links) and exposes the full action set. Writes go through the django
// proxy and reconcile via refresh. Mirrors useOrdersBoard's in-flight guard.
import type { OperatorOrderProjection, OrderDetailResponse } from "~/types/orders";

export function useOrderDetail(orderRef: string) {
  const path = `/api/v1/backstage/orders/${encodeURIComponent(orderRef)}/`;
  const { data, pending, error, refresh } = useFetch<OrderDetailResponse>(path, {
    key: `order-detail-${orderRef}`,
    server: true,
  });

  const order = computed<OperatorOrderProjection | null>(() => data.value?.order ?? null);

  const busy = ref(false);

  async function act(action: string, body?: Record<string, unknown>): Promise<boolean> {
    if (busy.value) return false;
    busy.value = true;
    try {
      await $fetch(`/api/v1/backstage/orders/${encodeURIComponent(orderRef)}/${action}/`, {
        method: "POST",
        body: body ?? {},
      });
      await refresh();
      return true;
    } catch (err: any) {
      useSonner.error(err?.data?.detail || "Falha na ação. Tente de novo.");
      return false;
    } finally {
      busy.value = false;
    }
  }

  const confirm = () => act("confirm");
  const advance = () => act("advance");
  const reject = (reason: string) => act("reject", { reason });
  const cancel = (reason: string) => act("cancel", { reason });
  const settleCash = (amount: string) => act("settle-delivery-cash", { amount });
  const requeueFiscal = () => act("requeue-fiscal");

  async function saveNotes(notes: string): Promise<boolean> {
    const ok = await act("notes", { notes });
    if (ok) useSonner.success("Notas salvas.");
    return ok;
  }

  return { order, pending, error, refresh, busy, confirm, advance, reject, cancel, settleCash, requeueFiscal, saveNotes };
}
