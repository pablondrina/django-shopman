"""
Context processors para o Admin do Omniman.
"""

from __future__ import annotations

from django.http import HttpRequest


def pending_directives(request: HttpRequest) -> dict:
    """
    Adiciona contagem de diretivas pendentes ao contexto do Admin.

    Usado para exibir banner de alerta quando há diretivas aguardando execução.
    """
    # Só executa no Admin
    if not request.path.startswith("/admin/"):
        return {}

    from shopman.ordering.models import Directive

    pending_count = Directive.objects.filter(status="queued").count()

    return {
        "omniman_pending_directives_count": pending_count,
        "omniman_has_pending_directives": pending_count > 0,
    }
