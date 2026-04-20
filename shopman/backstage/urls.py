"""Backstage URL configuration — operator-facing routes."""

from __future__ import annotations

from django.urls import path

from shopman.backstage import views

app_name = "backstage"

urlpatterns = [
    # Gestor de Pedidos
    path("pedidos/", views.OperatorOrdersView.as_view(), name="gestor_pedidos"),
    path("pedidos/list/", views.OrderListPartialView.as_view(), name="gestor_list_partial"),
    path("pedidos/<str:ref>/detail/", views.OrderDetailPartialView.as_view(), name="gestor_detail"),
    path("pedidos/<str:ref>/confirm/", views.OrderConfirmView.as_view(), name="gestor_confirm"),
    path("pedidos/<str:ref>/reject/", views.OrderRejectView.as_view(), name="gestor_reject"),
    path("pedidos/<str:ref>/advance/", views.OrderAdvanceView.as_view(), name="gestor_advance"),
    path("pedidos/<str:ref>/notes/", views.OrderNotesView.as_view(), name="gestor_notes"),
    path("pedidos/<str:ref>/mark-paid/", views.OrderMarkPaidView.as_view(), name="gestor_mark_paid"),
    # POS (Balcão)
    path("gestao/pos/", views.pos_view, name="pos"),
    path("gestao/pos/customer-lookup/", views.pos_customer_lookup, name="pos_customer_lookup"),
    path("gestao/pos/close/", views.pos_close, name="pos_close"),
    path("gestao/pos/cancel-last/", views.pos_cancel_last, name="pos_cancel_last"),
    path("gestao/pos/shift-summary/", views.pos_shift_summary, name="pos_shift_summary"),
    path("gestao/pos/caixa/abrir/", views.pos_cash_open, name="pos_cash_open"),
    path("gestao/pos/caixa/sangria/", views.pos_cash_sangria, name="pos_cash_sangria"),
    path("gestao/pos/caixa/fechar/", views.pos_cash_close, name="pos_cash_close"),
    # Production
    path("gestao/producao/criar/", views.bulk_create_work_orders, name="bulk_create_work_orders"),
    # KDS (Kitchen Display System)
    path("kds/", views.KDSIndexView.as_view(), name="kds_index"),
    path("kds/<slug:ref>/", views.KDSDisplayView.as_view(), name="kds_display"),
    path("kds/<slug:ref>/tickets/", views.KDSTicketListPartialView.as_view(), name="kds_ticket_list"),
    path("kds/ticket/<int:pk>/check/", views.KDSTicketCheckItemView.as_view(), name="kds_ticket_check"),
    path("kds/ticket/<int:pk>/done/", views.KDSTicketDoneView.as_view(), name="kds_ticket_done"),
    path("kds/expedition/<int:pk>/action/", views.KDSExpeditionActionView.as_view(), name="kds_expedition_action"),
    # Closing
    path("gestao/fechamento/", views.DayClosingView.as_view(), name="day_closing"),
]
