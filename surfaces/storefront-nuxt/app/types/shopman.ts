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
  has_items: boolean
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
  unit_weight_label: string | null
  approx_dimensions_label: string | null
  ingredients_text: string | null
  trace_notice: string
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
  total_display: string
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
  payment_status: string | null
}
