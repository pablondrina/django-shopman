"""Heartbeat de workers — timestamp do último ciclo, via cache do Django.

Observabilidade mínima da ADR-003: cada worker grava o timestamp do seu ciclo
e quem monitora lê a idade do último batimento. O cache é o lugar mais simples
e robusto que a casa já tem para isso: em staging/produção é Redis
compartilhado (obrigatório no runtime, visível entre processos), sem migração
e sem modelo novo só para um par chave→timestamp.

Limite consciente: em dev/CI o cache é locmem (por processo) — o batimento de
outro processo é invisível. Por isso o leitor trata ausência de chave como
"desconhecido" (nunca alerta), e só alerta quando um batimento CONHECIDO
envelhece além do limiar.
"""

from __future__ import annotations

from datetime import datetime

from django.core.cache import cache
from django.utils import timezone

# Worker de directives do Core (process_directives --watch).
PROCESS_DIRECTIVES_WORKER = "process_directives"

_KEY_TEMPLATE = "shopman:worker_heartbeat:{name}"


def beat(name: str) -> None:
    """Grava o timestamp de ciclo do worker ``name`` (sem expiração)."""
    cache.set(_KEY_TEMPLATE.format(name=name), timezone.now(), None)


def last_beat(name: str) -> datetime | None:
    """Timestamp do último ciclo do worker ``name``; None = desconhecido."""
    return cache.get(_KEY_TEMPLATE.format(name=name))


__all__ = ["PROCESS_DIRECTIVES_WORKER", "beat", "last_beat"]
