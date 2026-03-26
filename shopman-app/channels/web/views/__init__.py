from .account import (
    AccountView,
    AddressCreateView,
    AddressDeleteView,
    AddressSetDefaultView,
    AddressUpdateView,
)
from .auth import AccessLinkLoginView, CustomerLookupView, DeviceCheckLoginView, RequestCodeView, VerifyCodeView
from .cart import (
    AddToCartView,
    ApplyCouponView,
    CartCheckView,
    CartContentPartialView,
    CartSummaryView,
    CartView,
    FloatingCartBarView,
    RemoveCartItemView,
    RemoveCouponView,
    UpdateCartItemView,
)
from .catalog import MenuSearchView, MenuView, ProductDetailView
from .checkout import CheckoutView, OrderConfirmationView
from .devices import DeviceListView, DeviceRevokeAllView, DeviceRevokeView
from .info import HowItWorksView, OrderHistoryView, SitemapView
from .payment import MockPaymentConfirmView, PaymentStatusView, PaymentView
from .pwa import OfflineView
from .tracking import OrderStatusPartialView, OrderTrackingView

__all__ = [
    "AccountView",
    "AddToCartView",
    "AccessLinkLoginView",
    "ApplyCouponView",
    "AddressCreateView",
    "AddressDeleteView",
    "AddressSetDefaultView",
    "AddressUpdateView",
    "CartCheckView",
    "CartContentPartialView",
    "CartSummaryView",
    "CartView",
    "CheckoutView",
    "CustomerLookupView",
    "DeviceCheckLoginView",
    "DeviceListView",
    "DeviceRevokeAllView",
    "DeviceRevokeView",
    "FloatingCartBarView",
    "HowItWorksView",
    "MenuSearchView",
    "MenuView",
    "MockPaymentConfirmView",
    "OfflineView",
    "OrderConfirmationView",
    "OrderHistoryView",
    "OrderStatusPartialView",
    "OrderTrackingView",
    "PaymentStatusView",
    "PaymentView",
    "ProductDetailView",
    "RemoveCartItemView",
    "RemoveCouponView",
    "RequestCodeView",
    "SitemapView",
    "UpdateCartItemView",
    "VerifyCodeView",
]
