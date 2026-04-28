"""Backstage URL configuration — operator-facing routes."""

from __future__ import annotations

from django.urls import path
from django_eventstream.views import events as eventstream_view

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
    path("gestor/pedidos/historico/", views.OrderHistoricoView.as_view(), name="gestor_historico"),
    path("gestor/pedidos/alerts/<int:pk>/ack/", views.AlertAcknowledgeView.as_view(), name="gestor_alert_ack"),
    # Realtime
    path(
        "gestor/events/<slug:kind>/",
        eventstream_view,
        {"format-channels": ["backstage-{kind}-main"]},
        name="events",
    ),
    path(
        "gestor/events/<slug:kind>/<slug:scope>/",
        eventstream_view,
        {"format-channels": ["backstage-{kind}-{scope}"]},
        name="events_scoped",
    ),
    path("gestor/alertas/badge/", views.alerts_badge, name="alerts_badge"),
    path("gestor/alertas/painel/", views.alerts_panel, name="alerts_panel"),
    path("gestor/alertas/<int:pk>/ack/", views.alert_ack, name="alert_ack"),
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
    path("gestor/producao/", views.production_view, name="production"),
    path("gestor/producao/dashboard/", views.production_dashboard_view, name="production_dashboard"),
    path("gestor/producao/kds/", views.production_kds_view, name="production_kds"),
    path("gestor/producao/kds/cards/", views.production_kds_cards_view, name="production_kds_cards"),
    path("gestor/producao/relatorios/", views.production_reports_view, name="production_reports"),
    path("gestor/producao/<slug:wo_ref>/pedidos/", views.production_work_order_orders_view, name="production_work_order_orders"),
    path("gestor/producao/void/", views.production_void_view, name="production_void"),
    path("gestor/producao/criar/", views.bulk_create_work_orders, name="bulk_create_work_orders"),
    path("gestor/producao/<int:wo_id>/avancar-passo/", views.production_advance_step_view, name="production_advance_step"),
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
