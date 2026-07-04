"""Criação de evento com `seq` sequencial resiliente a corrida.

`seq` é MAX(seq)+1 no escopo (order / session_key). O `select_for_update()` sobre um
`aggregate()` NÃO trava nada — o Django remove o FOR UPDATE de queries de agregação —,
então duas emissões concorrentes (ex.: webhook de pagamento × ação de operador) leem o
mesmo MAX e colidem no unique `(order, seq)` / `(session_key, seq)`, estourando 500.

A correção real é otimista: tenta criar e, se colidir, recalcula o MAX e tenta de novo.
Cada tentativa roda num savepoint próprio (`transaction.atomic`) para que o
IntegrityError do Postgres não aborte a transação externa.
"""

from __future__ import annotations

_MAX_ATTEMPTS = 6


def create_sequenced_event(*, model, scope: dict, **fields):
    """Cria um evento de ``model`` com ``seq = MAX(seq)+1`` no ``scope``, com retry.

    ``scope`` é o filtro que define a sequência (ex.: ``{"order": order}``); ``fields``
    são os demais campos do evento (que já devem incluir as chaves de ``scope``).
    """
    from django.db import IntegrityError, transaction
    from django.db.models import Max, Value
    from django.db.models.functions import Coalesce

    for attempt in range(_MAX_ATTEMPTS):
        seq = None
        try:
            with transaction.atomic():
                last_seq = model.objects.filter(**scope).aggregate(
                    m=Coalesce(Max("seq"), Value(-1))
                )["m"]
                seq = last_seq + 1
                return model.objects.create(seq=seq, **fields)
        except IntegrityError:
            # Só retenta se a violação foi MESMO a colisão de (scope, seq). Outra
            # constraint (FK, NOT NULL, check) não é corrida de seq e não pode ser
            # mascarada por 6 tentativas — re-levanta na hora. O savepoint do
            # `with` já reverteu, então a consulta abaixo é segura.
            if seq is None or not model.objects.filter(seq=seq, **scope).exists():
                raise
            if attempt == _MAX_ATTEMPTS - 1:
                raise
            # colisão de seq com emissão concorrente — recalcula e tenta de novo.
    # Inalcançável: o último attempt ou retorna ou re-levanta.
    raise RuntimeError("create_sequenced_event: laço de retry terminou sem resultado")
