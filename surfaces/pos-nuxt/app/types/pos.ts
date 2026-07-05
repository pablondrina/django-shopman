import type { PosPaymentCollection, PosPaymentMethod } from "~/generated/posContract";

export interface Action {
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
  image_url: string;
}

export interface POSCollectionProjection {
  ref: string;
  name: string;
}

export interface POSPaymentMethodProjection {
  ref: PosPaymentMethod | string;
  label: string;
}

export interface POSFulfillmentOptionProjection {
  ref: "pickup" | "delivery";
  label: string;
  description: string;
  requires_address: boolean;
}

export interface POSPaymentCollectionProjection {
  ref: PosPaymentCollection;
  label: string;
  description: string;
  fulfillment_types: Array<"pickup" | "delivery">;
  payment_method_refs: string[];
}

export interface POSCheckoutOptionProjection {
  ref: string;
  label: string;
  description: string;
}

export interface POSCheckoutFieldProjection {
  ref: string;
  payload_key: string;
  section_ref: string;
  label: string;
  input_type: string;
  required: boolean;
  required_when: Record<string, unknown>;
  placeholder: string;
  help_text: string;
  max_length: number;
  options: POSCheckoutOptionProjection[];
  capability_ref: string;
}

export interface POSCheckoutSectionProjection {
  ref: string;
  label: string;
  description: string;
  field_refs: string[];
}

// Sub-objetos do mapa `capabilities` do contrato de checkout. Só os campos que a
// superfície lê são tipados; o index signature preserva as demais chaves (o servidor
// pode carregar mais) e mantém cada capability atribuível a `Record<string, unknown>`.
export interface POSCashManagementCapability {
  movement_kinds?: string[];
  [key: string]: unknown;
}
export interface POSKitchenHandoffCapability {
  fire_action_ref?: string;
  [key: string]: unknown;
}
export interface POSTabManipulationCapability {
  rename_action_ref?: string;
  [key: string]: unknown;
}
export interface POSSaleCorrectionCapability {
  cancel_recent_action_ref?: string;
  [key: string]: unknown;
}
export interface POSCheckoutCapabilities {
  cash_management?: POSCashManagementCapability | null;
  kitchen_handoff?: POSKitchenHandoffCapability | null;
  tab_manipulation?: POSTabManipulationCapability | null;
  sale_correction?: POSSaleCorrectionCapability | null;
  [key: string]: unknown;
}

export interface POSCheckoutContractProjection {
  intent_version: string;
  allowed_payload_keys: string[];
  sections: POSCheckoutSectionProjection[];
  fields: POSCheckoutFieldProjection[];
  receipt_modes: POSCheckoutOptionProjection[];
  tender_methods: POSCheckoutOptionProjection[];
  cash_tender_delta_presets_q: number[];
  discount_types: POSCheckoutOptionProjection[];
  discount_reasons: POSCheckoutOptionProjection[];
  customer_memory_actions: POSCheckoutOptionProjection[];
  capabilities: Record<string, unknown>;
}

export interface POSCashRuntimeProjection {
  has_open_shift: boolean;
  shift_id: number | null;
  terminal_ref: string;
  terminal_label: string;
  operator_username: string;
  opened_at: string;
  status?: "open" | "closed" | "terminal_occupied" | string;
  blocking_operator_username?: string;
  blocking_shift_id?: number | null;
  blocking_message?: string;
  can_close_blocking?: boolean;
}

export interface POSAddressAutocompleteProjection {
  enabled: boolean;
  provider: "google_places" | string;
  public_api_key: string;
  language: string;
  region: string;
  countries: string[];
  types: string[];
  fields: string[];
  structured_fields: string[];
  reverse_geocode_action_ref: string;
  shop_latitude: number | null;
  shop_longitude: number | null;
  bias_radius_m: number;
}

export interface StructuredAddressProjection {
  formatted_address?: string;
  route?: string;
  street_number?: string;
  neighborhood?: string;
  city?: string;
  state?: string;
  state_code?: string;
  postal_code?: string;
  country?: string;
  country_code?: string;
  latitude?: number | null;
  longitude?: number | null;
  place_id?: string | null;
  complement?: string;
  delivery_instructions?: string;
  reference?: string;
  is_verified?: boolean;
}

export interface SavedAddressProjection extends StructuredAddressProjection {
  id: number;
  label: string;
  label_key: string;
  label_custom: string;
  formatted_address: string;
  complement: string;
  delivery_instructions: string;
  is_default: boolean;
}

export interface POSCustomerMemoryProjection {
  total_orders: number;
  average_order_display: string;
  favorite_product: string;
  favorite_item: Record<string, unknown>;
  last_order_items: Array<Record<string, unknown>>;
}

export interface POSCustomerLookupProjection {
  ref: string;
  name: string;
  phone: string;
  email: string;
  loyalty_group: string;
  is_staff: boolean;
  default_address: SavedAddressProjection | null;
  saved_addresses: SavedAddressProjection[];
  memory: POSCustomerMemoryProjection;
}

export interface POSCustomerLookupResponse {
  customer: POSCustomerLookupProjection | null;
}

export interface POSCustomerSearchResult {
  ref: string;
  name: string;
  phone: string;
  document: string;
  email: string;
}

export interface POSCustomerSearchResponse {
  results: POSCustomerSearchResult[];
}

export interface POSTerminalComponentProjection {
  key: string;
  label: string;
  status: "ready" | "warning" | "error" | string;
  message: string;
}

export interface POSOperatorProjection {
  id: number;
  username: string;
  name: string;
}

export interface POSProjection {
  products: POSProductProjection[];
  collections: POSCollectionProjection[];
  payment_methods: POSPaymentMethodProjection[];
  fulfillment_options: POSFulfillmentOptionProjection[];
  payment_collections: POSPaymentCollectionProjection[];
  checkout: POSCheckoutContractProjection;
  actions: Action[];
  has_open_cash_session: boolean;
  cash_runtime: POSCashRuntimeProjection;
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
  operators: POSOperatorProjection[];
  auto_lock_seconds: number;
}

export interface POSShiftSummaryProjection {
  count: number;
  total_display: string;
  pickup_count: number;
  delivery_count: number;
  last_ref: string;
  last_total_display: string;
  cod_pending_count: number;
  cod_pending_display: string;
}

export interface POSTabProjection {
  ref: string;
  display_ref: string;
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
  fired?: boolean;
}

export interface POSResponse {
  pos: POSProjection;
  shift: POSShiftSummaryProjection;
  tabs: POSTabProjection[];
  operator: POSOperatorProjection | null;
  // O operador ativo recebeu um PIN temporário (reset do gerente) e precisa
  // trocá-lo antes de operar — a lock screen força a troca quando true.
  pin_must_change: boolean;
}

export interface POSCartItem {
  sku: string;
  name: string;
  price_q: number;
  qty: number;
  notes: string;
  is_d1: boolean;
  line_id?: string;
  fired?: boolean;
  discount?: { value: number; reason: string };
  /** Operator overrode the unit price (numpad "Preço"): the kernel freezes it and
   *  the server review requires manager approval. Survives persist→reload. */
  price_overridden?: boolean;
}

export interface POSPaymentTenderDraft {
  method: string;
  amount_q: number;
  collection: PosPaymentCollection;
  reference?: string;
  /** Internal: amount is still the untouched system auto-fill (first cédula
   *  replaces it). Stripped before the intent — never sent to the server. */
  _virgin?: boolean;
}

export interface POSTabPayload {
  session_key: string;
  tab_session_key: string;
  tab_ref: string;
  tab_display: string;
  items: POSCartItem[];
  customer_phone: string;
  customer_name: string;
  customer_ref: string;
  customer_group?: string;
  customer_tax_id: string;
  customer_email: string;
  fulfillment_type: "pickup" | "delivery";
  delivery_address: string;
  delivery_address_structured: StructuredAddressProjection;
  delivery_date: string;
  delivery_time_slot: string;
  delivery_fee_q: number;
  order_notes: string;
  payment_method: string;
  payment_collection: PosPaymentCollection;
  payment_tenders: POSIntentCartState["paymentTenders"];
  tendered_amount_q: number | string;
  issue_fiscal_document: boolean;
  receipt_mode: string;
  receipt_email: string;
  discount_type: string;
  discount_value: string;
  discount_reason: string;
}

export interface POSCloseSaleResponse {
  ok: boolean;
  order_ref?: string;
  tab_ref?: string;
  payment?: POSPaymentResultProjection;
}

export interface POSPaymentResultProjection {
  method: string;
  amount_q: number;
  amount_display: string;
  status: string;
  message: string;
  intent_ref?: string;
  qr_code?: string;
  copy_paste?: string;
  expires_at?: string;
  checkout_url?: string;
  error?: string;
}

export interface POSIntentCartState {
  tabRef: string;
  tabSessionKey: string;
  items: POSCartItem[];
  customerName: string;
  customerRef: string;
  customerPhone: string;
  customerTaxId: string;
  customerEmail: string;
  customerMemoryAction: string;
  fulfillmentType: "pickup" | "delivery";
  deliveryAddress: string;
  deliveryAddressStructured: StructuredAddressProjection;
  deliveryComplement: string;
  deliveryInstructions: string;
  deliveryDate: string;
  deliveryTimeSlot: string;
  deliveryFeeQ: number;
  orderNotes: string;
  paymentMethod: string;
  paymentCollection: PosPaymentCollection;
  paymentTenders: POSPaymentTenderDraft[];
  tenderedAmountQ: number | null;
  issueFiscalDocument: boolean;
  receiptMode: string;
  receiptEmail: string;
  manualDiscount: Record<string, unknown> | null;
  managerApproval: Record<string, unknown> | null;
  clientRequestId: string;
}

export interface POSSaleReviewProjection {
  intent_version: string;
  tab_ref: string;
  subtotal_q: number;
  subtotal_display: string;
  discount_q: number;
  discount_display: string;
  delivery_fee_q: number;
  delivery_fee_display: string;
  total_q: number;
  total_display: string;
  payment_method: string;
  payment_collection: string;
  tender_total_q: number;
  tender_total_display: string;
  tender_count: number;
  tendered_amount_q: number;
  tendered_amount_display: string;
  change_q: number;
  change_display: string;
  requires_manager_approval: boolean;
  manager_approval_threshold_q: number;
  receipt_mode: string;
  issue_fiscal_document: boolean;
  warnings: Array<{ code: string; field: string; message: string }>;
}

export interface POSSaleReviewResponse {
  ok: boolean;
  review: POSSaleReviewProjection;
}
