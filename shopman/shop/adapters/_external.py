"""Trava de segurança para adapters que fazem chamadas externas reais.

Qualquer adapter que dispara uma chamada de rede real para um provedor externo
(SMS via Comtele, WhatsApp via ManyChat/Meta, etc.) deve ficar **inerte** em
ambiente de desenvolvimento (``settings.DEBUG``) — senão um ``seed``, uma sessão
de shell ou o dev server disparam mensagens de verdade para telefones reais,
usando as credenciais reais que ficam no ``.env`` de dev.

Opt-in explícito quando o dev realmente quer testar o envio real localmente:
- por adapter, ex. ``SHOPMAN_SMS_ALLOW_IN_DEBUG=true``;
- ou globalmente, ``SHOPMAN_ALLOW_EXTERNAL_IN_DEBUG=true``.

Fora de DEBUG (staging/produção) a trava nunca ativa — o comportamento real é
sempre o de produção.
"""

from __future__ import annotations

from django.conf import settings


def inert_in_debug(opt_in_setting: str | None = None) -> bool:
    """Retorna True quando o adapter deve pular a chamada externa (dev-safety).

    True somente em ``DEBUG`` e sem opt-in — o adapter então loga o que teria
    enviado e devolve seu resultado "neutro" (sucesso para notificações, falha
    para OTP, de modo que a cadeia caia no console).
    """
    if not getattr(settings, "DEBUG", False):
        return False
    if getattr(settings, "SHOPMAN_ALLOW_EXTERNAL_IN_DEBUG", False):
        return False
    if opt_in_setting and getattr(settings, opt_in_setting, False):
        return False
    return True
