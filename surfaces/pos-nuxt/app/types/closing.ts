// Contrato do fechamento do DIA (contagem cega de sobras/perdas), servido por
// GET/POST /api/v1/backstage/closing/ — serialização da DayClosingProjection
// (shopman/backstage/projections/closing.py). Só os campos que a superfície lê.

export interface ClosingItemProjection {
  sku: string;
  name: string;
  qty_available: number;
  classification: "d1" | "loss" | "neutral" | string;
}

export interface ClosingProductionRow {
  recipe_ref: string;
  output_sku: string;
  planned: number;
  finished: number;
  loss?: number;
}

export interface ClosingReconciliationError {
  sku: string;
  sold_qty: number;
  available_qty: number;
  deficit_qty: number;
}

export interface ClosingPendingProduction {
  ref: string;
  output_sku: string;
  recipe_name: string;
  status: string;
  status_label: string;
  quantity: string;
  target_date_display: string;
  is_overdue: boolean;
}

export interface ClosingUpcomingPreorder {
  date: string;
  date_display: string;
  orders_count: number;
  total_q: number;
  total_display: string;
}

export interface DayClosingProjection {
  today: string;
  today_display: string;
  items: ClosingItemProjection[];
  has_items: boolean;
  already_closed: boolean;
  existing_closing_display: string;
  has_old_d1: boolean;
  total_available: number;
  production_summary: Record<string, ClosingProductionRow>;
  reconciliation_errors: ClosingReconciliationError[];
  pending_production: ClosingPendingProduction[];
  has_pending_production: boolean;
  upcoming_preorders: ClosingUpcomingPreorder[];
  has_upcoming_preorders: boolean;
}

export interface DayClosingResponse {
  closing: DayClosingProjection;
}
