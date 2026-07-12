"""Shopman API - REST endpoints (DRF)."""

from __future__ import annotations

import unicodedata
from typing import Any

# Caracteres de formatacao bidirecional / largura-zero. Nao tem uso legitimo em
# texto digitado por cliente e sao vetor classico de spoofing e injecao em log/
# ticket (Trojan Source, override RTL). Removidos de TODO campo: ao contrario de
# bytes de controle crus (\n, \t), nao carregam significado nem em texto livre.
# Listados por code point para manter o fonte 100% ASCII e inequivoco.
_BIDI_FORMAT_CODEPOINTS = (
    0x200B, 0x200C, 0x200D, 0x200E, 0x200F,  # zero-width space/ZWNJ/ZWJ + LRM/RLM
    0x202A, 0x202B, 0x202C, 0x202D, 0x202E,  # embeddings e overrides bidi
    0x2066, 0x2067, 0x2068, 0x2069,          # isolates bidi (LRI/RLI/FSI/PDI)
    0x2060, 0xFEFF,                          # word joiner + BOM/zero-width no-break
)
_BIDI_STRIP = dict.fromkeys(_BIDI_FORMAT_CODEPOINTS)


def clean_text(value: Any) -> str:
    """Coerce a JSON body field to a stripped string, safely.

    A text field arriving as int/list/dict/bool (``{"code": 42}``) must never
    reach ``.strip()`` on a non-string and blow up as a 500 with a leaked
    traceback. Non-strings are treated as absent (empty), so the caller's
    required-field guard turns type-confusion into a clean 400.

    Also strips bidi/zero-width format characters (see ``_BIDI_FORMAT_CODEPOINTS``):
    seguro para campos multi-linha (preserva ``\\n``/``\\t``) e fecha o vetor de
    spoofing antes que o valor chegue a persistencia, KDS ou log.
    """
    if not isinstance(value, str):
        return ""
    return value.translate(_BIDI_STRIP).strip()


def clean_name(value: Any, *, max_length: int = 100) -> str:
    """Sanitize a person-name field before it reaches persistence and the KDS.

    Alem do ``clean_text`` (bidi/zero-width), troca TODO caractere de controle
    Unicode (categoria ``Cc``: inclui ``\\n``/``\\t``, que um nome nunca tem) por
    espaco — preservando o limite de palavra de um "Joao\\nSilva" colado —,
    colapsa espacos repetidos e limita o comprimento a ``max_length``. O nome
    impresso no ticket da cozinha fica curto e sem bytes de controle.
    """
    text = clean_text(value)
    text = "".join(" " if unicodedata.category(char) == "Cc" else char for char in text)
    text = " ".join(text.split())  # colapsa runs de espaco em branco
    return text[:max_length].strip()
