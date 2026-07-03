"""Trava de segurança para adapters que fazem chamadas externas reais.

Qualquer adapter que dispara uma chamada de rede real para um provedor externo
(SMS via Comtele, WhatsApp via ManyChat/Meta, etc.) fica **inerte** em duas
situações:

1. **Processo suprimido** (``suppress()``): o ``seed`` ativa isto no início —
   dados sintéticos nunca notificam telefones de verdade, em NENHUM ambiente
   (o staging roda ``DEBUG=False`` com credenciais reais; sem isto, um reseed
   dispararia SMS para os números fictícios do seed). Sem opt-out.

2. **DEBUG sem opt-in**: em dev as credenciais reais ficam no ``.env``, então
   um shell ou o dev server disparariam mensagens de verdade. Opt-in explícito
   quando o dev realmente quer testar o envio real localmente:
   - por adapter, ex. ``SHOPMAN_SMS_ALLOW_IN_DEBUG=true``;
   - ou globalmente, ``SHOPMAN_ALLOW_EXTERNAL_IN_DEBUG=true``.

Fora dessas situações (staging/produção em operação normal) a trava nunca
ativa — o comportamento real é sempre o de produção.
"""

from __future__ import annotations

from django.conf import settings

_suppressed_reason: str | None = None


def suppress(reason: str) -> None:
    """Suprime chamadas externas neste processo, sem opt-out (usado pelo seed)."""
    global _suppressed_reason
    _suppressed_reason = reason


def inert(opt_in_setting: str | None = None) -> bool:
    """Retorna True quando o adapter deve pular a chamada externa.

    O adapter então loga o que teria enviado e devolve seu resultado "neutro"
    (sucesso para notificações, falha para OTP, de modo que a cadeia caia no
    console).
    """
    if _suppressed_reason is not None:
        return True
    if not getattr(settings, "DEBUG", False):
        return False
    if getattr(settings, "SHOPMAN_ALLOW_EXTERNAL_IN_DEBUG", False):
        return False
    if opt_in_setting and getattr(settings, opt_in_setting, False):
        return False
    return True
