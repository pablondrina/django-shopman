"""Typed social-PIM attributes stored in ``Product.metadata['social']``.

Dataclass-driven (mirrors ``NutritionFacts`` / ``ProductFiscalClassification``):
the admin form edits proper fields; this module owns the shape, the validation
and the (de)serialization to the ``metadata`` sub-dict. Empty/default values are
NOT persisted, so ``metadata['social']`` stays lean and round-trips cleanly.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from shopman.offerman.contrib.social.taxonomy import google_category_error

# Meta requires ``condition``; a bakery is always "new". Kept configurable for
# generic shelf software (resale/used goods).
CONDITION_CHOICES: tuple[tuple[str, str], ...] = (
    ("new", "Novo"),
    ("refurbished", "Recondicionado"),
    ("used", "Usado"),
)
_CONDITION_VALUES = {value for value, _ in CONDITION_CHOICES}
_DEFAULT_CONDITION = "new"

# GTIN standard lengths (GTIN-8/12/13/14).
_GTIN_LENGTHS = {8, 12, 13, 14}


def _gtin_is_valid(gtin: str) -> bool:
    """GS1 mod-10 check-digit validation for GTIN-8/12/13/14."""
    if not gtin.isdigit() or len(gtin) not in _GTIN_LENGTHS:
        return False
    digits = [int(c) for c in gtin]
    body, check = digits[:-1], digits[-1]
    total = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
    return (10 - (total % 10)) % 10 == check


def _norm_hashtags(raw) -> list[str]:
    """Normalize a list/str of hashtags: strip leading ``#`` and whitespace, drop empties."""
    if isinstance(raw, str):
        items = raw.replace(",", " ").split()
    else:
        items = list(raw or [])
    seen: list[str] = []
    for item in items:
        tag = str(item).lstrip("#").strip()
        if tag and tag not in seen:
            seen.append(tag)
    return seen


@dataclass(frozen=True)
class ProductSocialAttributes:
    """Per-product social/commerce catalog attributes.

    All fields optional with sensible defaults — the operator only fills what
    matters (``brand`` empty resolves to the shop name at projection time;
    ``condition`` defaults to "new"; empty ``gtin`` means "no identifier").
    """

    brand: str = ""
    gtin: str = ""
    mpn: str = ""
    condition: str = _DEFAULT_CONDITION
    google_product_category: str = ""
    tiktok_category_id: str = ""
    hashtags: list[str] = field(default_factory=list)
    social_caption: str = ""

    def __post_init__(self):
        # Accept a raw "tag1, #tag2 tag3" string or a list interchangeably.
        object.__setattr__(self, "hashtags", _norm_hashtags(self.hashtags))

    # ── (de)serialization ────────────────────────────────────────────────

    @classmethod
    def from_metadata(cls, metadata: dict | None) -> ProductSocialAttributes:
        data = {}
        if isinstance(metadata, dict):
            raw = metadata.get("social")
            if isinstance(raw, dict):
                data = raw
        return cls(
            brand=str(data.get("brand") or ""),
            gtin=str(data.get("gtin") or ""),
            mpn=str(data.get("mpn") or ""),
            condition=str(data.get("condition") or _DEFAULT_CONDITION),
            google_product_category=str(data.get("google_product_category") or ""),
            tiktok_category_id=str(data.get("tiktok_category_id") or ""),
            hashtags=_norm_hashtags(data.get("hashtags")),
            social_caption=str(data.get("social_caption") or ""),
        )

    def to_metadata(self) -> dict:
        """The ``metadata['social']`` sub-dict — only non-default keys."""
        out: dict = {}
        if self.brand:
            out["brand"] = self.brand
        if self.gtin:
            out["gtin"] = self.gtin
        if self.mpn:
            out["mpn"] = self.mpn
        if self.condition and self.condition != _DEFAULT_CONDITION:
            out["condition"] = self.condition
        if self.google_product_category:
            out["google_product_category"] = self.google_product_category
        if self.tiktok_category_id:
            out["tiktok_category_id"] = self.tiktok_category_id
        if self.hashtags:
            out["hashtags"] = list(self.hashtags)
        if self.social_caption:
            out["social_caption"] = self.social_caption
        return out

    @property
    def has_data(self) -> bool:
        return bool(self.to_metadata())

    # ── validation ───────────────────────────────────────────────────────

    def errors(self) -> list[str]:
        """Customer/operator-facing validation messages (empty = valid)."""
        problems: list[str] = []
        if self.gtin and not _gtin_is_valid(self.gtin):
            problems.append(
                "GTIN inválido: use 8, 12, 13 ou 14 dígitos com dígito verificador correto "
                "(ou deixe vazio para 'sem código de barras')."
            )
        if self.condition not in _CONDITION_VALUES:
            problems.append(f"Condição inválida: use uma de {sorted(_CONDITION_VALUES)}.")
        cat_error = google_category_error(self.google_product_category)
        if cat_error:
            problems.append(cat_error)
        return problems


# ── module-level helpers (the public read/write API) ──────────────────────


def get_social_attributes(source) -> ProductSocialAttributes:
    """Read social attributes from a Product (or a raw metadata dict)."""
    metadata = getattr(source, "metadata", source)
    return ProductSocialAttributes.from_metadata(metadata if isinstance(metadata, dict) else {})


def set_social_attributes(metadata: dict | None, attrs: ProductSocialAttributes) -> dict:
    """Return a new metadata dict with ``social`` set (or removed when empty)."""
    new = dict(metadata or {})
    payload = attrs.to_metadata()
    if payload:
        new["social"] = payload
    else:
        new.pop("social", None)
    return new
