from __future__ import annotations

from django.urls import path
from django.views.generic import TemplateView

from . import views
from .views.pwa import ManifestView, OfflineView, ServiceWorkerView

app_name = "storefront"

urlpatterns = [
    # Home
    path("", views.HomeView.as_view(), name="home"),
    # Bridge token
    path("bridge/", views.BridgeTokenView.as_view(), name="bridge_token"),
    # PWA
    path("manifest.json", ManifestView.as_view(), name="manifest"),
    path("sw.js", ServiceWorkerView.as_view(), name="service_worker"),
    path("offline/", OfflineView.as_view(), name="offline"),
    # SEO
    path(
        "robots.txt",
        TemplateView.as_view(template_name="storefront/robots.txt", content_type="text/plain"),
        name="robots_txt",
    ),
    path("sitemap.xml", views.SitemapView.as_view(), name="sitemap"),
    # Menu
    path("menu/", views.MenuView.as_view(), name="menu"),
    path("menu/search/", views.MenuSearchView.as_view(), name="menu_search"),
    path("menu/<slug:collection>/", views.MenuView.as_view(), name="menu_collection"),
    path("produto/<str:sku>/", views.ProductDetailView.as_view(), name="product_detail"),
    # Cart
    path("cart/", views.CartView.as_view(), name="cart"),
    path("cart/add/", views.AddToCartView.as_view(), name="cart_add"),
    path("cart/update/", views.UpdateCartItemView.as_view(), name="cart_update"),
    path("cart/remove/", views.RemoveCartItemView.as_view(), name="cart_remove"),
    path("cart/content/", views.CartContentPartialView.as_view(), name="cart_content"),
    path("cart/summary/", views.CartSummaryView.as_view(), name="cart_summary"),
    path("cart/floating-bar/", views.FloatingCartBarView.as_view(), name="floating_cart_bar"),
    path("cart/check/", views.CartCheckView.as_view(), name="cart_check"),
    path("cart/drawer/", views.CartDrawerContentView.as_view(), name="cart_drawer"),
    path("cart/quick-add/<str:sku>/", views.QuickAddView.as_view(), name="cart_quick_add"),
    path("cart/coupon/", views.ApplyCouponView.as_view(), name="cart_apply_coupon"),
    path("cart/coupon/remove/", views.RemoveCouponView.as_view(), name="cart_remove_coupon"),
    # Checkout
    path("checkout/", views.CheckoutView.as_view(), name="checkout"),
    path("checkout/cep-lookup/", views.CepLookupView.as_view(), name="cep_lookup"),
    path("checkout/customer-lookup/", views.CustomerLookupView.as_view(), name="customer_lookup"),
    path("checkout/request-code/", views.RequestCodeView.as_view(), name="request_code"),
    path("checkout/verify-code/", views.VerifyCodeView.as_view(), name="verify_code"),
    path("pedido/<str:ref>/confirmacao/", views.OrderConfirmationView.as_view(), name="order_confirmation"),
    # Payment
    path("pedido/<str:ref>/pagamento/", views.PaymentView.as_view(), name="order_payment"),
    path("pedido/<str:ref>/pagamento/status/", views.PaymentStatusView.as_view(), name="payment_status_partial"),
    # Mock payment (view guards with DEBUG check — 404 in production)
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
    path("minha-conta/perfil/", views.ProfileUpdateView.as_view(), name="profile_update"),
    path("minha-conta/perfil/display/", views.ProfileDisplayView.as_view(), name="profile_display"),
    path("minha-conta/perfil/edit/", views.ProfileEditView.as_view(), name="profile_edit"),
    path("minha-conta/notificacoes/", views.NotificationPrefsToggleView.as_view(), name="notification_prefs_toggle"),
    path("minha-conta/preferencias/", views.FoodPreferenceToggleView.as_view(), name="food_preference_toggle"),
    path("minha-conta/exportar/", views.DataExportView.as_view(), name="data_export"),
    path("minha-conta/excluir/", views.AccountDeleteView.as_view(), name="account_delete"),
    # Auth
    path("login/", views.LoginView.as_view(), name="login"),
    path("auth/access/<str:token>/", views.AccessLinkLoginView.as_view(), name="access_link_login"),
    path("auth/device-check/", views.DeviceCheckLoginView.as_view(), name="device_check_login"),
    # Device management
    path("auth/devices/", views.DeviceListView.as_view(), name="device_list"),
    path("auth/devices/<uuid:device_id>/", views.DeviceRevokeView.as_view(), name="device_revoke"),
    path("auth/devices/revoke-all/", views.DeviceRevokeAllView.as_view(), name="device_revoke_all"),
    # Info pages
    path("como-funciona/", views.HowItWorksView.as_view(), name="como_funciona"),
    # Operator: Gestor de Pedidos
    path("pedidos/", views.GestorPedidosView.as_view(), name="gestor_pedidos"),
    path("pedidos/list/", views.OrderListPartialView.as_view(), name="gestor_list_partial"),
    path("pedidos/<str:ref>/detail/", views.PedidoDetailPartialView.as_view(), name="gestor_detail"),
    path("pedidos/<str:ref>/confirm/", views.PedidoConfirmView.as_view(), name="gestor_confirm"),
    path("pedidos/<str:ref>/reject/", views.PedidoRejectView.as_view(), name="gestor_reject"),
    path("pedidos/<str:ref>/advance/", views.PedidoAdvanceView.as_view(), name="gestor_advance"),
    path("pedidos/<str:ref>/notes/", views.PedidoNotesView.as_view(), name="gestor_notes"),
    # Operator: POS (Balcao)
    path("gestao/pos/", views.pos_view, name="pos"),
    path("gestao/pos/customer-lookup/", views.pos_customer_lookup, name="pos_customer_lookup"),
    path("gestao/pos/close/", views.pos_close, name="pos_close"),
    # Operator: Production
    path("gestao/producao/criar/", views.bulk_create_work_orders, name="bulk_create_work_orders"),
    # Operator: KDS (Kitchen Display System)
    path("kds/", views.KDSIndexView.as_view(), name="kds_index"),
    path("kds/<slug:ref>/", views.KDSDisplayView.as_view(), name="kds_display"),
    path("kds/<slug:ref>/tickets/", views.KDSTicketListPartialView.as_view(), name="kds_ticket_list"),
    path("kds/ticket/<int:pk>/check/", views.KDSTicketCheckItemView.as_view(), name="kds_ticket_check"),
    path("kds/ticket/<int:pk>/done/", views.KDSTicketDoneView.as_view(), name="kds_ticket_done"),
    path("kds/expedition/<int:pk>/action/", views.KDSExpeditionActionView.as_view(), name="kds_expedition_action"),
]
