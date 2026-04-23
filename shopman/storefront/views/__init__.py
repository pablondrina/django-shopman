"""Storefront views — customer-facing web surface (HTMX + Alpine)."""

from .account import (
    AccountDeleteView,
    AccountView,
    AddressCreateView,
    AddressDeleteView,
    AddressLabelUpdateView,
    AddressSetDefaultView,
    AddressUpdateView,
    DataExportView,
    FoodPreferenceToggleView,
    NotificationPrefsToggleView,
    ProfileDisplayView,
    ProfileEditView,
    ProfileUpdateView,
)
from .auth import (
    AccessLinkLoginView,
    CustomerLookupView,
    DeviceCheckLoginView,
    LoginView,
    RequestCodeView,
    TrustDeviceView,
    VerifyCodeView,
)
from .access import AccessLinkEntryView
from .cart import (
    AddToCartView,
    ApplyCouponView,
    CartDrawerContentProjView,
    CartPageContentView,
    CartSetQtyBySkuView,
    CartSummaryView,
    CartView,
    QuickAddView,
    RemoveCouponView,
)
from .catalog import MenuView, ProductDetailView, TipsView
from .checkout import (
    CepLookupView,
    CheckoutOrderSummaryView,
    CheckoutView,
    OrderConfirmationView,
    SimulateIFoodView,
)
from .devices import DeviceListView, DeviceRevokeAllView, DeviceRevokeView
from .home import HomeView
from .info import HowItWorksView, OrderHistoryView, SitemapView
from .payment import MockPaymentConfirmView, PaymentStatusView, PaymentView
from .pwa import OfflineView
from .sse_state import SkuStateView
from .tracking import OrderCancelView, OrderStatusPartialView, OrderTrackingView, ReorderView
from .welcome import WelcomeView

__all__ = [
    "AccessLinkLoginView",
    "AccountDeleteView",
    "AccountView",
    "AddToCartView",
    "AddressCreateView",
    "AddressDeleteView",
    "AddressLabelUpdateView",
    "AddressSetDefaultView",
    "AddressUpdateView",
    "ApplyCouponView",
    "AccessLinkEntryView",
    "CartDrawerContentProjView",
    "CartPageContentView",
    "CartSetQtyBySkuView",
    "CartSummaryView",
    "CartView",
    "CepLookupView",
    "CheckoutOrderSummaryView",
    "CheckoutView",
    "CustomerLookupView",
    "DataExportView",
    "DeviceCheckLoginView",
    "DeviceListView",
    "TrustDeviceView",
    "DeviceRevokeAllView",
    "DeviceRevokeView",
    "FoodPreferenceToggleView",
    "HomeView",
    "HowItWorksView",
    "LoginView",
    "MenuView",
    "MockPaymentConfirmView",
    "NotificationPrefsToggleView",
    "OfflineView",
    "OrderCancelView",
    "OrderConfirmationView",
    "OrderHistoryView",
    "OrderStatusPartialView",
    "OrderTrackingView",
    "PaymentStatusView",
    "PaymentView",
    "ProductDetailView",
    "ProfileDisplayView",
    "ProfileEditView",
    "ProfileUpdateView",
    "QuickAddView",
    "RemoveCouponView",
    "ReorderView",
    "RequestCodeView",
    "SimulateIFoodView",
    "SitemapView",
    "SkuStateView",
    "TipsView",
    "VerifyCodeView",
    "WelcomeView",
]
