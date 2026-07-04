"""Backstage URL configuration — operator-facing routes."""

from __future__ import annotations

from django.urls import path
from django_eventstream.views import events as eventstream_view

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
    # POS/KDS/Pedidos/alertas/Produção migraram para apps Nuxt dedicados
    # (surfaces/*-nuxt) via api/v1/backstage/*; as camadas de view HTMX
    # foram removidas (SURFACE-CONVERGENCE-PLAN WP1 + OPERATOR-APPS-PLAN Fases 2 e 4).
    # O console Admin/Unfold de produção (admin_console/production.py) segue —
    # consome os helpers compartilhados de views/production.py.
]
