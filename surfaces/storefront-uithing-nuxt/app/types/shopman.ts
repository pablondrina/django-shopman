export interface CategoryProjection {
  ref: string
  name: string
  icon: string
  url: string
}

export interface CatalogItemProjection {
  sku: string
  slug: string
  name: string
  short_description: string
  image_url: string | null
  category: string | null
  tags: string[]
  search_terms: string[]
  base_price_q: number
  price_display: string
  has_promotion: boolean
  original_price_display: string | null
  promotion_label: string | null
  unit_weight_label: string | null
  availability: 'available' | 'low_stock' | 'planned_ok' | 'unavailable'
  availability_label: string
  can_add_to_cart: boolean
  dietary_info: string[]
  is_new: boolean
  is_featured: boolean
  qty_in_cart: number
  available_qty: number | null
  allergens: string[]
}

export interface CatalogSectionProjection {
  ref: string
  label: string
  icon: string
  description: string
  is_dynamic: boolean
  dynamic_ref: string | null
  category: CategoryProjection | null
  items: CatalogItemProjection[]
}

export interface CatalogProjection {
  items: CatalogItemProjection[]
  categories: CategoryProjection[]
  sections: CatalogSectionProjection[]
  featured: CatalogItemProjection[]
  active_category_ref: string | null
  happy_hour: {
    active: boolean
    discount_percent: number
    start: string
    end: string
  } | null
  favorite_category_ref: string | null
  has_items: boolean
}

export interface ComponentProjection {
  sku: string
  name: string
  qty_display: string
}

export interface ProductAllergenProjection {
  allergens: string[]
  dietary_info: string[]
  serves: string | null
  has_any?: boolean
}

export interface ProductConservationProjection {
  shelf_life_label: string | null
  storage_tip: string | null
  has_any?: boolean
}

export interface NutritionRowProjection {
  field: string
  label: string
  value_display: string
  unit: string
  percent_daily_value: number | null
}

export interface ProductNutritionProjection {
  serving_size_display: string
  servings_per_container: number
  energy_kcal_display: string | null
  energy_pdv: number | null
  rows: NutritionRowProjection[]
  has_any?: boolean
}

export interface ProductDetailProjection {
  sku: string
  slug: string
  name: string
  short_description: string
  long_description: string
  image_url: string | null
  gallery: string[]
  base_price_q: number
  price_display: string
  has_promotion: boolean
  original_price_display: string | null
  promotion_label: string | null
  availability: CatalogItemProjection['availability']
  availability_label: string
  can_add_to_cart: boolean
  available_qty: number | null
  max_qty: number
  qty_in_cart: number
  is_bundle: boolean
  components: ComponentProjection[]
  unit_weight_label: string | null
  approx_dimensions_label: string | null
  allergen: ProductAllergenProjection | null
  conservation: ProductConservationProjection | null
  ingredients_text: string | null
  trace_notice: string
  nutrition: ProductNutritionProjection | null
  seo_description: string
  seo_keywords: string[]
  breadcrumb_category: CategoryProjection | null
}

export interface MinimumOrderProgressProjection {
  minimum_q: number
  remaining_q: number
  percent: number
  minimum_display: string
  remaining_display: string
}

export interface CartItemProjection {
  line_id: string
  sku: string
  name: string
  qty: number
  unit_price_q: number
  total_price_q: number
  price_display: string
  total_display: string
  image_url: string | null
  original_price_display: string | null
  discount_label: string | null
  is_available: boolean
  availability_warning: string | null
  available_qty: number | null
  is_awaiting_confirmation: boolean
  is_ready_for_confirmation: boolean
  confirmation_deadline_iso: string | null
  confirmation_deadline_display: string | null
}

export interface CartProjection {
  items: CartItemProjection[]
  items_count: number
  is_empty: boolean
  summary_pending?: boolean
  subtotal_q: number
  subtotal_display: string
  original_subtotal_q: number
  original_subtotal_display: string
  discount_total_q: number
  discount_total_display: string
  has_discount: boolean
  discount_lines: Array<{ label: string, amount_q: number, amount_display: string }>
  delivery_fee_q: number | null
  delivery_fee_display: string | null
  delivery_is_free: boolean
  grand_total_q: number
  grand_total_display: string
  coupon_code: string | null
  coupon_discount_q: number | null
  coupon_discount_display: string | null
  has_unavailable_items: boolean
  has_awaiting_confirmation_items: boolean
  has_ready_for_confirmation_items: boolean
  minimum_order_progress: MinimumOrderProgressProjection | null
  upsell: { sku: string, name: string, unit_price_q: number, price_display: string, image_url: string | null } | null
  actions: SurfaceActionProjection[]
}

export interface SocialLinkProjection {
  url: string
  platform: string
  label: string
  icon_svg: string
}

export interface ShopDesignTokensProjection {
  background?: string
  foreground?: string
  card?: string
  card_foreground?: string
  popover?: string
  popover_foreground?: string
  primary?: string
  primary_foreground?: string
  secondary?: string
  secondary_foreground?: string
  muted?: string
  muted_foreground?: string
  accent?: string
  accent_foreground?: string
  destructive?: string
  destructive_foreground?: string
  success?: string
  success_foreground?: string
  warning?: string
  warning_foreground?: string
  info?: string
  info_foreground?: string
  border?: string
  input?: string
  ring?: string
  surface?: string
  surface_hover?: string
  foreground_muted?: string
  border_strong?: string
  primary_hover?: string
  secondary_hover?: string
  accent_hover?: string
  error?: string
  error_foreground?: string
  background_hex?: string
  theme_hex?: string
  heading_font?: string
  body_font?: string
  color_mode?: string
  dark?: Record<string, string>
}

export interface ShopProjection {
  brand_name: string
  tagline: string
  description: string
  description_html: string
  logo_url: string
  color_mode: string
  theme_color: string
  background_color?: string
  whatsapp_url: string
  phone: string
  phone_display: string
  phone_url: string
  email: string
  full_address: string
  maps_url: string
  default_city: string
  social_links: SocialLinkProjection[]
  design_tokens?: ShopDesignTokensProjection
}

export interface OmotenashiProjection {
  moment: 'madrugada' | 'manha' | 'almoco' | 'tarde' | 'fechando' | 'fechado'
  greeting: string
  greeting_with_name: string
  shop_hint: string
  customer_name: string | null
  is_birthday: boolean
  audience: 'anon' | 'new' | 'returning' | 'vip'
}

export interface ShopStatusProjection {
  is_open: boolean
  label: string
  message: string | null
  opens_at: string | null
  closes_at: string | null
}

export interface CopyEntryProjection {
  title: string
  message: string
}

export interface HomeHeroCopyProjection {
  birthday_heading: CopyEntryProjection
  birthday_sub: CopyEntryProjection
  order_title_prefix: CopyEntryProjection
  order_title_suffix: CopyEntryProjection
  order_subtitle: CopyEntryProjection
  reorder_title_prefix: CopyEntryProjection
  reorder_title_suffix: CopyEntryProjection
  reorder_subtitle: CopyEntryProjection
  handmade_title_prefix: CopyEntryProjection
  handmade_title_suffix: CopyEntryProjection
  handmade_subtitle: CopyEntryProjection
  menu_cta: CopyEntryProjection
  birthday_cta: CopyEntryProjection
}

export interface HomeSectionsCopyProjection {
  availability_heading: CopyEntryProjection
  full_menu_cta: CopyEntryProjection
  how_it_works_heading: CopyEntryProjection
  how_it_works_intro: CopyEntryProjection
  how_online_heading: CopyEntryProjection
  how_store_heading: CopyEntryProjection
  how_step_choose: CopyEntryProjection
  how_step_pay: CopyEntryProjection
  how_step_fulfill: CopyEntryProjection
  how_self_service_label: CopyEntryProjection
  how_counter_label: CopyEntryProjection
  how_hours_label: CopyEntryProjection
  how_hours_empty: CopyEntryProjection
  how_online_choose_message: CopyEntryProjection
  how_online_pay_message: CopyEntryProjection
  how_online_track_message: CopyEntryProjection
  how_store_self_service_message: CopyEntryProjection
  how_store_counter_message: CopyEntryProjection
  tomorrow_label: CopyEntryProjection
  tomorrow_hook: CopyEntryProjection
  whatsapp_cta: CopyEntryProjection
  whatsapp_cta_label: CopyEntryProjection
}

export interface AuthCopyProjection {
  phone_heading: CopyEntryProjection
  phone_subtitle: CopyEntryProjection
  phone_cta_wa: CopyEntryProjection
  phone_cta_sms: CopyEntryProjection
  trusted_device_message: CopyEntryProjection
  trusted_device_cta: CopyEntryProjection
  trusted_other_phone: CopyEntryProjection
  no_password_note: CopyEntryProjection
  terms_note: CopyEntryProjection
  code_heading: CopyEntryProjection
  code_help: CopyEntryProjection
  name_heading: CopyEntryProjection
  name_subtitle: CopyEntryProjection
  name_cta: CopyEntryProjection
  auth_confirmed: CopyEntryProjection
  device_trust_prompt: CopyEntryProjection
  device_trust_cta: CopyEntryProjection
  device_trust_skip_cta: CopyEntryProjection
}

export interface OpeningHoursEntry {
  label: string
  hours: string
}

export interface LastOrderItemProjection {
  sku: string
  name: string
  qty: number
}

export interface PublicConfigProjection {
  google_maps_api_key: string
  whatsapp_url: string
}

export interface HomeProjection {
  omotenashi: OmotenashiProjection
  hero_copy: HomeHeroCopyProjection
  sections_copy: HomeSectionsCopyProjection
  auth_copy: AuthCopyProjection
  shop: ShopProjection
  shop_status: ShopStatusProjection
  opening_hours: OpeningHoursEntry[]
  last_order_ref: string | null
  last_order_items: LastOrderItemProjection[]
  actions: SurfaceActionProjection[]
  featured_items: CatalogItemProjection[]
  origin_channel: string | null
  public_config: PublicConfigProjection
}

export interface HomeResponse {
  home: HomeProjection
  cart: CartProjection
}

export interface AuthSessionResponse {
  is_authenticated: boolean
  customer_ref: string
  customer_name: string
  customer_phone: string
  customer_email: string
  requires_welcome?: boolean
  welcome_suggested_name?: string
}

export interface MenuResponse {
  catalog: CatalogProjection
  cart: CartProjection
}

export interface ProductResponse {
  product: ProductDetailProjection
  cart: CartProjection
}

export interface CartResponse {
  cart: CartProjection
}

export interface ReorderConflictItemProjection {
  sku: string
  name: string
  qty: number
}

export interface ReorderConflictCopyProjection {
  title: CopyEntryProjection
  message: CopyEntryProjection
  current_cart_label: CopyEntryProjection
  previous_order_label: CopyEntryProjection
  append_help: CopyEntryProjection
  replace_help: CopyEntryProjection
  replace_ack_label: CopyEntryProjection
  cancel_label: CopyEntryProjection
}

export interface ReorderConflictProjection {
  detail: string
  error_code: 'cart_not_empty'
  order_ref: string
  cart: CartProjection
  items: ReorderConflictItemProjection[]
  copy: ReorderConflictCopyProjection
  actions: SurfaceActionProjection[]
}

export interface CartMutationResponse {
  ok: true
  action: 'add' | 'update' | 'remove'
  sku: string
  line: {
    sku: string
    line_id: string | null
    qty: number
    unit_price_q: number
    line_total_q: number
    line_total_display: string
    name: string
  }
  summary: {
    count: number
    subtotal_q: number
    subtotal_display: string
    grand_total_q: number
    grand_total_display: string
    minimum_order_progress: MinimumOrderProgressProjection | null
    checkout_enabled: boolean
  }
  cart: CartProjection
}

export interface ProductMutationMeta {
  sku: string
  name: string
  price_q: number
  price_display: string
  image_url: string | null
}

export interface PaymentMethodProjection {
  ref: string
  label: string
  is_default: boolean
}

export interface PickupSlotProjection {
  ref: string
  label: string
  starts_at: string
  enabled: boolean
  reason: string
  is_earliest: boolean
}

export interface SavedAddressProjection {
  id: number
  label: string
  label_key?: 'home' | 'work' | 'other' | string
  label_custom?: string
  formatted_address: string
  complement: string
  delivery_instructions: string
  is_default: boolean
  route?: string
  street_number?: string
  neighborhood?: string
  city?: string
  state_code?: string
  postal_code?: string
  latitude?: number | null
  longitude?: number | null
  place_id?: string | null
}

export interface StructuredAddressProjection {
  formatted_address?: string
  route?: string
  street_number?: string
  neighborhood?: string
  city?: string
  state_code?: string
  postal_code?: string
  country?: string
  country_code?: string
  latitude?: number | null
  longitude?: number | null
  place_id?: string | null
}

export interface SurfaceActionProjection {
  ref: string
  kind: 'mutation' | 'link' | 'external' | 'copy' | 'instruction' | string
  label: string
  priority: 'primary' | 'secondary' | 'danger' | 'quiet' | string
  enabled: boolean
  reason: string
  method: string
  href: string
  payload_schema: Record<string, unknown>
  idempotency: 'none' | 'recommended' | 'required' | string
  confirmation: Record<string, unknown>
}

export interface CheckoutProjection {
  cart: CartProjection
  customer_phone: string
  customer_name: string
  is_authenticated: boolean
  requires_authentication: boolean
  auth_action: SurfaceActionProjection | null
  saved_addresses: SavedAddressProjection[]
  preselected_address_id: number | null
  payment_methods: PaymentMethodProjection[]
  default_payment_method: string
  actions: SurfaceActionProjection[]
  fulfillment_options: Array<'pickup' | 'delivery' | string>
  has_pickup: boolean
  has_delivery: boolean
  pickup_slots: PickupSlotProjection[]
  earliest_slot_ref: string | null
  loyalty_balance_q: number
  loyalty_value_display: string | null
  max_preorder_days: number
  closed_dates_json: string
  is_debug: boolean
  support_whatsapp_url: string
  pickup_hint: string
  delivery_hint: string
}

export interface CheckoutResponse {
  checkout: CheckoutProjection
}

export interface CheckoutMutationResponse {
  order_ref: string
  status: string
  next_url?: string
}

export interface TrackingPromiseRowProjection {
  label: string
  value: string
  url: string | null
}

export interface TrackingPromiseProjection {
  state: string
  title: string
  message: string
  tone: 'success' | 'warning' | 'danger' | 'info' | string
  deadline_at: string | null
  deadline_kind: string | null
  timer_mode: string
  deadline_action: string
  requires_active_notification: boolean
  notification_topic: string | null
  actions: SurfaceActionProjection[]
  next_event: string
  recovery: string
  active_notification: string
}

export interface OrderProgressStepProjection {
  label: string
  key: string
  state: 'completed' | 'current' | 'pending' | 'cancelled' | string
  timestamp_display: string | null
}

export interface TimelineEventProjection {
  label: string
  event_type: string
  timestamp_display: string
}

export interface OrderItemProjection {
  sku: string
  name: string
  qty: number
  unit_price_display: string
  total_display: string
}

export interface TrackingFulfillmentProjection {
  status: string
  status_label: string
  tracking_label: string
  tracking_code: string | null
  tracking_url: string | null
  carrier: string | null
  dispatched_at: string | null
  delivered_at: string | null
}

export interface PickupInfoProjection {
  heading: string
  address: string
  opening_hours: string
  directions_label: string
  directions_url: string | null
}

export interface TrackingCopyProjection {
  page_kicker: string
  order_ref_label: string
  menu_label: string
  support_label: string
  progress_heading: string
  live_badge: string
  polling_badge: string
  finished_badge: string
  items_heading: string
  total_label: string
  delivery_fee_label: string
  promise_fallback_message: string
  payment_confirmed_notice: string
  retry_label: string
  not_found_title: string
  not_found_description: string
  rate_limit_title: string
  cancel_success_title: string
  cancel_success_message: string
  cancel_failed_message: string
  mock_payment_success_title: string
  mock_payment_success_message: string
  mock_payment_failed_title: string
  mock_payment_failed_message: string
  rating_success_title: string
  rating_failed_message: string
  rating_comment_placeholder: string
  rating_comment_aria_label: string
  rating_submit_label: string
}

export interface TrackingResponse {
  ref: string
  status: string
  status_label: string
  status_color: string
  copy: TrackingCopyProjection
  promise: TrackingPromiseProjection
  promise_rows: TrackingPromiseRowProjection[]
  promise_deadline_label: string
  progress_steps: OrderProgressStepProjection[]
  total_display: string
  delivery_fee_display: string | null
  is_delivery: boolean
  timeline: TimelineEventProjection[]
  items: OrderItemProjection[]
  delivery_fulfillments: TrackingFulfillmentProjection[]
  pickup_fulfillments: TrackingFulfillmentProjection[]
  fulfillments: TrackingFulfillmentProjection[]
  pickup_info: PickupInfoProjection | null
  actions: SurfaceActionProjection[]
  is_active: boolean
  server_now_iso: string
  payment_pending: boolean
  payment_expired: boolean
  payment_confirmed: boolean
  show_payment_confirmed_notice: boolean
  payment_status_label: string | null
  payment_status: string | null
  payment_expires_at: string | null
  requires_payment_gate: boolean
  payment_gate_url: string | null
  confirmation_countdown: boolean
  confirmation_expires_at: string | null
  eta_display: string | null
  whatsapp_url: string
  support_url: string
  share_text: string
  is_debug: boolean
  last_updated_iso: string
  last_updated_display: string
  stale_after_seconds: number
}

export interface PaymentPromiseProjection {
  state: string
  title: string
  message: string
  tone: 'success' | 'warning' | 'danger' | 'info' | string
  actions: SurfaceActionProjection[]
  deadline_at: string | null
  deadline_kind: string | null
  deadline_action: string
  requires_active_notification: boolean
  next_event: string
  recovery: string
  active_notification: string
  stale_after_seconds: number | null
}

export interface PaymentProjection {
  order_ref: string
  method: string
  order_status: string
  payment_status: string | null
  total_display: string
  promise: PaymentPromiseProjection
  pix_qr_code: string | null
  pix_copy_paste: string | null
  pix_expires_at: string | null
  checkout_url: string | null
  status_url: string
  tracking_url: string
  server_now_iso: string
  actions: SurfaceActionProjection[]
  error_message: string | null
  is_debug: boolean
}

export interface PaymentResponse {
  redirect_url: string | null
  intent_ready?: boolean
  reason?: string
  payment: PaymentProjection | null
}

export interface PaymentStatusResponse {
  order_ref: string
  promise: PaymentPromiseProjection
  is_paid: boolean
  is_cancelled: boolean
  is_expired: boolean
  is_terminal: boolean
  redirect_url: string
  should_redirect: boolean
}

export interface RemoteConversationProjection {
  order_ref: string
  order_status: string
  channel_ref: string
  source_projection: 'tracking' | 'payment' | string
  state: string
  title: string
  message: string
  tone: 'success' | 'warning' | 'danger' | 'info' | string
  actions: SurfaceActionProjection[]
  deadline_at: string | null
  next_event: string
  recovery: string
  items_summary: string[]
  total_display: string
  tracking_url: string
  payment_url: string | null
  supports_access_link: boolean
  requires_payment_gate: boolean
}
