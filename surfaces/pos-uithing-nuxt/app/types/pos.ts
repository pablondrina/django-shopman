export interface SurfaceActionProjection {
  ref: string;
  kind: string;
  label: string;
  priority: "primary" | "secondary" | "quiet" | string;
  enabled: boolean;
  reason: string;
  href: string;
  method: string;
  payload_schema: Record<string, unknown>;
  idempotency: string;
  confirmation: Record<string, unknown>;
}

export interface POSProductProjection {
  sku: string;
  name: string;
  price_q: number;
  price_display: string;
  collection_ref: string;
  is_d1: boolean;
}

export interface POSCollectionProjection {
  ref: string;
  name: string;
}

export interface POSPaymentMethodProjection {
  ref: "cash" | "pix" | "card" | "external" | "mixed" | string;
  label: string;
}

export interface POSFulfillmentOptionProjection {
  ref: "pickup" | "delivery";
  label: string;
  description: string;
  requires_address: boolean;
}

export interface POSPaymentCollectionProjection {
  ref: "terminal" | "on_delivery";
  label: string;
  description: string;
  fulfillment_types: Array<"pickup" | "delivery">;
  payment_method_refs: string[];
}

export interface POSTerminalComponentProjection {
  key: string;
  label: string;
  status: "ready" | "warning" | "error" | string;
  message: string;
}

export interface POSProjection {
  products: POSProductProjection[];
  collections: POSCollectionProjection[];
  payment_methods: POSPaymentMethodProjection[];
  fulfillment_options: POSFulfillmentOptionProjection[];
  payment_collections: POSPaymentCollectionProjection[];
  actions: SurfaceActionProjection[];
  has_open_cash_session: boolean;
  terminal_ref: string;
  terminal_label: string;
  terminal_default_fulfillment_type: "pickup" | "delivery" | string;
  terminal_health_status: "ready" | "warning" | "error" | string;
  terminal_components: POSTerminalComponentProjection[];
  favorite_collection_refs: string[];
  delivery_minimum_q: number;
  delivery_minimum_display: string;
  fiscal_status: "ready" | "warning" | "error" | string;
  fiscal_label: string;
  fiscal_message: string;
}

export interface POSShiftSummaryProjection {
  count: number;
  total_display: string;
  pickup_count: number;
  delivery_count: number;
  cash_total_display: string;
  digital_total_display: string;
  last_ref: string;
  last_total_display: string;
  cod_pending_count: number;
  cod_pending_display: string;
}

export interface POSTabProjection {
  code: string;
  display_code: string;
  session_key: string;
  state: "empty" | "in_use" | string;
  status_label: string;
  status_class: string;
  customer_name: string;
  customer_phone: string;
  item_count: number;
  line_count: number;
  total_display: string;
  last_touched_display: string;
  items_preview: string;
}

export interface POSResponse {
  pos: POSProjection;
  shift: POSShiftSummaryProjection;
  tabs: POSTabProjection[];
}

export interface POSCartItem {
  sku: string;
  name: string;
  price_q: number;
  qty: number;
  notes: string;
  is_d1: boolean;
}

export interface POSTabPayload {
  session_key: string;
  tab_session_key: string;
  tab_code: string;
  tab_display: string;
  items: POSCartItem[];
  customer_phone: string;
  customer_name: string;
  fulfillment_type: "pickup" | "delivery";
  delivery_address: string;
  delivery_time_slot: string;
  payment_method: string;
  payment_collection: "terminal" | "on_delivery";
}

export interface POSCloseSaleResponse {
  ok: boolean;
  order_ref?: string;
  tab_code?: string;
}

export interface POSIntentCartState {
  tabCode: string;
  tabSessionKey: string;
  items: POSCartItem[];
  customerName: string;
  customerPhone: string;
  fulfillmentType: "pickup" | "delivery";
  deliveryAddress: string;
  deliveryTimeSlot: string;
  paymentMethod: string;
  paymentCollection: "terminal" | "on_delivery";
  clientRequestId: string;
}
