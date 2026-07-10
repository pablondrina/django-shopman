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


def test_no_em_dash_in_copy():
    """Voz da marca: travessão largo (—) proibido na copy user-facing, salvo
    instrução explícita. Ele é marca de texto gerado por IA. Use ponto/vírgula.
    """
    offenders: list[str] = []
    for key, by_moment in OMOTENASHI_DEFAULTS.items():
        for moment, by_audience in by_moment.items():
            for audience, entry in by_audience.items():
                for field in ("title", "message"):
                    value = getattr(entry, field, "") or ""
                    if "—" in value:
                        offenders.append(f"{key}[{moment}][{audience}].{field}: {value!r}")
    assert not offenders, "Travessão largo (—) na copy (use ponto/vírgula):\n" + "\n".join(offenders)


# Prefixos resolvidos por f-string (chave construída em runtime, não literal) — sempre
# alcançáveis: `f"ORDER_STATUS_{}"`, `f"PAYMENT_METHOD_{}"`, `f"AVAILABILITY_{}"`.
_DYNAMIC_PREFIXES = ("ORDER_STATUS_", "PAYMENT_METHOD_", "AVAILABILITY_")
_LITERAL_KEY = re.compile(r"[\"']([A-Z][A-Z0-9_]{3,})[\"']")


def _orphan_keys() -> set[str]:
    """Chaves definidas que NÃO chegam a nenhuma tela: sem literal em produção
    (`shopman/`+`surfaces/`, fora de testes) e sem prefixo dinâmico."""
    defined = set(OMOTENASHI_DEFAULTS.keys())
    repo_root = Path(settings.BASE_DIR)
    defn_file = (_shopman_root() / "shop" / "omotenashi" / "copy.py").as_posix()
    referenced: set[str] = set()
    for base in ("shopman", "surfaces"):
        for path in (repo_root / base).rglob("*"):
            if path.suffix not in (".py", ".ts", ".vue"):
                continue
            ap = path.as_posix()
            if ap == defn_file or "/tests/" in ap or "/test_" in ap:
                continue
            referenced |= {k for k in _LITERAL_KEY.findall(path.read_text("utf-8", errors="ignore")) if k in defined}
    dynamic = {k for k in defined if k.startswith(_DYNAMIC_PREFIXES)}
    return defined - referenced - dynamic


def test_copy_wiring_backlog():
    """Burndown omotenashi: toda copy de cliente deve chegar a uma tela (configurável).
    Chaves ainda não religadas vivem em `docs/plans/copy-wiring-backlog.txt` — que só
    ENCOLHE. Uma órfã NOVA (fora do backlog) falha: ligue via projection, não hardcode.
    Ver COPY-CONSOLIDATION-PLAN (omotenashi-first).
    """
    backlog_file = Path(settings.BASE_DIR) / "docs/plans/copy-wiring-backlog.txt"
    backlog = {
        ln.strip()
        for ln in backlog_file.read_text("utf-8").splitlines()
        if ln.strip() and not ln.startswith("#")
    }
    orphans = _orphan_keys()
    new_drift = sorted(orphans - backlog)
    assert not new_drift, (
        "Copy nova sem tela (ligue via projection ao registro, não hardcode): "
        f"{new_drift}"
    )
