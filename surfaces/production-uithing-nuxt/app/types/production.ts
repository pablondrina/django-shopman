// TS mirror of the Django production projections
// (shopman/backstage/projections/production.py), serialised by
// backstage/api/projections.py. Kept in lockstep with those dataclasses — the
// surface renders intent, never rules.

export type ProductionTimerClass = "timer-ok" | "timer-warning" | "timer-late";

// ── Live floor (KDS) ───────────────────────────────────────────────────────

export interface ProductionKDSCardProjection {
  pk: number;
  ref: string;
  output_sku: string;
  recipe_name: string;
  started_qty: string;
  operator_ref: string;
  position_ref: string;
  started_at_display: string;
  elapsed_seconds: number;
  elapsed_minutes: number;
  target_seconds: number;
  timer_class: ProductionTimerClass;
  current_step: string;
  current_step_index: number | null;
  total_steps: number;
  current_step_name: string;
  step_progress_pct: number;
  next_step_name: string;
  time_remaining_min: number | null;
  can_finish: boolean;
  order_refs: string[];
}

export interface ProductionKDSProjection {
  selected_date: string;
  selected_date_display: string;
  cards: ProductionKDSCardProjection[];
  total_count: number;
  late_count: number;
}

export interface ProductionKDSResponse {
  kds: ProductionKDSProjection;
}

// ── Planning board (matrix) ────────────────────────────────────────────────

export interface OrderCommitmentProjection {
  ref: string;
  status: string;
  status_label: string;
  qty_required: string;
}

export interface BaseRecipeUsageProjection {
  ref: string;
  output_sku: string;
  name: string;
  quantity_display: string;
  per_unit_display: string;
}

export interface WorkOrderCardProjection {
  pk: number;
  ref: string;
  recipe_pk: number;
  recipe_ref: string;
  recipe_name: string;
  base_usages: BaseRecipeUsageProjection[];
  output_sku: string;
  status: string;
  status_label: string;
  status_color: string;
  planned_qty: string;
  started_qty: string;
  finished_qty: string;
  yield_rate: string;
  loss: string;
  operator_ref: string;
  position_ref: string;
  target_date_display: string;
  started_at_display: string;
  created_at_display: string;
  progress_pct: number;
  committed_qty: string;
  order_commitments: OrderCommitmentProjection[];
  can_void: boolean;
}

export interface ProductionCountsProjection {
  total: number;
  planned: number;
  started: number;
  finished: number;
  void: number;
  planned_qty: string;
  started_qty: string;
  finished_qty: string;
  loss_qty: string;
}

export interface RecipeOptionProjection {
  pk: number;
  ref: string;
  name: string;
}

export interface PositionOptionProjection {
  pk: number;
  ref: string;
  name: string;
  is_default: boolean;
}

export interface ProductionSuggestionProjection {
  recipe_pk: number;
  recipe_ref: string;
  recipe_name: string;
  base_usages: BaseRecipeUsageProjection[];
  output_sku: string;
  quantity: string;
  committed: string;
  avg_demand: string;
  confidence: string;
  sample_size: number;
  high_demand_applied: boolean;
  explanation_parts: string[];
}

export interface ProductionMatrixRowProjection {
  recipe_pk: number | null;
  output_sku: string;
  recipe_name: string;
  base_usages: BaseRecipeUsageProjection[];
  suggestion: ProductionSuggestionProjection | null;
  planned_orders: WorkOrderCardProjection[];
  started_orders: WorkOrderCardProjection[];
  finished_orders: WorkOrderCardProjection[];
  planned_qty: string;
  started_qty: string;
  finished_qty: string;
  loss_qty: string;
}

export interface ProductionBoardProjection {
  selected_date: string;
  selected_date_display: string;
  selected_position_ref: string;
  selected_operator_ref: string;
  selected_base_recipe: string;
  work_orders: WorkOrderCardProjection[];
  counts: ProductionCountsProjection;
  planned_queue: WorkOrderCardProjection[];
  started_queue: WorkOrderCardProjection[];
  finished_queue: WorkOrderCardProjection[];
  recipes: RecipeOptionProjection[];
  base_recipes: { ref: string; output_sku: string; name: string; count: number }[];
  positions: PositionOptionProjection[];
  suggestions: ProductionSuggestionProjection[];
  matrix_rows: ProductionMatrixRowProjection[];
  default_position_pk: number | null;
}

export interface ProductionBoardResponse {
  board: ProductionBoardProjection;
}

// ── Structured shortage envelope (material/order) ──────────────────────────
// Mirrors backstage/api/operations.py `_shortage_response` (HTTP 409).

export interface MaterialShortageItem {
  sku: string;
  needed: string;
  available: string;
  shortage: string;
}

export interface MaterialShortageError {
  code: "material_shortage";
  work_order_ref: string;
  missing: MaterialShortageItem[];
}

export interface OrderShortageError {
  code: "order_shortage";
  work_order_ref: string;
  required: string;
  requested: string;
  order_refs: string[];
}

export type ProductionShortageError = MaterialShortageError | OrderShortageError;

// ── Operator alerts (shared backstage projection) ──────────────────────────

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

// ── Mise en place (aggregated material needs) ───────────────────────────────

export interface MiseEnPlaceBreakdownProjection {
  recipe_name: string;
  output_sku: string;
  quantity_display: string;
}

export interface MiseEnPlaceLineProjection {
  sku: string;
  name: string;
  quantity_display: string;
  unit: string;
  is_subrecipe: boolean;
  available_display: string;
  is_short: boolean;
  breakdown: MiseEnPlaceBreakdownProjection[];
}

export interface ProductionMiseEnPlaceProjection {
  selected_date: string;
  selected_date_display: string;
  expanded: boolean;
  lines: MiseEnPlaceLineProjection[];
  has_lines: boolean;
  work_order_count: number;
  has_stock_readings: boolean;
}

export interface MiseEnPlaceResponse {
  mise_en_place: ProductionMiseEnPlaceProjection;
}

// ── Weighing (per-prep tickets + blind codes) ───────────────────────────────

export interface WeighingIngredientProjection {
  sku: string;
  name: string;
  quantity_display: string;
  is_subrecipe: boolean;
}

export interface WeighingTicketProjection {
  recipe_ref: string;
  output_sku: string;
  name: string;
  output_quantity_display: string;
  dough_weight_display: string;
  sources_display: string;
  ingredients: WeighingIngredientProjection[];
  blind_code: string;
  made_display: string;
  expiry_display: string;
}

export interface ProductionWeighingProjection {
  selected_date: string;
  selected_date_display: string;
  tickets: WeighingTicketProjection[];
}

export interface WeighingResponse {
  weighing: ProductionWeighingProjection;
}
