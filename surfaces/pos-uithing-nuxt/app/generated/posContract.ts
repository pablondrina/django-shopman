// AUTO-GENERATED — do not edit by hand.
// Source of truth: shopman/shop/services/pos_intent.py
// Regenerate with: python manage.py export_pos_schema

export const POS_SALE_INTENT_VERSION = "pos.sale-intent.v1";

export const POS_PAYMENT_METHODS = ["card", "cash", "external", "mixed", "pix"] as const;
export type PosPaymentMethod = (typeof POS_PAYMENT_METHODS)[number];

export const POS_PAYMENT_COLLECTIONS = ["on_delivery", "terminal"] as const;
export type PosPaymentCollection = (typeof POS_PAYMENT_COLLECTIONS)[number];

export const POS_RECEIPT_MODES = ["email", "none", "print"] as const;
export type PosReceiptMode = (typeof POS_RECEIPT_MODES)[number];
