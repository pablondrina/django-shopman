"""Backstage URL configuration — operator-facing routes."""

from __future__ import annotations

from django.urls import path

from shopman.backstage import views

app_name = "backstage"

urlpatterns = [
    # Gestor de Pedidos
    path("gestor/pedidos/", views.OperatorOrdersView.as_view(), name="gestor_pedidos"),
    path("gestor/pedidos/list/", views.OrderListPartialView.as_view(), name="gestor_list_partial"),
    path("gestor/pedidos/<str:ref>/detail/", views.OrderDetailPartialView.as_view(), name="gestor_detail"),
    path("gestor/pedidos/<str:ref>/confirm/", views.OrderConfirmView.as_view(), name="gestor_confirm"),
    path("gestor/pedidos/<str:ref>/reject/", views.OrderRejectView.as_view(), name="gestor_reject"),
    path("gestor/pedidos/<str:ref>/advance/", views.OrderAdvanceView.as_view(), name="gestor_advance"),
    path("gestor/pedidos/<str:ref>/notes/", views.OrderNotesView.as_view(), name="gestor_notes"),
    path("gestor/pedidos/<str:ref>/mark-paid/", views.OrderMarkPaidView.as_view(), name="gestor_mark_paid"),
    path("gestor/pedidos/alerts/<int:pk>/ack/", views.AlertAcknowledgeView.as_view(), name="gestor_alert_ack"),
    # POS (Balcão)
    path("gestor/pos/", views.pos_view, name="pos"),
    path("gestor/pos/customer-lookup/", views.pos_customer_lookup, name="pos_customer_lookup"),
    path("gestor/pos/close/", views.pos_close, name="pos_close"),
    path("gestor/pos/cancel-last/", views.pos_cancel_last, name="pos_cancel_last"),
    path("gestor/pos/shift-summary/", views.pos_shift_summary, name="pos_shift_summary"),
    path("gestor/pos/park/", views.pos_park, name="pos_park"),
    path("gestor/pos/sessions/", views.pos_sessions, name="pos_sessions"),
    path("gestor/pos/session/<str:session_key>/load/", views.pos_load_session, name="pos_load_session"),
    path("gestor/pos/caixa/abrir/", views.pos_cash_open, name="pos_cash_open"),
    path("gestor/pos/caixa/sangria/", views.pos_cash_sangria, name="pos_cash_sangria"),
    path("gestor/pos/caixa/fechar/", views.pos_cash_close, name="pos_cash_close"),
    # Production
    path("gestor/producao/criar/", views.bulk_create_work_orders, name="bulk_create_work_orders"),
    # KDS (Kitchen Display System)
    path("gestor/kds/", views.KDSIndexView.as_view(), name="kds_index"),
    path("gestor/kds/<slug:ref>/", views.KDSDisplayView.as_view(), name="kds_display"),
    path("gestor/kds/<slug:ref>/tickets/", views.KDSTicketListPartialView.as_view(), name="kds_ticket_list"),
    path("gestor/kds/ticket/<int:pk>/check/", views.KDSTicketCheckItemView.as_view(), name="kds_ticket_check"),
    path("gestor/kds/ticket/<int:pk>/done/", views.KDSTicketDoneView.as_view(), name="kds_ticket_done"),
    path("gestor/kds/expedition/<int:pk>/action/", views.KDSExpeditionActionView.as_view(), name="kds_expedition_action"),
    # Closing
    path("gestor/fechamento/", views.closing_view, name="day_closing"),
]
