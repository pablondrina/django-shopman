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
    # POS/KDS/Pedidos/alertas migraram para apps Nuxt dedicados (surfaces/*-uithing-nuxt)
    # via api/v1/backstage/*; as camadas de view HTMX foram removidas
    # (SURFACE-CONVERGENCE-PLAN WP1 + OPERATOR-APPS-PLAN Fase 2).
    # Production (HTMX até o app dedicado — Fase 4)
    path("gestor/producao/kds/", views.production_kds_view, name="production_kds"),
    path("gestor/producao/kds/cards/", views.production_kds_cards_view, name="production_kds_cards"),
    path("gestor/producao/kds/concluir/", views.production_kds_finish_view, name="production_kds_finish"),
    path("gestor/producao/kds/<int:wo_id>/avancar-passo/", views.production_advance_step_view, name="production_advance_step"),
]
