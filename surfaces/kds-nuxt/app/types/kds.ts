// KDS contract types — mirror the backend projections (shopman/backstage/
// projections/kds.py), served verbatim by the canonical JSON API
// (shopman/backstage/api/kds.py). The surface renders these; it does not invent
// shape. Keep in lockstep with the dataclasses.

export type KDSTimerClass = "timer-ok" | "timer-warning" | "timer-late";

export interface KDSItemProjection {
  sku: string;
  name: string;
  qty: number;
  notes: string;
  checked: boolean;
  stock_warning: string; // "" = no warning
}

export interface KDSTicketProjection {
  pk: number;
  order_ref: string;
  channel_icon: string;
  customer_name: string;
  fulfillment_icon: string;
  created_at_display: string;
  elapsed_seconds: number;
  target_seconds: number;
  timer_class: KDSTimerClass;
  items: KDSItemProjection[];
  status: string;
  all_checked: boolean;
  status_label: string;
  is_cancelled: boolean;
  cancelled_at_display: string;
  completed_at_display: string;
  kitchen_note: string; // operator's note from the gestor ("" = none)
  customer_note: string; // customer's checkout note / order_notes ("" = none)
}

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

export interface KDSInstanceSummaryProjection {
  ref: string;
  name: string;
  type: string;
  type_display: string;
  pending_count: number;
}

export interface KDSBoardProjection {
  instance_ref: string;
  instance_name: string;
  instance_type: string;
  is_expedition: boolean;
  /** Prep stations hold KDSTicketProjection; expedition holds KDSExpeditionCardProjection. */
  tickets: (KDSTicketProjection | KDSExpeditionCardProjection)[];
  counts: Record<string, number>; // "pending" | "in_progress" | "total" | ...
  cancelled_tickets: KDSTicketProjection[];
  recent_done: KDSTicketProjection[]; // para recall (desfazer finalização)
}

export interface KDSCustomerOrderProjection {
  ref: string;
  status: string;
  status_label: string;
  updated_at_display: string;
}

export interface KDSCustomerStatusProjection {
  preparing: KDSCustomerOrderProjection[];
  ready: KDSCustomerOrderProjection[];
  updated_at_display: string;
}

// API envelopes (shopman/backstage/api/kds.py response shapes).
export interface KDSIndexResponse { instances: KDSInstanceSummaryProjection[] }
export interface KDSBoardResponse { board: KDSBoardProjection }
export interface KDSTicketResponse { ticket: KDSTicketProjection }
export interface KDSCustomerStatusResponse { status: KDSCustomerStatusProjection }
