// AUTO-GENERATED — do not edit by hand.
// Source of truth: shopman/backstage/projections/production.py
// Regenerate with: python manage.py export_production_schema

/** A compact order commitment for a production work order. */
export interface OrderCommitmentProjection {
  ref: string;
  status: string;
  status_label: string;
  qty_required: string;
}

/** How much of a base recipe is used by an output SKU recipe. */
export interface BaseRecipeUsageProjection {
  ref: string;
  output_sku: string;
  name: string;
  quantity_display: string;
  per_unit_display: string;
}

/** A single work order card on the production board. */
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

/** Aggregate counts for the production board header. */
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

/** A recipe available for quick production form. */
export interface RecipeOptionProjection {
  pk: number;
  ref: string;
  name: string;
}

/** A base recipe available as an operational filter. */
export interface BaseRecipeOptionProjection {
  ref: string;
  output_sku: string;
  name: string;
  count: number;
}

/** A stock position available for production form. */
export interface PositionOptionProjection {
  pk: number;
  ref: string;
  name: string;
  is_default: boolean;
}

/** A suggested production row from Craftsman demand planning. */
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

/** A high-volume production matrix row grouped by SKU. */
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

/** A matrix row within a base recipe group. */
export interface ProductionMatrixGroupRowProjection {
  row: ProductionMatrixRowProjection;
  usage: BaseRecipeUsageProjection | null;
}

/** A group of production matrix rows that share a base recipe. */
export interface ProductionMatrixGroupProjection {
  ref: string;
  output_sku: string;
  name: string;
  rows: ProductionMatrixGroupRowProjection[];
}

/** Column-level access for the production board surface. */
export interface ProductionSurfaceAccess {
  can_manage_all: boolean;
  can_view_suggested: boolean;
  can_edit_suggested: boolean;
  can_view_planned: boolean;
  can_edit_planned: boolean;
  can_view_started: boolean;
  can_edit_started: boolean;
  can_view_finished: boolean;
  can_edit_finished: boolean;
  can_view_unsold: boolean;
  can_edit_unsold: boolean;
}

/** Top-level read model for the production board. */
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
  base_recipes: BaseRecipeOptionProjection[];
  positions: PositionOptionProjection[];
  suggestions: ProductionSuggestionProjection[];
  matrix_rows: ProductionMatrixRowProjection[];
  matrix_groups: ProductionMatrixGroupProjection[];
  default_position_pk: number | null;
  access: ProductionSurfaceAccess;
}

/** A started work order card for the production KDS. */
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
  timer_class: string;
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

/** Top-level read model for the production KDS. */
export interface ProductionKDSProjection {
  selected_date: string;
  selected_date_display: string;
  cards: ProductionKDSCardProjection[];
  total_count: number;
  late_count: number;
}

/** ForecastRowProjection(ref: 'str', output_sku: 'str', recipe_name: 'str', qty: 'str', eta_display: 'str', eta_is_actual: 'bool', status: 'str', status_label: 'str', history_days: 'int') */
export interface ForecastRowProjection {
  ref: string;
  output_sku: string;
  recipe_name: string;
  qty: string;
  eta_display: string;
  eta_is_actual: boolean;
  status: string;
  status_label: string;
  history_days: number;
}

/** ProductionForecastProjection(selected_date: 'str', selected_date_display: 'str', generated_at_display: 'str', rows: 'tuple[ForecastRowProjection, ...]') */
export interface ProductionForecastProjection {
  selected_date: string;
  selected_date_display: string;
  generated_at_display: string;
  rows: ForecastRowProjection[];
}

/** Quanto deste insumo cada receita do dia consome. */
export interface MiseEnPlaceBreakdownProjection {
  recipe_name: string;
  output_sku: string;
  quantity_display: string;
}

/** One aggregated ingredient line for the day's mise en place. */
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

/** Aggregated material needs for the day's open work orders. */
export interface ProductionMiseEnPlaceProjection {
  selected_date: string;
  selected_date_display: string;
  expanded: boolean;
  lines: MiseEnPlaceLineProjection[];
  has_lines: boolean;
  work_order_count: number;
  has_stock_readings: boolean;
}

/** One ingredient line for a thermal weighing ticket. */
export interface ProductionWeighingIngredientProjection {
  sku: string;
  name: string;
  quantity_display: string;
  is_subrecipe: boolean;
}

/** A printable 80mm-oriented ticket for one recipe/base recipe. */
export interface ProductionWeighingTicketProjection {
  recipe_ref: string;
  output_sku: string;
  name: string;
  output_quantity_display: string;
  dough_weight_display: string;
  sources_display: string;
  ingredients: ProductionWeighingIngredientProjection[];
  table: Record<string, unknown>;
  blind_code: string;
  made_display: string;
  expiry_display: string;
}

/** Printable weighing tickets for saved production planning. */
export interface ProductionWeighingProjection {
  selected_date: string;
  selected_date_display: string;
  selected_position_ref: string;
  selected_base_recipe: string;
  tickets: ProductionWeighingTicketProjection[];
}
