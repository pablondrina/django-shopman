// TS mirror of the Django order projections (shopman/backstage/projections/order_queue.py
// + shopman/shop/projections/types.py), serialised by backstage/api/projections.py.
// Kept in lockstep with those dataclasses — the surface renders intent, never rules.

export type OrderTimerClass = "timer-ok" | "timer-warning" | "timer-urgent" | "timer-muted";

export interface AwaitingWorkOrderProjection {
  ref: string;
  status: string;
  status_label: string;
  output_sku: string;
  planned_qty: string;
  finished_qty: string;
  progress_pct: number;
}

export interface OrderItemProjection {
  sku: string;
  name: string;
  qty: number;
  unit_price_display: string;
  total_display: string;
}

export interface TimelineEventProjection {
  label: string;
  event_type: string;
  timestamp_display: string;
  actor: string;
  detail: string;
}

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
  timer_class: OrderTimerClass;
  items_summary: string;
  items_count: number;
  total_display: string;
  fulfillment_icon: string;
  fulfillment_label: string;
  fulfillment_type: "delivery" | "pickup";
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
  confirmation_deadline_iso: string; // prazo da confirmação otimista (vazio se sem timer)
  confirmation_action: string; // "auto_confirm" | "auto_cancel"
}

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
  internal_notes: string;
  payment_method: string;
  payment_method_label: string;
  payment_status: string;
  can_settle_delivery_cash: boolean;
  fiscal_status_label: string;
  fiscal_status: string;
  fiscal_links: { label?: string; href?: string; url?: string }[];
  awaiting_work_orders: AwaitingWorkOrderProjection[];
  is_gift: boolean;
  gift_recipient_name: string;
  gift_recipient_phone: string;
  gift_message: string;
  gift_hide_values: boolean;
}

export interface TwoZoneQueueProjection {
  entrada: OrderCardProjection[];
  preparing_count: number;
  preparo: OrderCardProjection[];
  saida_retirada: OrderCardProjection[];
  saida_delivery: OrderCardProjection[];
  saida_delivery_transit: OrderCardProjection[];
  saida_delivery_count: number;
  saida_count: number;
  total_count: number;
}

export interface OrderQueueResponse {
  queue: TwoZoneQueueProjection;
}

export interface OrderDetailResponse {
  order: OperatorOrderProjection;
}

export interface AlertProjection {
  pk: number;
  type: string;
  type_label: string;
  severity: "warning" | "error" | "critical";
  severity_label: string;
  message: string;
  order_ref: string;
  created_at_display: string;
}

export interface AlertsResponse {
  alerts: AlertProjection[];
  counts: { active: number; critical: number };
}
