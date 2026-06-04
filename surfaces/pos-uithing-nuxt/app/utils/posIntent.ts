import type { POSCartItem, POSIntentCartState, POSPaymentTenderDraft, SurfaceActionProjection } from "~/types/pos";

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

export function moneyInputToQ(value: string): number {
  const raw = String(value || "").trim();
  const normalized = raw.includes(",") ? raw.replace(/\./g, "").replace(",", ".") : raw;
  const parsed = Number.parseFloat(normalized);
  return Number.isFinite(parsed) && parsed > 0 ? Math.round(parsed * 100) : 0;
}

export function qToMoneyInput(amountQ: number): string {
  return (Math.max(0, amountQ) / 100).toFixed(2).replace(".", ",");
}

export interface ResolvedPayment {
  paymentMethod: string;
  paymentTenders: POSPaymentTenderDraft[];
  tenderedAmountQ: number | null;
}

/**
 * Map operator-injected tender lines onto the backend payment contract (Odoo-style:
 * no "mixed" selection — you inject amounts in different forms; the method is derived).
 * - A single cash tender covering the total → single-cash path, so overpayment becomes
 *   change (tendered_amount_q). The backend rejects overpay inside the tenders list, so
 *   cash change only exists for a lone cash payment.
 * - A single non-cash tender → just the method; the backend builds the tender from the
 *   total (no need to replay a tender line — and the spec forbids replaying saved ones).
 * - Two or more tenders → "mixed" with the lines (they must sum to the total).
 */
export function resolvePayment(tenders: POSPaymentTenderDraft[], totalQ: number): ResolvedPayment {
  const only = tenders.length === 1 ? tenders[0] : undefined;
  if (only) {
    if (only.method === "cash" && only.amount_q >= totalQ) {
      return { paymentMethod: "cash", paymentTenders: [], tenderedAmountQ: only.amount_q };
    }
    return { paymentMethod: only.method, paymentTenders: [], tenderedAmountQ: null };
  }
  if (tenders.length >= 2) {
    return { paymentMethod: "mixed", paymentTenders: tenders, tenderedAmountQ: null };
  }
  return { paymentMethod: "", paymentTenders: [], tenderedAmountQ: null };
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

export function buildPosSaleIntent(
  state: POSIntentCartState,
  intentVersion = POS_SALE_INTENT_VERSION,
): Record<string, unknown> {
  const payload: Record<string, unknown> = {
    intent_version: intentVersion || POS_SALE_INTENT_VERSION,
    tab_ref: state.tabRef,
    tab_session_key: state.tabSessionKey,
    items: state.items.map((item) => ({
      sku: item.sku,
      name: item.name,
      qty: item.qty,
      unit_price_q: item.price_q,
      notes: item.notes,
      is_d1: item.is_d1,
      ...(item.discount && item.discount.value > 0
        ? { discount: { type: "percent", value: item.discount.value, reason: item.discount.reason } }
        : {}),
    })),
    fulfillment_type: state.fulfillmentType,
    payment_method: state.paymentMethod,
    payment_collection: state.paymentCollection,
    issue_fiscal_document: state.issueFiscalDocument,
    receipt_mode: state.receiptMode || "none",
    client_request_id: state.clientRequestId,
  };

  if (state.customerName.trim()) payload.customer_name = state.customerName.trim();
  if (state.customerRef.trim()) payload.customer_ref = state.customerRef.trim();
  if (state.customerPhone.trim()) payload.customer_phone = state.customerPhone.replace(/\D/g, "");
  if (state.customerTaxId.trim()) payload.customer_tax_id = state.customerTaxId.replace(/\D/g, "");
  if (state.customerEmail.trim()) payload.customer_email = state.customerEmail.trim();
  if (state.customerMemoryAction.trim()) payload.customer_memory_action = state.customerMemoryAction.trim();

  if (state.fulfillmentType === "delivery") {
    payload.delivery_address = state.deliveryAddress.trim();
    payload.delivery_address_structured = {
      ...state.deliveryAddressStructured,
      complement: state.deliveryComplement.trim() || state.deliveryAddressStructured.complement,
      delivery_instructions: state.deliveryInstructions.trim() || state.deliveryAddressStructured.delivery_instructions,
    };
    if (state.deliveryDate.trim()) payload.delivery_date = state.deliveryDate.trim();
    if (state.deliveryTimeSlot.trim()) payload.delivery_time_slot = state.deliveryTimeSlot.trim();
    payload.delivery_fee_q = Math.max(0, state.deliveryFeeQ || 0);
  }

  if (state.orderNotes.trim()) payload.order_notes = state.orderNotes.trim();
  if (state.paymentMethod === "mixed" && state.paymentTenders.length) payload.payment_tenders = state.paymentTenders;
  if (
    state.paymentMethod === "cash"
    && state.paymentCollection === "terminal"
    && state.tenderedAmountQ !== null
    && state.tenderedAmountQ > 0
  ) {
    payload.tendered_amount_q = state.tenderedAmountQ;
  }
  if (state.receiptEmail.trim()) payload.receipt_email = state.receiptEmail.trim();
  if (state.manualDiscount) payload.manual_discount = state.manualDiscount;
  if (state.managerApproval) payload.manager_approval = state.managerApproval;

  return payload;
}
