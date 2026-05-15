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
  upsell: { sku: string, name: string, price_display: string, image_url: string | null } | null
}

export interface SocialLinkProjection {
  url: string
  platform: string
  label: string
  icon_svg: string
}

export interface ShopProjection {
  brand_name: string
  tagline: string
  description: string
  description_html: string
  logo_url: string
  color_mode: string
  theme_color: string
  whatsapp_url: string
  phone: string
  phone_display: string
  phone_url: string
  email: string
  full_address: string
  maps_url: string
  default_city: string
  social_links: SocialLinkProjection[]
}

export interface OmotenashiProjection {
  moment: 'madrugada' | 'manha' | 'almoco' | 'tarde' | 'fechando' | 'fechado'
  greeting: string
  greeting_with_name: string
  shop_hint: string
  customer_name: string | null
  is_birthday: boolean
  audience: 'anon' | 'new' | 'returning' | 'vip'
  is_open: boolean
  opens_at: string | null
  closes_at: string | null
}

export interface ShopStatusProjection {
  is_open: boolean
  message: string | null
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
  shop: ShopProjection
  shop_status: ShopStatusProjection
  opening_hours: OpeningHoursEntry[]
  last_order_ref: string | null
  last_order_items: LastOrderItemProjection[]
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

export interface CartCommandResponse {
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

export interface ProductCommandMeta {
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
}

export interface SavedAddressProjection {
  id: number
  label: string
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

export interface CheckoutProjection {
  cart: CartProjection
  customer_phone: string
  customer_name: string
  is_authenticated: boolean
  saved_addresses: SavedAddressProjection[]
  preselected_address_id: number | null
  payment_methods: PaymentMethodProjection[]
  default_payment_method: string
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

export interface CheckoutCommandResponse {
  order_ref: string
  status: string
  next_url?: string
}

export interface TrackingResponse {
  ref: string
  status: string
  status_label: string
  status_color: string
  promise: {
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
    customer_action: string
    customer_action_label: string
    customer_action_url: string | null
    next_event: string
    recovery: string
    active_notification: string
  }
  progress_steps: Array<{
    label: string
    key: string
    state: 'completed' | 'current' | 'pending' | 'cancelled' | string
    timestamp_display: string | null
  }>
  total_display: string
  delivery_fee_display: string | null
  is_delivery: boolean
  timeline: Array<{
    label: string
    event_type: string
    timestamp_display: string
  }>
  items: Array<{
    sku: string
    name: string
    qty: number
    unit_price_display: string
    total_display: string
  }>
  fulfillments: Array<{
    status: string
    status_label: string
    tracking_code: string | null
    tracking_url: string | null
    carrier: string | null
    dispatched_at: string | null
    delivered_at: string | null
  }>
  pickup_info: {
    address: string
    opening_hours: string
    google_maps_url: string | null
  } | null
  can_cancel: boolean
  is_active: boolean
  server_now_iso: string
  payment_pending: boolean
  payment_expired: boolean
  payment_confirmed: boolean
  show_payment_confirmed_notice: boolean
  payment_status: string | null
  payment_expires_at: string | null
  requires_payment_gate: boolean
  payment_gate_url: string | null
  can_rate: boolean
  rating_url: string | null
  confirmation_countdown: boolean
  confirmation_expires_at: string | null
  eta_display: string | null
  whatsapp_url: string
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
  customer_action: string
  customer_action_label: string
  customer_action_url: string | null
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
  total_display: string
  promise: PaymentPromiseProjection
  pix_qr_code: string | null
  pix_copy_paste: string | null
  pix_expires_at: string | null
  checkout_url: string | null
  status_url: string
  tracking_url: string
  server_now_iso: string
  error_message: string | null
  is_debug: boolean
  can_mock_confirm: boolean
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
}
