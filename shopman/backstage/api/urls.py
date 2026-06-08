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
    POSCancelRecentSaleView,
    POSCashCloseView,
    POSCashMovementView,
    POSCashOpenView,
    POSCloseSaleView,
    POSCustomerLookupView,
    POSCustomerSearchView,
    POSOperatorLockView,
    POSOperatorUnlockView,
    POSReviewSaleView,
    POSTabClearView,
    POSTabCreateView,
    POSTabFireView,
    POSTabMoveLinesView,
    POSTabOpenView,
    POSTabRenameView,
    POSTabSaveView,
    POSTabUnfireView,
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
    path("pos/operator/unlock/", POSOperatorUnlockView.as_view(), name="api-backstage-pos-operator-unlock"),
    path("pos/operator/lock/", POSOperatorLockView.as_view(), name="api-backstage-pos-operator-lock"),
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
    path("pos/tabs/<str:tab_ref>/open/", POSTabOpenView.as_view(), name="api-backstage-pos-tab-open"),
    path("pos/tabs/save/", POSTabSaveView.as_view(), name="api-backstage-pos-tab-save"),
    path("pos/tabs/rename/", POSTabRenameView.as_view(), name="api-backstage-pos-tab-rename"),
    path("pos/tabs/move-lines/", POSTabMoveLinesView.as_view(), name="api-backstage-pos-tab-move-lines"),
    path("pos/tabs/fire/", POSTabFireView.as_view(), name="api-backstage-pos-tab-fire"),
    path("pos/tabs/unfire/", POSTabUnfireView.as_view(), name="api-backstage-pos-tab-unfire"),
    path("pos/tabs/<str:session_key>/clear/", POSTabClearView.as_view(), name="api-backstage-pos-tab-clear"),
    path("pos/sale/review/", POSReviewSaleView.as_view(), name="api-backstage-pos-review-sale"),
    path("pos/sale/close/", POSCloseSaleView.as_view(), name="api-backstage-pos-close-sale"),
    path("pos/sale/recent/cancel/", POSCancelRecentSaleView.as_view(), name="api-backstage-pos-cancel-recent-sale"),
    path("pos/customer/lookup/", POSCustomerLookupView.as_view(), name="api-backstage-pos-customer-lookup"),
    path("pos/customer/search/", POSCustomerSearchView.as_view(), name="api-backstage-pos-customer-search"),
]
