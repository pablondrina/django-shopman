// Receipt shaping (spec §D3 — web/CSS print). Pure functions that turn the
// finalized-sale snapshot into the lines a thermal receipt renders. The snapshot
// is captured at finalize (the cart is reset right after), so the receipt is a
// frozen record of what was sold — never recomputed from live state. Formatting
// only; no policy. The print transport (kiosk window.print → ESC-POS / network
// ePOS on real hardware) is validated separately on a device.
import type { POSPaymentMethodProjection } from "~/types/pos";
import { formatBRL } from "~/utils/posIntent";
import { methodLabel } from "~/presentation/payment";

export interface PosReceiptItem {
  name: string;
  qty: number;
  price_q: number;
  discountPct: number;
}

export interface PosReceiptPayment {
  method: string;
  amount_q: number;
}

/** Frozen record of a finalized sale, captured before the cart resets. */
export interface PosReceiptSnapshot {
  orderRef: string;
  tabDisplay: string;
  customerName: string;
  items: PosReceiptItem[];
  totalDisplay: string;
  payments: PosReceiptPayment[];
  fulfillmentLabel: string;
  printedAtMs: number;
}

export interface ReceiptLineView {
  name: string;
  qty: number;
  unitDisplay: string;
  totalDisplay: string;
  discountPct: number;
}

/** Net line total in cents, applying the per-line percentage discount. */
export function receiptLineTotalQ(item: PosReceiptItem): number {
  const gross = item.price_q * item.qty;
  if (!item.discountPct) return gross;
  const perUnit = Math.min(item.price_q, Math.round((item.price_q * item.discountPct) / 100));
  return Math.max(0, gross - perUnit * item.qty);
}

export function receiptLines(snap: PosReceiptSnapshot): ReceiptLineView[] {
  return snap.items.map((item) => ({
    name: item.name,
    qty: item.qty,
    unitDisplay: formatBRL(item.price_q),
    totalDisplay: formatBRL(receiptLineTotalQ(item)),
    discountPct: item.discountPct,
  }));
}

export function receiptPayments(
  snap: PosReceiptSnapshot,
  methods: POSPaymentMethodProjection[],
): { label: string; amountDisplay: string }[] {
  return snap.payments.map((payment) => ({
    label: methodLabel(payment.method, methods),
    amountDisplay: formatBRL(payment.amount_q),
  }));
}
