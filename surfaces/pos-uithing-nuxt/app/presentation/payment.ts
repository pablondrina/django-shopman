// Presentation — payment screen shaping (spec §2.4, Odoo-style tender injection).
//
// Pure transforms for the payment screen: the method affordances, the tender
// line views, the "remaining/change/covered" math, the cash quick-add presets,
// and the digital payment proof (PIX QR / card checkout link). Zero policy: the
// orchestrator's `review` is authoritative for the total; remaining/change/
// covered here are a UX gate over the operator's tender draft, recomputed live
// so the screen can disable Finalize until the total is covered. The backend
// re-derives and seals everything on review/commit.

import type {
  POSCheckoutContractProjection,
  POSPaymentCollectionProjection,
  POSPaymentMethodProjection,
  POSPaymentResultProjection,
  POSPaymentTenderDraft,
} from "~/types/pos";
import { formatBRL } from "~/utils/posIntent";

const PAYMENT_ICONS: Record<string, string> = {
  cash: "lucide:banknote",
  pix: "lucide:qr-code",
  card: "lucide:credit-card",
  mixed: "lucide:layers",
  external: "lucide:ellipsis",
};

export function paymentIcon(ref: string): string {
  return PAYMENT_ICONS[ref] || "lucide:wallet";
}

/**
 * Methods the operator can inject as a tender. The derived "mixed" pseudo-method
 * is never a button — the method is derived from the set of tenders, not picked
 * (see `resolvePayment`).
 */
export function injectableMethods(methods: POSPaymentMethodProjection[]): POSPaymentMethodProjection[] {
  return methods.filter((method) => method.ref !== "mixed");
}

export function methodLabel(ref: string, methods: POSPaymentMethodProjection[]): string {
  return methods.find((method) => method.ref === ref)?.label || ref;
}

export function tenderSumQ(tenders: POSPaymentTenderDraft[]): number {
  return tenders.reduce((sum, tender) => sum + (tender.amount_q || 0), 0);
}

/**
 * Amount still due. Can go negative once overpaid (cash change) — clamp at the
 * call site for display. Driven by the authoritative `totalQ` from the review.
 */
export function paymentRemainingQ(tenders: POSPaymentTenderDraft[], totalQ: number): number {
  return totalQ - tenderSumQ(tenders);
}

export function paymentChangeQ(tenders: POSPaymentTenderDraft[], totalQ: number): number {
  return Math.max(0, tenderSumQ(tenders) - totalQ);
}

/** UX gate: at least one tender and the total fully covered. */
export function isPaymentCovered(tenders: POSPaymentTenderDraft[], totalQ: number): boolean {
  return tenders.length > 0 && paymentRemainingQ(tenders, totalQ) <= 0;
}

export interface TenderLineView {
  method: string;
  label: string;
  icon: string;
  amountQ: number;
  amountDisplay: string;
}

export function tenderLineView(
  tender: POSPaymentTenderDraft,
  methods: POSPaymentMethodProjection[],
): TenderLineView {
  return {
    method: tender.method,
    label: methodLabel(tender.method, methods),
    icon: paymentIcon(tender.method),
    amountQ: tender.amount_q,
    amountDisplay: formatBRL(tender.amount_q),
  };
}

/**
 * Cash quick-add deltas (+R$10/50/100…) sourced from the contract; falls back to
 * a sensible BR set only if the channel omits them. The presets are policy and
 * live in the Projection, never hardcoded in the screen.
 */
export function cashDeltaPresets(contract: POSCheckoutContractProjection | null): number[] {
  const presets = contract?.cash_tender_delta_presets_q;
  return Array.isArray(presets) && presets.length ? presets : [1000, 5000, 10000];
}

/** Collections offered for the current fulfillment type (e.g. on-delivery vs terminal). */
export function collectionsForFulfillment(
  collections: POSPaymentCollectionProjection[],
  fulfillmentType: string,
): POSPaymentCollectionProjection[] {
  return collections.filter((collection) => collection.fulfillment_types.includes(fulfillmentType as "pickup" | "delivery"));
}

export type PaymentProofTone = "info" | "warning" | "success" | "danger" | "neutral";

const PROOF_TONES: Record<string, PaymentProofTone> = {
  pending: "info",
  unavailable: "warning",
  error: "danger",
};

export interface PaymentProofView {
  method: string;
  icon: string;
  amountDisplay: string;
  status: string;
  tone: PaymentProofTone;
  message: string;
  /** Render-ready `<img src>` for the PIX QR (data URI or http), or "". */
  qrCodeSrc: string;
  copyPaste: string;
  checkoutUrl: string;
  isPix: boolean;
  isCard: boolean;
  /** Has gateway data worth surfacing (QR / copy-paste / checkout link). */
  hasProof: boolean;
}

/**
 * Normalize the gateway QR field into an `<img src>`. Efi returns the QR as a
 * base64 PNG (sometimes already a data URI); pass through http(s)/data URIs and
 * wrap a bare base64 payload. Empty in, empty out.
 */
export function qrCodeSrc(qrCode: string): string {
  if (!qrCode) return "";
  if (qrCode.startsWith("data:") || qrCode.startsWith("http")) return qrCode;
  return `data:image/png;base64,${qrCode}`;
}

/**
 * Shape the close_sale `payment` result into a render-ready proof, or null when
 * there is nothing to show (cash, or a digital method without gateway data).
 *
 * PCI SAQ A: the screen only DISPLAYS the gateway's QR / copy-paste / checkout
 * link — it never captures card data. The webhook is the authoritative return.
 */
export function paymentProofView(
  result: POSPaymentResultProjection | null | undefined,
): PaymentProofView | null {
  if (!result || !result.method) return null;
  const method = result.method;
  if (method !== "pix" && method !== "card") return null;
  const qrSrc = qrCodeSrc(result.qr_code || "");
  const copyPaste = result.copy_paste || "";
  const checkoutUrl = result.checkout_url || "";
  return {
    method,
    icon: paymentIcon(method),
    amountDisplay: result.amount_display || "",
    status: result.status || "",
    tone: PROOF_TONES[result.status || ""] || "neutral",
    message: result.message || "",
    qrCodeSrc: qrSrc,
    copyPaste,
    checkoutUrl,
    isPix: method === "pix",
    isCard: method === "card",
    hasProof: Boolean(qrSrc || copyPaste || checkoutUrl),
  };
}
