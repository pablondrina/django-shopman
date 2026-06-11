"""Backstage URL configuration — operator-facing routes."""

from __future__ import annotations

from django.urls import path
from django_eventstream.views import events as eventstream_view

from shopman.backstage import views

app_name = "backstage"

urlpatterns = [
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
    # KDS runtime stations
    path("operacao/kds/", views.kds_station_picker_view, name="kds_station_picker"),
    path("operacao/kds/estacao/<slug:ref>/", views.kds_station_runtime_view, name="kds_station_runtime"),
    path("operacao/kds/estacao/<slug:ref>/cards/", views.kds_station_runtime_cards_view, name="kds_station_runtime_cards"),
    path("operacao/kds/item/<int:pk>/check/", views.kds_station_runtime_check_view, name="kds_station_runtime_check"),
    path("operacao/kds/ticket/<int:pk>/done/", views.kds_station_runtime_done_view, name="kds_station_runtime_done"),
    path("operacao/kds/expedicao/<int:pk>/acao/", views.kds_station_runtime_expedition_view, name="kds_station_runtime_expedition"),
    # Customer pickup board
    path("operacao/kds/cliente/", views.kds_customer_board_view, name="kds_customer_board"),
    path("operacao/kds/cliente/pedidos/", views.kds_customer_board_orders_view, name="kds_customer_board_orders"),
    # POS migrou para Nuxt (surfaces/pos-uithing-nuxt via api/v1/backstage/pos/*);
    # a camada de view POS-HTMX foi removida (SURFACE-CONVERGENCE-PLAN WP1).
    # Production
    path("gestor/producao/kds/", views.production_kds_view, name="production_kds"),
    path("gestor/producao/kds/cards/", views.production_kds_cards_view, name="production_kds_cards"),
    path("gestor/producao/kds/concluir/", views.production_kds_finish_view, name="production_kds_finish"),
    path("gestor/producao/kds/<int:wo_id>/avancar-passo/", views.production_advance_step_view, name="production_advance_step"),
]
