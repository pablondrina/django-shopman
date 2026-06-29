"""Fiscal classification for sellable products — Brazilian NFC-e / NF-e.

Single source of truth for the schema of ``Product.metadata["fiscal"]`` and the
suite's named fiscal profiles. Dataclass-driven: the dataclasses below give
Python typing, drive the admin form (one field per concept, no raw JSON), and
validate fiscal invariants. **No new Core columns** — fiscal data lives in the
product's JSONField; Offerman stores the blob, Fiscalman owns the schema.

Design (decisions locked with the owner, 2026-06-28):

- Regime: **Simples Nacional**. Document: **NFC-e (model 65)** intrastate; NF-e
  (model 55) interstate is future scope.
- Two named profiles instead of copying CFOP/CSOSN into every product. The real
  fiscal axis (per the accountant's parametrization, SEFA-PR) is **ST vs não-ST**:
    * ``own_production`` — não sujeito a ST: fabricação própria + revenda comum
      (pães, salgados, doces, bebidas preparadas). CSOSN 102, **CFOP 5102/6102**,
      no CEST.
    * ``resale`` — sujeito a ST (refrigerantes, água, industrializados).
      CSOSN 500, CFOP 5405/6405, **CEST required** per product.
- A product carries only what *varies per product*: ``profile`` + ``ncm`` +
  ``cest`` (resale only) + ``unit``. The profile supplies CFOP/CSOSN/origem and
  PIS/COFINS CST. ``resolve_fiscal_item`` merges both into the flat dict the
  fiscal adapter consumes.

PIS/COFINS CST = ``99`` (outras operações) — conforme a parametrização do contador
(doc "PROCEDIMENTO E PARAMETRIZAÇÃO", SEFA-PR, Simples Nacional CRT-01).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Fiscal codes are textual (leading zeros are significant) — never ints.
NCM_RE = re.compile(r"^\d{8}$")   # NCM: 8 digits.
CEST_RE = re.compile(r"^\d{7}$")  # CEST: 7 digits (format SS.III.DD).


@dataclass(frozen=True)
class FiscalProfile:
    """A reusable, named fiscal preset shared by many products.

    Holds the fields that depend on the *operation* (not the individual
    product): CFOP, CSOSN, origem, PIS/COFINS CST. CFOP comes in two flavours —
    intrastate and interstate — and the emission layer picks one by the buyer's
    UF (see ``resolve_fiscal_item``).
    """

    key: str
    name: str
    csosn: str             # ICMS situação tributária no Simples (e.g. "102", "500").
    cfop_internal: str     # Operação interna (mesmo estado), e.g. "5101".
    cfop_interstate: str   # Operação interestadual, e.g. "6101".
    icms_origem: str = "0"     # 0 = Nacional.
    pis_cst: str = "99"        # Simples (CRT-01): 99 = outras operações (parametrização do contador).
    cofins_cst: str = "99"
    requires_cest: bool = False


OWN_PRODUCTION = FiscalProfile(
    key="own_production",
    name="Fabricação própria",
    csosn="102",
    cfop_internal="5102",
    cfop_interstate="6102",
    requires_cest=False,
)

RESALE = FiscalProfile(
    key="resale",
    name="Revenda (com ST)",
    csosn="500",
    cfop_internal="5405",
    cfop_interstate="6405",
    requires_cest=True,
)

FISCAL_PROFILES: dict[str, FiscalProfile] = {p.key: p for p in (OWN_PRODUCTION, RESALE)}
DEFAULT_PROFILE_KEY = OWN_PRODUCTION.key


@dataclass(frozen=True)
class ProductFiscalClassification:
    """Typed view of ``Product.metadata['fiscal']`` — per-product fiscal data.

    Only the per-product variable bits live here; the rest is resolved from the
    named :class:`FiscalProfile`.
    """

    profile: str = DEFAULT_PROFILE_KEY
    ncm: str = ""
    cest: str = ""
    unit: str = "UN"

    @property
    def fiscal_profile(self) -> FiscalProfile | None:
        return FISCAL_PROFILES.get(self.profile)

    def errors(self) -> list[str]:
        """Validation messages (empty == valid). Drives ``Product.clean()``."""
        profile = self.fiscal_profile
        if profile is None:
            return [f"Perfil fiscal desconhecido: {self.profile!r}."]

        problems: list[str] = []
        if not NCM_RE.match(self.ncm or ""):
            problems.append("NCM deve ter 8 dígitos.")
        if profile.requires_cest:
            if not CEST_RE.match(self.cest or ""):
                problems.append("CEST (7 dígitos) é obrigatório para itens de revenda/ST.")
        elif self.cest:
            problems.append("CEST não se aplica a fabricação própria — deixe vazio.")
        return problems

    @property
    def is_valid(self) -> bool:
        return not self.errors()


def from_metadata(metadata: dict | None) -> ProductFiscalClassification:
    """Read a classification from ``Product.metadata`` (tolerant of legacy keys)."""
    raw = (metadata or {}).get("fiscal") or {}
    return ProductFiscalClassification(
        profile=str(raw.get("profile") or DEFAULT_PROFILE_KEY),
        ncm=str(raw.get("ncm") or raw.get("codigo_ncm") or ""),
        cest=str(raw.get("cest") or ""),
        unit=str(raw.get("unit") or raw.get("unidade_comercial") or "UN"),
    )


def to_metadata_fiscal(classification: ProductFiscalClassification) -> dict:
    """Serialize back to the compact shape stored in ``Product.metadata['fiscal']``."""
    data = {
        "profile": classification.profile,
        "ncm": classification.ncm,
        "unit": classification.unit,
    }
    if classification.cest:
        data["cest"] = classification.cest
    return data


def resolve_fiscal_item(
    classification: ProductFiscalClassification,
    *,
    interstate: bool = False,
) -> dict:
    """Merge a product's classification with its profile into the flat dict the
    fiscal adapter consumes (``fiscal_focusnfe`` reads exactly these keys).

    ``interstate`` selects the CFOP flavour by the buyer's UF (intrastate is the
    default; interstate is rare and, for consumer sales, ultimately needs NF-e).
    """
    profile = classification.fiscal_profile
    if profile is None:
        raise ValueError(f"Perfil fiscal desconhecido: {classification.profile!r}.")

    item = {
        "ncm": classification.ncm,
        "cfop": profile.cfop_interstate if interstate else profile.cfop_internal,
        "unit": classification.unit,
        "icms_origem": profile.icms_origem,
        "icms_situacao_tributaria": profile.csosn,
        "pis_situacao_tributaria": profile.pis_cst,
        "cofins_situacao_tributaria": profile.cofins_cst,
    }
    if profile.requires_cest and classification.cest:
        item["cest"] = classification.cest
    return item
