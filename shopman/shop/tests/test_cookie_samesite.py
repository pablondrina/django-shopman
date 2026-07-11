"""SameSite explícito nos cookies de sessão/CSRF.

Os BFFs Nuxt auto-preenchem o token CSRF a partir do cookie
(surfaces/*/server/utils/djangoProxy.ts), então a defesa CSRF real contra
requests cross-site é o SameSite=Lax destes cookies. Este teste trava a
configuração: mudar para "None" exige revisar essa cadeia inteira.
"""

from __future__ import annotations

from django.conf import settings


def test_session_cookie_samesite_is_lax():
    assert settings.SESSION_COOKIE_SAMESITE == "Lax"


def test_csrf_cookie_samesite_is_lax():
    assert settings.CSRF_COOKIE_SAMESITE == "Lax"
