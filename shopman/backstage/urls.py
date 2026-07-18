"""Backstage URL configuration — operator-facing routes."""

from __future__ import annotations

from django.http import Http404
from django.urls import path
from django_eventstream.views import events as eventstream_view

app_name = "backstage"


def user_events_view(request):
    """Stream pessoal ``user-<id>`` do usuário autenticado.

    O id sai da sessão, nunca da URL: não existe forma de pedir a caixa de
    outra pessoa. Anônimo leva 404 antes de delegar, para o ``EventSource``
    falhar limpo em vez de reconectar para sempre contra um 200 com
    ``stream-error`` in-band (mesmo motivo do stream de acompanhamento).
    """
    user = getattr(request, "user", None)
    if not (user and user.is_authenticated):
        raise Http404
    return eventstream_view(
        request, **{"format-channels": ["user-{user_id}"], "user_id": str(user.pk)}
    )


urlpatterns = [
    # Realtime
    path("gestor/events/me/", user_events_view, name="user_events"),
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
