"""Backstage API URL configuration."""

from __future__ import annotations

from django.urls import path

from .kds import (
    KDSBoardView,
    KDSCustomerStatusView,
    KDSExpeditionActionView,
    KDSIndexView,
    KDSTicketDoneView,
    KDSTicketItemView,
)
from .operations import (
    DayClosingView,
    OrderAdvanceView,
    OrderCancelView,
    OrderConfirmView,
    OrderDetailView,
    OrderQueueView,
    OrderRejectView,
    POSCashCloseView,
    POSCashMovementView,
    POSCashOpenView,
    POSCloseSaleView,
    POSCustomerLookupView,
    POSTabClearView,
    POSTabCreateView,
    POSTabOpenView,
    POSTabSaveView,
    POSView,
    ProductionBoardView,
    ProductionKDSView,
    WorkOrderAdvanceStepView,
    WorkOrderQuickFinishView,
    WorkOrderVoidView,
)

urlpatterns = [
    # KDS
    path("kds/", KDSIndexView.as_view(), name="api-backstage-kds-index"),
    path("kds/cliente/", KDSCustomerStatusView.as_view(), name="api-backstage-kds-customer"),
    path("kds/<slug:ref>/", KDSBoardView.as_view(), name="api-backstage-kds-board"),
    path("kds/tickets/<int:ticket_pk>/items/", KDSTicketItemView.as_view(), name="api-backstage-kds-ticket-item"),
    path("kds/tickets/<int:ticket_pk>/done/", KDSTicketDoneView.as_view(), name="api-backstage-kds-ticket-done"),
    path("kds/expedition/<int:order_pk>/action/", KDSExpeditionActionView.as_view(), name="api-backstage-kds-expedition"),
    # Operations — read views
    path("pos/", POSView.as_view(), name="api-backstage-pos"),
    path("production/", ProductionBoardView.as_view(), name="api-backstage-production"),
    path("production/kds/", ProductionKDSView.as_view(), name="api-backstage-production-kds"),
    path("closing/", DayClosingView.as_view(), name="api-backstage-closing"),
    path("orders/", OrderQueueView.as_view(), name="api-backstage-orders"),
    # Orders — operator actions
    path("orders/<str:ref>/", OrderDetailView.as_view(), name="api-backstage-order-detail"),
    path("orders/<str:ref>/advance/", OrderAdvanceView.as_view(), name="api-backstage-order-advance"),
    path("orders/<str:ref>/confirm/", OrderConfirmView.as_view(), name="api-backstage-order-confirm"),
    path("orders/<str:ref>/reject/", OrderRejectView.as_view(), name="api-backstage-order-reject"),
    path("orders/<str:ref>/cancel/", OrderCancelView.as_view(), name="api-backstage-order-cancel"),
    # Production — work order actions
    path("production/<int:wo_id>/advance-step/", WorkOrderAdvanceStepView.as_view(), name="api-backstage-wo-advance"),
    path("production/quick-finish/", WorkOrderQuickFinishView.as_view(), name="api-backstage-wo-quick-finish"),
    path("production/<int:wo_id>/void/", WorkOrderVoidView.as_view(), name="api-backstage-wo-void"),
    # POS — cash session actions
    path("pos/cash/open/", POSCashOpenView.as_view(), name="api-backstage-pos-cash-open"),
    path("pos/cash/close/", POSCashCloseView.as_view(), name="api-backstage-pos-cash-close"),
    path("pos/cash/movement/", POSCashMovementView.as_view(), name="api-backstage-pos-cash-movement"),
    # POS — tab (comanda) lifecycle
    path("pos/tabs/", POSTabCreateView.as_view(), name="api-backstage-pos-tab-create"),
    path("pos/tabs/<str:tab_code>/open/", POSTabOpenView.as_view(), name="api-backstage-pos-tab-open"),
    path("pos/tabs/save/", POSTabSaveView.as_view(), name="api-backstage-pos-tab-save"),
    path("pos/tabs/<str:session_key>/clear/", POSTabClearView.as_view(), name="api-backstage-pos-tab-clear"),
    path("pos/sale/close/", POSCloseSaleView.as_view(), name="api-backstage-pos-close-sale"),
    path("pos/customer/lookup/", POSCustomerLookupView.as_view(), name="api-backstage-pos-customer-lookup"),
]
