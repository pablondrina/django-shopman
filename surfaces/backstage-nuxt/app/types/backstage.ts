export interface KDSItemProjection {
  sku: string
  name: string
  qty: number
  notes: string
  checked: boolean
  stock_warning: string
}

export interface KDSTicketProjection {
  pk: number
  order_ref: string
  channel_icon: string
  customer_name: string
  fulfillment_icon: string
  created_at_display: string
  elapsed_seconds: number
  target_seconds: number
  timer_class: 'timer-ok' | 'timer-warning' | 'timer-late'
  items: KDSItemProjection[]
  status: string
  all_checked: boolean
}

export interface KDSExpeditionCardProjection {
  pk: number
  ref: string
  channel_icon: string
  customer_name: string
  fulfillment_icon: string
  fulfillment_label: string
  is_delivery: boolean
  units_count: string
  line_count: number
  total_display: string
}

export interface KDSInstanceSummaryProjection {
  ref: string
  name: string
  type: string
  type_display: string
  pending_count: number
}

export interface KDSBoardProjection {
  instance_ref: string
  instance_name: string
  instance_type: string
  is_expedition: boolean
  tickets: Array<KDSTicketProjection | KDSExpeditionCardProjection>
  counts: { pending: number, in_progress: number, total: number }
}

export interface KDSCustomerOrderProjection {
  ref: string
  customer_name: string
  status: string
  status_label: string
  ready_at_display: string
}

export interface KDSCustomerStatusProjection {
  preparing: KDSCustomerOrderProjection[]
  ready: KDSCustomerOrderProjection[]
}

export interface KDSIndexResponse {
  instances: KDSInstanceSummaryProjection[]
}

export interface KDSBoardResponse {
  board: KDSBoardProjection
}

export interface KDSCustomerStatusResponse {
  status: KDSCustomerStatusProjection
}

// ── POS ────────────────────────────────────────────────────────────────

export interface POSProductProjection {
  sku: string
  name: string
  price_q: number
  price_display: string
  collection_ref: string
  is_d1: boolean
}

export interface POSCollectionProjection {
  ref: string
  name: string
}

export interface POSPaymentMethodProjection {
  ref: string
  label: string
}

export interface POSFulfillmentOptionProjection {
  ref: 'pickup' | 'delivery'
  label: string
  description: string
  requires_address: boolean
}

export interface POSPaymentCollectionProjection {
  ref: 'terminal' | 'on_delivery'
  label: string
  description: string
  fulfillment_types: Array<'pickup' | 'delivery'>
  payment_method_refs: string[]
}

export interface POSCheckoutOptionProjection {
  ref: string
  label: string
  description: string
}

export interface POSCheckoutFieldProjection {
  ref: string
  payload_key: string
  section_ref: string
  label: string
  input_type: string
  required: boolean
  required_when: Record<string, unknown>
  placeholder: string
  help_text: string
  max_length: number
  options: POSCheckoutOptionProjection[]
  capability_ref: string
}

export interface POSCheckoutSectionProjection {
  ref: string
  label: string
  description: string
  field_refs: string[]
}

export interface POSCheckoutContractProjection {
  intent_version: string
  allowed_payload_keys: string[]
  sections: POSCheckoutSectionProjection[]
  fields: POSCheckoutFieldProjection[]
  receipt_modes: POSCheckoutOptionProjection[]
  tender_methods: POSCheckoutOptionProjection[]
  cash_tender_delta_presets_q: number[]
  discount_types: POSCheckoutOptionProjection[]
  discount_reasons: POSCheckoutOptionProjection[]
  customer_memory_actions: POSCheckoutOptionProjection[]
  capabilities: Record<string, unknown>
}

export interface Action {
  ref: string
  kind: string
  label: string
  priority: string
  enabled: boolean
  reason: string
  href: string
  method: string
  payload_schema: Record<string, unknown>
  idempotency: string
  confirmation: Record<string, unknown>
}

export interface POSShiftSummaryProjection {
  count: number
  total_display: string
  last_ref: string
  last_total_display: string
}

export interface POSTabProjection {
  code: string
  display_code: string
  session_key: string
  state: string
  status_label: string
  status_class: string
  customer_name: string
  customer_phone: string
  item_count: number
  line_count: number
  total_display: string
  last_touched_display: string
  items_preview: string
}

export interface POSProjection {
  products: POSProductProjection[]
  collections: POSCollectionProjection[]
  payment_methods: POSPaymentMethodProjection[]
  fulfillment_options: POSFulfillmentOptionProjection[]
  payment_collections: POSPaymentCollectionProjection[]
  checkout: POSCheckoutContractProjection
  actions: Action[]
  has_open_cash_session: boolean
}

export interface POSResponse {
  pos: POSProjection
  shift: POSShiftSummaryProjection
  tabs: POSTabProjection[]
}

export interface POSCartItem {
  sku: string
  name: string
  price_q: number
  qty: number
  notes: string
  is_d1: boolean
  line_id?: string
}

export interface POSTabPayload {
  session_key: string
  tab_session_key: string
  tab_code: string
  tab_display: string
  items: POSCartItem[]
  subtotal_display?: string
  total_display?: string
}

// ── Production ─────────────────────────────────────────────────────────

export interface WorkOrderCardProjection {
  pk: number
  ref: string
  recipe_name: string
  output_sku: string
  status: string
  status_display: string
  quantity_display: string
  position_display: string
  created_at_display: string
  started_at_display: string
  finished_at_display: string
  loss_qty_display: string
  yield_pct_display: string
  is_late: boolean
}

export interface ProductionBoardProjection {
  selected_date: string
  selected_date_display: string
  cards: WorkOrderCardProjection[]
  counts: { planned: number, started: number, finished: number, total: number }
}

export interface ProductionKDSCardProjection {
  pk: number
  ref: string
  recipe_name: string
  output_sku: string
  quantity_display: string
  elapsed_seconds: number
  timer_class: 'timer-ok' | 'timer-warning' | 'timer-late'
  position_display: string
  next_step_label: string
}

export interface ProductionKDSProjection {
  selected_date: string
  selected_date_display: string
  cards: ProductionKDSCardProjection[]
  total_count: number
  late_count: number
}

export interface ProductionBoardResponse { board: ProductionBoardProjection }
export interface ProductionKDSResponse { kds: ProductionKDSProjection }

// ── Day Closing ────────────────────────────────────────────────────────

export interface ClosingItemProjection {
  sku: string
  name: string
  qty_available: number
  classification: 'd1' | 'loss' | 'neutral'
  badge_label: string
  badge_css: string
}

export interface ReconciliationError {
  sku: string
  sold_qty: number
  available_qty: number
  deficit_qty: number
}

export interface DayClosingProjection {
  today: string
  today_display: string
  items: ClosingItemProjection[]
  has_items: boolean
  already_closed: boolean
  existing_closing_display: string
  has_old_d1: boolean
  total_available: number
  production_summary: Record<string, unknown>
  reconciliation_errors: ReconciliationError[]
}

export interface DayClosingResponse { closing: DayClosingProjection }

// ── Order Queue ────────────────────────────────────────────────────────

export interface AwaitingWorkOrderProjection {
  ref: string
  status: string
  status_label: string
  output_sku: string
  planned_qty: string
  finished_qty: string
  progress_pct: number
}

export interface OrderCardProjection {
  ref: string
  status: string
  status_label: string
  status_color: string
  channel_ref: string
  channel_icon: string
  customer_name: string
  created_at_display: string
  created_at_iso: string
  server_now_iso: string
  elapsed_seconds: number
  timer_class: 'timer-ok' | 'timer-warning' | 'timer-urgent' | 'timer-muted'
  items_summary: string
  items_count: number
  total_display: string
  fulfillment_icon: string
  fulfillment_label: string
  can_confirm: boolean
  can_advance: boolean
  next_status: string
  next_action_label: string
  payment_method: string
  payment_method_label: string
  payment_status: string
  payment_pending: boolean
  has_notes: boolean
  awaiting_work_orders: AwaitingWorkOrderProjection[]
}

export interface TwoZoneQueueProjection {
  entrada: OrderCardProjection[]
  preparing_count: number
  preparo: OrderCardProjection[]
  saida_retirada: OrderCardProjection[]
  saida_delivery: OrderCardProjection[]
  saida_delivery_transit: OrderCardProjection[]
  saida_delivery_count: number
  saida_count: number
  total_count: number
}

export interface OrderQueueResponse { queue: TwoZoneQueueProjection }

export interface OrderItemProjection {
  sku: string
  name: string
  qty: number
  unit_price_display: string
  total_display: string
}

export interface TimelineEventProjection {
  label: string
  event_type: string
  timestamp_display: string
  actor?: string
  detail?: string
}

export interface OperatorOrderProjection {
  ref: string
  status: string
  status_label: string
  status_color: string
  customer_name: string
  channel_ref: string
  channel_icon: string
  fulfillment_label: string
  total_display: string
  items: OrderItemProjection[]
  timeline: TimelineEventProjection[]
  internal_notes: string
  payment_method: string
  payment_method_label: string
  payment_status: string
  awaiting_work_orders: AwaitingWorkOrderProjection[]
}

export interface OrderDetailResponse { order: OperatorOrderProjection }
