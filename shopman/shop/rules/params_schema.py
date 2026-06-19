"""Esquemas tipados de ``RuleConfig.params`` por regra (dataclass-driven).

Os modifiers de preço (`shop/modifiers.py`) JÁ leem os params via
``get_channel_rule_params``; aqui apenas descrevemos o *shape* de cada regra
conhecida para que o Admin edite campos tipados em vez de JSON cru (omotenashi
para o operador). Regras sem schema (validators, etc.) continuam no JSONField.
"""

from __future__ import annotations

from dataclasses import dataclass

PERCENT = "percent"
TIME = "time"


@dataclass(frozen=True)
class RuleParam:
    """Um parâmetro de regra: chave no JSON + tipo + rótulo/ajuda pt-BR."""

    name: str  # chave em RuleConfig.params
    kind: str  # PERCENT | TIME
    label: str
    help_text: str = ""


@dataclass(frozen=True)
class RuleParamSchema:
    code: str
    title: str
    params: tuple[RuleParam, ...]


# Chave = RuleConfig.code (sem prefixo — é o que get_channel_rule_params matcheia).
RULE_PARAM_SCHEMAS: dict[str, RuleParamSchema] = {
    "happy_hour": RuleParamSchema(
        code="happy_hour",
        title="Happy hour — janela de desconto",
        params=(
            RuleParam("discount_percent", PERCENT, "Desconto (%)",
                      "Percentual aplicado a cada item dentro da janela."),
            RuleParam("start", TIME, "Início",
                      "Hora em que a janela começa (HH:MM)."),
            RuleParam("end", TIME, "Fim",
                      "Hora em que a janela termina — exclusiva (HH:MM)."),
        ),
    ),
    "d1_discount": RuleParamSchema(
        code="d1_discount",
        title="Desconto D-1 — produto da véspera",
        params=(
            RuleParam("discount_percent", PERCENT, "Desconto (%)",
                      "Percentual sobre itens marcados como D-1 (do dia anterior)."),
        ),
    ),
    "employee_discount": RuleParamSchema(
        code="employee_discount",
        title="Desconto funcionário",
        params=(
            RuleParam("discount_percent", PERCENT, "Desconto (%)",
                      "Percentual para clientes do grupo “staff”."),
        ),
    ),
}


def schema_for(code: str | None) -> RuleParamSchema | None:
    return RULE_PARAM_SCHEMAS.get(code or "")
