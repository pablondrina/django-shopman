// AUTO-GENERATED — do not edit by hand.
// Source of truth: shopman/backstage/projections/kds.py
// Regenerate with: python manage.py export_kds_schema

/** A single item within a KDS ticket. */
export interface KDSItemProjection {
  sku: string;
  name: string;
  qty: number;
  notes: string;
  checked: boolean;
  stock_warning: string;
}

/** A KDS ticket card (prep/picking station). */
export interface KDSTicketProjection {
  pk: number;
  order_ref: string;
  channel_icon: string;
  customer_name: string;
  fulfillment_icon: string;
  created_at_display: string;
  elapsed_seconds: number;
  target_seconds: number;
  timer_class: string;
  items: KDSItemProjection[];
  status: string;
  all_checked: boolean;
  status_label: string;
  is_cancelled: boolean;
  cancelled_at_display: string;
  completed_at_display: string;
  kitchen_note: string;
  customer_note: string;
}

/** An order card in the expedition (dispatch) board. */
export interface KDSExpeditionCardProjection {
  pk: number;
  order_ref: string;
  channel_icon: string;
  customer_name: string;
  fulfillment_icon: string;
  fulfillment_label: string;
  is_delivery: boolean;
  units_count: string;
  line_count: number;
  total_display: string;
  items: KDSItemProjection[];
}

/** A KDS instance in the index (station selector). */
export interface KDSInstanceSummaryProjection {
  ref: string;
  name: string;
  type: string;
  type_display: string;
  pending_count: number;
}

/** Top-level read model for a KDS display. */
export interface KDSBoardProjection {
  instance_ref: string;
  instance_name: string;
  instance_type: string;
  is_expedition: boolean;
  tickets: (KDSTicketProjection | KDSExpeditionCardProjection)[];
  counts: Record<string, number>;
  cancelled_tickets: KDSTicketProjection[];
  recent_done: KDSTicketProjection[];
}

/** Privacy-safe order status for a customer-facing ready board. */
export interface KDSCustomerOrderProjection {
  ref: string;
  status: string;
  status_label: string;
  updated_at_display: string;
}

/** Customer-facing KDS status split by preparation and pickup readiness. */
export interface KDSCustomerStatusProjection {
  preparing: KDSCustomerOrderProjection[];
  ready: KDSCustomerOrderProjection[];
  updated_at_display: string;
}
