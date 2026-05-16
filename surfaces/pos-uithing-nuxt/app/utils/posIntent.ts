import type { POSCartItem, POSIntentCartState, SurfaceActionProjection } from "~/types/pos";

export const POS_SALE_INTENT_VERSION = "pos.sale-intent.v1";

export function formatBRL(amountQ: number): string {
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  }).format((Number.isFinite(amountQ) ? amountQ : 0) / 100);
}

export function cartTotalQ(items: POSCartItem[]): number {
  return items.reduce((sum, item) => sum + item.price_q * item.qty, 0);
}

export function actionHref(
  actions: SurfaceActionProjection[] | undefined,
  ref: string,
  fallback: string,
): string {
  return actions?.find((action) => action.ref === ref)?.href || fallback;
}

export function concreteActionHref(
  actions: SurfaceActionProjection[] | undefined,
  ref: string,
  fallback: string,
  params: Record<string, string>,
): string {
  let href = actionHref(actions, ref, fallback);
  for (const [key, value] of Object.entries(params)) {
    href = href.replace(`{${key}}`, encodeURIComponent(value));
  }
  return href;
}

export function buildPosSaleIntent(state: POSIntentCartState): Record<string, unknown> {
  const payload: Record<string, unknown> = {
    intent_version: POS_SALE_INTENT_VERSION,
    tab_code: state.tabCode,
    tab_session_key: state.tabSessionKey,
    items: state.items.map((item) => ({
      sku: item.sku,
      name: item.name,
      qty: item.qty,
      unit_price_q: item.price_q,
      notes: item.notes,
    })),
    fulfillment_type: state.fulfillmentType,
    payment_method: state.paymentMethod,
    payment_collection: state.paymentCollection,
    client_request_id: state.clientRequestId,
  };

  if (state.customerName.trim()) payload.customer_name = state.customerName.trim();
  if (state.customerPhone.trim()) payload.customer_phone = state.customerPhone.replace(/\D/g, "");

  if (state.fulfillmentType === "delivery") {
    payload.delivery_address = state.deliveryAddress.trim();
    if (state.deliveryTimeSlot.trim()) payload.delivery_time_slot = state.deliveryTimeSlot.trim();
  }

  return payload;
}
