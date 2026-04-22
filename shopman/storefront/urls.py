"""Storefront URL configuration — customer-facing routes."""

from __future__ import annotations

from django.urls import path
from django.views.generic import TemplateView
from django_eventstream.views import events as eventstream_view

from shopman.storefront import views
from shopman.storefront.views.pwa import ManifestView, ServiceWorkerView

app_name = "storefront"

urlpatterns = [
    # Home
    path("", views.HomeView.as_view(), name="home"),
    # AccessLink entry — pre-authenticated link from notifications
    path("a/", views.AccessLinkEntryView.as_view(), name="access_link_entry"),
    # PWA
    path("manifest.json", ManifestView.as_view(), name="manifest"),
    path("sw.js", ServiceWorkerView.as_view(), name="service_worker"),
    path("offline/", views.OfflineView.as_view(), name="offline"),
    # SEO
    path(
        "robots.txt",
        TemplateView.as_view(template_name="storefront/robots.txt", content_type="text/plain"),
        name="robots_txt",
    ),
    path("sitemap.xml", views.SitemapView.as_view(), name="sitemap"),
    # Server-Sent Events: per-channel availability push
    path(
        "storefront/stock/events/<slug:channel_ref>/",
        eventstream_view,
        {"format-channels": ["stock-{channel_ref}"]},
        name="stock_events",
    ),
    # SSE: per-order status push
    path(
        "pedido/<str:ref>/events/",
        eventstream_view,
        {"format-channels": ["order-{ref}"]},
        name="order_events",
    ),
    # Per-SKU availability badge
    path(
        "storefront/sku/<str:sku>/state/",
        views.SkuStateView.as_view(),
        name="sku_state",
    ),
    # Menu
    path("menu/", views.MenuView.as_view(), name="menu"),
    path("prototipo/menu/", TemplateView.as_view(template_name="storefront/prototype_menu.html"), name="prototype_menu"),
    path("menu/<slug:collection>/", views.MenuView.as_view(), name="menu_collection"),
    path("produto/<str:sku>/", views.ProductDetailView.as_view(), name="product_detail"),
    path("dicas/", views.TipsView.as_view(), name="dicas"),
    # Cart
    path("cart/", views.CartView.as_view(), name="cart"),
    path("cart/add/", views.AddToCartView.as_view(), name="cart_add"),
    path("cart/set-qty/", views.CartSetQtyBySkuView.as_view(), name="cart_set_qty"),
    path("cart/page/", views.CartPageContentView.as_view(), name="cart_page_content"),
    path("cart/summary/", views.CartSummaryView.as_view(), name="cart_summary"),
    path("cart/drawer/", views.CartDrawerContentProjView.as_view(), name="cart_drawer"),
    path("cart/quick-add/<str:sku>/", views.QuickAddView.as_view(), name="cart_quick_add"),
    path("cart/coupon/", views.ApplyCouponView.as_view(), name="cart_apply_coupon"),
    path("cart/coupon/remove/", views.RemoveCouponView.as_view(), name="cart_remove_coupon"),
    # Checkout
    path("checkout/", views.CheckoutView.as_view(), name="checkout"),
    path(
        "checkout/summary/",
        views.CheckoutOrderSummaryView.as_view(),
        name="checkout_order_summary",
    ),
    path("checkout/cep-lookup/", views.CepLookupView.as_view(), name="cep_lookup"),
    path("checkout/simular-ifood/", views.SimulateIFoodView.as_view(), name="simulate_ifood"),
    path("checkout/customer-lookup/", views.CustomerLookupView.as_view(), name="customer_lookup"),
    path("checkout/request-code/", views.RequestCodeView.as_view(), name="request_code"),
    path("checkout/verify-code/", views.VerifyCodeView.as_view(), name="verify_code"),
    path("pedido/<str:ref>/confirmacao/", views.OrderConfirmationView.as_view(), name="order_confirmation"),
    # Payment
    path("pedido/<str:ref>/pagamento/", views.PaymentView.as_view(), name="order_payment"),
    path("pedido/<str:ref>/pagamento/status/", views.PaymentStatusView.as_view(), name="payment_status_partial"),
    path("pedido/<str:ref>/pagamento/mock-confirm/", views.MockPaymentConfirmView.as_view(), name="mock_payment_confirm"),
    # Tracking
    path("pedido/<str:ref>/", views.OrderTrackingView.as_view(), name="order_tracking"),
    path("pedido/<str:ref>/status/", views.OrderStatusPartialView.as_view(), name="order_status_partial"),
    path("pedido/<str:ref>/cancelar/", views.OrderCancelView.as_view(), name="order_cancel"),
    # History
    path("meus-pedidos/<str:ref>/reorder/", views.ReorderView.as_view(), name="reorder"),
    path("meus-pedidos/", views.OrderHistoryView.as_view(), name="order_history"),
    # Account
    path("minha-conta/", views.AccountView.as_view(), name="account"),
    path("minha-conta/enderecos/", views.AddressCreateView.as_view(), name="address_create"),
    path("minha-conta/enderecos/<int:pk>/", views.AddressUpdateView.as_view(), name="address_update"),
    path("minha-conta/enderecos/<int:pk>/delete/", views.AddressDeleteView.as_view(), name="address_delete"),
    path("minha-conta/enderecos/<int:pk>/default/", views.AddressSetDefaultView.as_view(), name="address_set_default"),
    path("minha-conta/enderecos/<int:pk>/label/", views.AddressLabelUpdateView.as_view(), name="address_label_update"),
    path("minha-conta/perfil/", views.ProfileUpdateView.as_view(), name="profile_update"),
    path("minha-conta/perfil/display/", views.ProfileDisplayView.as_view(), name="profile_display"),
    path("minha-conta/perfil/edit/", views.ProfileEditView.as_view(), name="profile_edit"),
    path("minha-conta/notificacoes/", views.NotificationPrefsToggleView.as_view(), name="notification_prefs_toggle"),
    path("minha-conta/preferencias/", views.FoodPreferenceToggleView.as_view(), name="food_preference_toggle"),
    path("minha-conta/exportar/", views.DataExportView.as_view(), name="data_export"),
    path("minha-conta/excluir/", views.AccountDeleteView.as_view(), name="account_delete"),
    # Auth
    path("login/", views.LoginView.as_view(), name="login"),
    path("bem-vindo/", views.WelcomeView.as_view(), name="welcome"),
    path("auth/access/<str:token>/", views.AccessLinkLoginView.as_view(), name="access_link_login"),
    path("auth/device-check/", views.DeviceCheckLoginView.as_view(), name="device_check_login"),
    # Device management
    path("auth/devices/", views.DeviceListView.as_view(), name="device_list"),
    path("auth/devices/<uuid:device_id>/", views.DeviceRevokeView.as_view(), name="device_revoke"),
    path("auth/devices/revoke-all/", views.DeviceRevokeAllView.as_view(), name="device_revoke_all"),
    # Info pages
    path("como-funciona/", views.HowItWorksView.as_view(), name="como_funciona"),
]
