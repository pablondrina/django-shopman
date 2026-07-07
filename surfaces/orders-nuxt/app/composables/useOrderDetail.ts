// Order detail read-side. Reads the expanded operator projection (items, timeline,
// notes, fiscal links) and exposes the full action set. Writes go through the django
// proxy and reconcile via refresh. Mirrors useOrdersBoard's in-flight guard.
import type { CancellationReason, OperatorOrderProjection, OrderDetailResponse } from "~/types/orders";

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
    } catch (error) {
      useSonner.error(httpErrorMessage(error, "Falha na ação. Tente de novo."));
      return false;
    } finally {
      busy.value = false;
    }
  }

  const confirm = () => act("confirm");
  const advance = () => act("advance");
  // Marketplace (iFood) reject/cancel carry the operator-picked code so the backend
  // relays a valid reason to the provider; empty string for other channels.
  const reject = (reason: string, cancellation_code = "") => act("reject", { reason, cancellation_code });
  const cancel = (reason: string, cancellation_code = "") => act("cancel", { reason, cancellation_code });
  const settleCash = (amount: string) => act("settle-delivery-cash", { amount });
  const requeueFiscal = () => act("requeue-fiscal");

  // Valid cancellation reasons for this order: for iFood, the live per-order coded
  // list ({code, description}); empty for channels without reason codes.
  async function fetchCancellationReasons(): Promise<CancellationReason[]> {
    try {
      const res = await $fetch<{ reasons: CancellationReason[] }>(
        `/api/v1/backstage/orders/${encodeURIComponent(orderRef)}/cancellation-reasons/`,
      );
      return res?.reasons ?? [];
    } catch {
      return [];
    }
  }

  async function saveNotes(notes: string): Promise<boolean> {
    const ok = await act("notes", { notes });
    if (ok) useSonner.success("Notas salvas.");
    return ok;
  }

  async function addComment(note: string): Promise<boolean> {
    const ok = await act("comment", { note });
    if (ok) useSonner.success("Comentário adicionado.");
    return ok;
  }

  return { order, pending, error, refresh, busy, confirm, advance, reject, cancel, fetchCancellationReasons, settleCash, requeueFiscal, saveNotes, addComment };
}
