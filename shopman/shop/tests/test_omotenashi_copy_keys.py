"""Guard de drift do sistema de copy Omotenashi (headless).

A copy de cliente vive em chaves server-side: `OMOTENASHI_DEFAULTS[key][moment][audience]`
(orquestrador) resolvidas via `Copy.title/.text(key, fallback)` na camada de
presentation. Uma chave usada no código mas AUSENTE dos defaults nunca é
admin-configurável (só existe o fallback hardcoded) e, sem fallback, degradaria
para string vazia.

Este teste cruza as chaves literais usadas em `shopman/` contra `OMOTENASHI_DEFAULTS`
e falha se alguma usada não estiver definida — travando a invariante saudável atual
(0 órfãs). Substitui o antigo `lint_omotenashi_copy.py`, que varria os templates
Django de cliente (removidos no cutover headless).
"""

from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings

from shopman.shop.omotenashi.copy import OMOTENASHI_DEFAULTS

# `copy.title("KEY", ...)` / `copy.text("KEY", ...)` com chave literal MAIÚSCULA.
_KEY_CALL = re.compile(r"\.(?:title|text)\(\s*[\"']([A-Z0-9_]+)[\"']")


def _shopman_root() -> Path:
    return Path(settings.BASE_DIR) / "shopman"


def _used_copy_keys() -> set[str]:
    used: set[str] = set()
    for path in _shopman_root().rglob("*.py"):
        if "/tests/" in path.as_posix():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        used.update(_KEY_CALL.findall(text))
    return used


def test_used_copy_keys_are_defined():
    """Toda chave literal usada via .title/.text deve existir em OMOTENASHI_DEFAULTS."""
    defined = set(OMOTENASHI_DEFAULTS.keys())
    used = _used_copy_keys()
    missing = sorted(used - defined)
    assert not missing, (
        "Chaves de copy usadas mas não definidas em OMOTENASHI_DEFAULTS "
        f"(não admin-configuráveis / risco de string vazia): {missing}"
    )


def test_copy_keys_were_collected():
    """Sanidade: o scanner encontra as chaves (não silenciar por regex quebrada)."""
    assert len(_used_copy_keys()) > 10
