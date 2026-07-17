// Contrato do relatório de sessão de caixa (leituras X/Z + histórico do dia),
// servido por GET /api/v1/backstage/pos/cash/report/ — serialização da
// CashSessionReportProjection (shopman/backstage/projections/cash_session.py).
// Só os campos que a superfície lê. BLIND: o contrato NUNCA carrega o valor
// esperado da gaveta nem a variância — a conferência é da retaguarda.

export interface CashMovementRow {
  kind: "sangria" | "suprimento" | "ajuste" | string;
  kind_label: string;
  amount_q: number;
  amount_display: string;
  reason: string;
  created_by: string;
  created_at: string;
}

export interface SalesByMethodRow {
  method: string;
  method_label: string;
  orders_count: number;
  amount_q: number;
  amount_display: string;
}

export interface ShiftReading {
  shift_id: number;
  status: "open" | "closed" | string;
  terminal_ref: string;
  terminal_label: string;
  operator: string;
  opened_at: string;
  closed_at: string;
  opening_amount_q: number;
  opening_amount_display: string;
  counted_amount_q: number | null;
  counted_amount_display: string;
  movements: CashMovementRow[];
  movements_in_q: number;
  movements_in_display: string;
  movements_out_q: number;
  movements_out_display: string;
  sales_count: number;
  sales_total_q: number;
  sales_total_display: string;
  sales_by_method: SalesByMethodRow[];
  notes: string;
}

export interface CashDayTotals {
  shifts_count: number;
  sales_count: number;
  sales_total_q: number;
  sales_total_display: string;
  counted_total_q: number;
  counted_total_display: string;
  sales_by_method: SalesByMethodRow[];
}

export interface CashSessionReport {
  date: string;
  date_display: string;
  x_reading: ShiftReading | null;
  has_open_shift: boolean;
  z_readings: ShiftReading[];
  has_closed_shifts: boolean;
  day_totals: CashDayTotals;
}

export interface CashSessionReportResponse {
  report: CashSessionReport;
}
