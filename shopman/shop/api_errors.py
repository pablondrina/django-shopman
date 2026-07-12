"""Dialeto canônico de erro HTTP das superfícies headless.

Toda resposta de erro JSON das APIs (storefront e backstage) fala o mesmo
dialeto, que os fronts leem via ``httpError.ts``:

    {
        "detail": "<mensagem humana principal>",          # SEMPRE presente
        "field": "<campo que causou o erro>",             # só em erro de campo
        "errors": {"<campo>": ["<mensagem>", ...], ...},  # mapa campo → mensagens
    }

- ``detail`` é o que as superfícies exibem (``errorDetail``/``httpErrorMessage``
  leem ``data.detail``); sem ele o cliente vê só o fallback genérico.
- ``field`` roteia o erro para o passo/campo certo (ex.: ``finalizar.vue``
  reabre o passo do checkout dono do campo). Campos aninhados usam caminho
  pontuado (``delivery_address_structured.cep``, ``items.0.sku``).
- ``errors`` preserva todas as mensagens por campo para render inline.

Erros de negócio construídos manualmente nas views já seguem esse shape.
O PDV fala um SUPERSET deliberado: ``{"detail": ..., "error": {code, message,
field, focus, recovery}}`` (ver ``shopman/shop/services/pos_intent.py``) —
``detail`` continua obrigatório lá também; este handler não o achata.

Este handler existe porque o ``ValidationError`` de serializer DRF cru devolvia
``{"phone": ["Ensure this field..."]}`` sem ``detail`` — invisível para os
fronts. As mensagens dos validators chegam em pt-br via i18n do Django
(``LANGUAGE_CODE = "pt-br"`` + locale ``pt_BR`` do DRF).

Referência completa do dialeto: ``docs/reference/errors.md``.
"""

from __future__ import annotations

from rest_framework import exceptions
from rest_framework.settings import api_settings
from rest_framework.views import exception_handler as drf_exception_handler

FALLBACK_DETAIL = "Não conseguimos processar os dados enviados. Confira e tente novamente."


def exception_handler(exc, context):
    """DRF ``EXCEPTION_HANDLER``: converte ValidationError para o dialeto da casa.

    Demais exceções DRF (``NotAuthenticated``, ``Throttled``, ``NotFound``…) já
    saem do handler default como ``{"detail": ...}`` e passam intactas. O status
    HTTP nunca muda aqui.
    """
    response = drf_exception_handler(exc, context)
    if response is None:
        return None
    if isinstance(exc, exceptions.ValidationError):
        response.data = validation_error_payload(exc.detail)
    return response


def validation_error_payload(detail) -> dict:
    """Normaliza o ``detail`` de um ValidationError DRF para o dialeto canônico."""
    errors = _flatten_errors(detail)
    payload_detail = FALLBACK_DETAIL
    payload: dict = {"detail": payload_detail, "errors": errors}

    for field, messages in errors.items():
        if not messages:
            continue
        payload["detail"] = messages[0]
        if field != api_settings.NON_FIELD_ERRORS_KEY:
            payload["field"] = field
        break
    return payload


def _flatten_errors(detail, prefix: str = "") -> dict[str, list[str]]:
    """Achata o detail (dict/list/str aninhados) em ``{caminho: [mensagens]}``.

    Caminhos aninhados viram pontuados (``endereco.cep``, ``items.0.sku``) — o
    mesmo formato de ``field`` que o dialeto rico do PDV já usa. Mensagens
    soltas na raiz entram como ``non_field_errors``.
    """
    flat: dict[str, list[str]] = {}

    if isinstance(detail, dict):
        for key, value in detail.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            for inner_key, messages in _flatten_errors(value, path).items():
                flat.setdefault(inner_key, []).extend(messages)
        return flat

    if isinstance(detail, list):
        for index, item in enumerate(detail):
            if isinstance(item, (dict, list)):
                path = f"{prefix}.{index}" if prefix else str(index)
                for inner_key, messages in _flatten_errors(item, path).items():
                    flat.setdefault(inner_key, []).extend(messages)
            else:
                key = prefix or api_settings.NON_FIELD_ERRORS_KEY
                flat.setdefault(key, []).append(str(item))
        return flat

    key = prefix or api_settings.NON_FIELD_ERRORS_KEY
    flat.setdefault(key, []).append(str(detail))
    return flat
