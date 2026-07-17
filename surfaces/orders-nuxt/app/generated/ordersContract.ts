// AUTO-GENERATED — do not edit by hand.
// Source of truth: shopman/backstage/projections/order_queue.py + shopman/shop/projections/types.py
// Regenerate with: python manage.py export_orders_schema

/** One line item as displayed on order tracking or confirmation. */
export interface OrderItemProjection {
  sku: string;
  name: string;
  qty: number;
  unit_price_display: string;
  total_display: string;
}

/** A single event in the order timeline. */
export interface TimelineEventProjection {
  label: string;
  event_type: string;
  timestamp_display: string;
  actor: string;
  detail: string;
}

/** A compact production dependency shown on order cards and detail. */
export interface AwaitingWorkOrderProjection {
  ref: string;
  status: string;
  status_label: string;
  output_sku: string;
  planned_qty: string;
  finished_qty: string;
  progress_pct: number;
}

/** A single order card in the operator queue. */
export interface OrderCardProjection {
  ref: string;
  status: string;
  status_label: string;
  status_color: string;
  channel_ref: string;
  channel_icon: string;
  customer_name: string;
  created_at_display: string;
  created_at_iso: string;
  server_now_iso: string;
  elapsed_seconds: number;
  timer_class: string;
  items_summary: string;
  items_count: number;
  total_display: string;
  fulfillment_icon: string;
  fulfillment_label: string;
  fulfillment_type: string;
  can_confirm: boolean;
  can_advance: boolean;
  next_status: string;
  next_action_label: string;
  payment_method: string;
  payment_method_label: string;
  payment_status: string;
  payment_pending: boolean;
  can_settle_delivery_cash: boolean;
  fiscal_status_label: string;
  fiscal_status: string;
  has_notes: boolean;
  assigned_operator: string;
  awaiting_work_orders: AwaitingWorkOrderProjection[];
  confirmation_deadline_iso: string;
  confirmation_action: string;
  courier_status: string;
  courier_status_label: string;
  is_preorder: boolean;
  commitment_date: string;
  commitment_date_display: string;
}

/** Expanded detail for a single order (operator side-panel). */
export interface OperatorOrderProjection {
  ref: string;
  status: string;
  status_label: string;
  status_color: string;
  customer_name: string;
  channel_ref: string;
  channel_icon: string;
  fulfillment_label: string;
  total_display: string;
  items: OrderItemProjection[];
  timeline: TimelineEventProjection[];
  kitchen_note: string;
  payment_method: string;
  payment_method_label: string;
  payment_status: string;
  can_settle_delivery_cash: boolean;
  fiscal_status_label: string;
  fiscal_status: string;
  fiscal_links: Record<string, string>[];
  awaiting_work_orders: AwaitingWorkOrderProjection[];
  is_gift: boolean;
  gift_recipient_name: string;
  gift_recipient_phone: string;
  gift_message: string;
  gift_hide_values: boolean;
  cancellation_presets: string[];
  kitchen_note_tags: string[];
  courier: Record<string, unknown> | null;
}

/** Top-level read model for the operator order queue. */
export interface OrderQueueProjection {
  orders: OrderCardProjection[];
  counts: Record<string, number>;
  active_filter: string;
}

/** Operator queue grouped by action area: intake, prep and expedition */
export interface TwoZoneQueueProjection {
  intake: OrderCardProjection[];
  preparing_count: number;
  prep: OrderCardProjection[];
  expedition_pickup: OrderCardProjection[];
  expedition_delivery: OrderCardProjection[];
  expedition_delivery_transit: OrderCardProjection[];
  expedition_delivery_count: number;
  expedition_count: number;
  total_count: number;
  preorders: OrderCardProjection[];
  preorders_count: number;
}
