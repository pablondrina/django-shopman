"""
Context processors para o Admin do Ordering.
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

    from shopman.omniman.models import Directive

    pending_count = Directive.objects.filter(status="queued").count()

    return {
        "ordering_pending_directives_count": pending_count,
        "ordering_has_pending_directives": pending_count > 0,
    }
