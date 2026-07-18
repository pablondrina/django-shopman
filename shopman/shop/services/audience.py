"""AudienceResolver — quem merece saber, e antes de quem.

Cruza um evento operacional (fornada, reposição) com o que já sabemos do
cliente para achar a audiência quente de um SKU: quem favoritou, quem pediu
para ser avisado, quem compra sempre. Nunca a lista toda.

Três invariantes:

1. **Opt-in é lei.** Sem ``CustomerPreference(category="marketing",
   key="broadcast_optin")`` explícito, ninguém recebe broadcast. Sem exceção
   (LGPD e, antes disso, confiança). A única porta lateral é a assinatura de
   alerta por SKU, que já É um opt-in explícito daquele produto.
2. **Um destinatário por telefone.** As três regras se sobrepõem muito; o
   telefone normalizado é a chave de dedupe, então ninguém recebe em dobro.
3. **VIP primeiro é vantagem, não exclusão.** O atraso do grupo geral é uma
   janela de privilégio, e todo mundo acaba recebendo.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)

OPTIN_CATEGORY = "marketing"
OPTIN_KEY = "broadcast_optin"

#: RFM + tier que valem tratamento VIP (mesma régua do ``CustomerInsight.is_vip``).
VIP_RFM_SEGMENTS = ("champion", "loyal_customer")
VIP_LOYALTY_TIERS = ("gold", "platinum")


@dataclass(frozen=True)
class Recipient:
    """Um destinatário resolvido. ``phone`` é a identidade (e a chave de dedupe)."""

    phone: str
    customer_ref: str = ""
    reasons: frozenset = frozenset()  # favorites | alerts | recompra
    is_vip: bool = False


@dataclass(frozen=True)
class AudienceResult:
    """Audiência resolvida, já dividida em ondas."""

    general: tuple[Recipient, ...] = ()
    vip: tuple[Recipient, ...] = ()
    vip_delay_minutes: int = 0
    counts: dict = field(default_factory=dict)

    @property
    def total(self) -> int:
        return len(self.general) + len(self.vip)

    def all_recipients(self) -> tuple[Recipient, ...]:
        return tuple(self.vip) + tuple(self.general)

    def summary(self) -> dict:
        """Resumo persistível em ``BroadcastPost.audience`` (só números, sem PII)."""
        return {
            **self.counts,
            "vip_count": len(self.vip),
            "general_count": len(self.general),
            "vip_delay_minutes": self.vip_delay_minutes,
            "total": self.total,
        }


def resolve(sku: str, rules: dict | None = None) -> AudienceResult:
    """Resolver a audiência de um SKU segundo as regras da BroadcastRule.

    Args:
        sku: SKU do evento.
        rules: ``BroadcastRule.audience_rules`` — ``favorites`` (bool),
            ``alerts`` (bool), ``recompra_days`` (int), ``vip_first_minutes`` (int).

    Returns:
        ``AudienceResult`` vazio quando nenhuma regra está ligada ou ninguém
        passa no opt-in. Audiência vazia é resposta normal, não erro.
    """
    rules = rules or {}
    by_phone: dict[str, Recipient] = {}
    counts: dict[str, int] = {}

    if rules.get("favorites"):
        found = _favorites(sku)
        counts["favorites_count"] = len(found)
        _merge(by_phone, found, reason="favorites")

    if rules.get("alerts"):
        found = _pending_alerts(sku)
        counts["alerts_count"] = len(found)
        _merge(by_phone, found, reason="alerts")

    days = int(rules.get("recompra_days") or 0)
    if days > 0:
        found = _recompra(sku, days)
        counts["recompra_count"] = len(found)
        _merge(by_phone, found, reason="recompra")

    recipients = _filter_opted_in(by_phone.values())

    vip_delay = int(rules.get("vip_first_minutes") or 0)
    if vip_delay <= 0:
        return AudienceResult(general=tuple(recipients), counts=counts)

    vips = tuple(r for r in recipients if r.is_vip)
    general = tuple(r for r in recipients if not r.is_vip)
    return AudienceResult(
        general=general, vip=vips, vip_delay_minutes=vip_delay, counts=counts
    )


# ── Regras de audiência ──────────────────────────────────────────────


def _favorites(sku: str) -> list[Recipient]:
    """F8 — quem marcou este produto como favorito."""
    try:
        from shopman.shop.adapters import audience_sources

        refs = audience_sources.favorite_customer_refs(sku)
    except Exception:
        logger.warning("audience.favorites_failed sku=%s", sku, exc_info=True)
        return []
    return _recipients_for_refs(refs)


def _pending_alerts(sku: str) -> list[Recipient]:
    """F9 — quem pediu explicitamente para ser avisado sobre este SKU.

    A assinatura já é opt-in daquele produto, então dispensa o opt-in geral
    de marketing (``_filter_opted_in`` respeita isso). Anônimo entra só com
    telefone, sem ``customer_ref``.
    """
    try:
        from shopman.shop.adapters import audience_sources

        rows = audience_sources.pending_alert_contacts(sku)
    except Exception:
        logger.warning("audience.alerts_failed sku=%s", sku, exc_info=True)
        return []

    out = []
    for phone, customer_ref in rows:
        phone = (phone or "").strip()
        if not phone:
            continue
        out.append(
            Recipient(
                phone=phone,
                customer_ref=(customer_ref or "").strip(),
                is_vip=_is_vip(customer_ref),
            )
        )
    return out


def _recompra(sku: str, days: int) -> list[Recipient]:
    """F10 — quem comprou este SKU e voltaria a comprar dentro da janela.

    Lê ``CustomerInsight.favorite_products`` (já agregado pelo Guestman) em vez
    de varrer o histórico de pedidos: o insight é o índice desse cruzamento.
    """
    try:
        from shopman.guestman.contrib.insights.models import CustomerInsight

        insights = list(
            CustomerInsight.objects.filter(favorite_products__isnull=False)
            .select_related("customer")
        )
    except Exception:
        logger.warning("audience.recompra_failed sku=%s", sku, exc_info=True)
        return []

    cutoff = timezone.localdate() - timedelta(days=days)
    out = []
    for insight in insights:
        if not _bought_recently(insight, sku=sku, cutoff=cutoff):
            continue
        customer = insight.customer
        phone = (getattr(customer, "phone", "") or "").strip()
        if not phone:
            continue
        out.append(
            Recipient(
                phone=phone,
                customer_ref=getattr(customer, "ref", "") or "",
                is_vip=bool(getattr(insight, "is_vip", False)),
            )
        )
    return out


def _bought_recently(insight, *, sku: str, cutoff) -> bool:
    for entry in insight.favorite_products or []:
        if not isinstance(entry, dict) or entry.get("sku") != sku:
            continue
        last = _as_date(entry.get("ultimo_pedido"))
        # Sem data registrada, o insight ainda conta: ele só existe porque
        # houve compra. A janela filtra quem já esfriou, não quem não datou.
        return last is None or last >= cutoff
    return False


# ── Opt-in ───────────────────────────────────────────────────────────


def _filter_opted_in(recipients) -> list[Recipient]:
    """Manter só quem consentiu — direto (opt-in) ou por assinatura de SKU."""
    recipients = list(recipients)
    refs = {r.customer_ref for r in recipients if r.customer_ref}
    opted_in = _opted_in_refs(refs)

    kept = []
    for recipient in recipients:
        if "alerts" in recipient.reasons:
            kept.append(recipient)  # a assinatura por SKU é o próprio consentimento
            continue
        if recipient.customer_ref and recipient.customer_ref in opted_in:
            kept.append(recipient)
    return kept


def _opted_in_refs(customer_refs: set[str]) -> set[str]:
    """Refs com opt-in de marketing ativo. Valor falsy = opt-out explícito."""
    if not customer_refs:
        return set()
    try:
        from shopman.guestman.contrib.preferences.models import CustomerPreference

        rows = CustomerPreference.objects.filter(
            customer__ref__in=customer_refs,
            category=OPTIN_CATEGORY,
            key=OPTIN_KEY,
        ).values_list("customer__ref", "value")
    except Exception:
        logger.warning("audience.optin_lookup_failed", exc_info=True)
        return set()

    return {ref for ref, value in rows if _optin_is_on(value)}


def _optin_is_on(value) -> bool:
    """``True``, ``{"enabled": true}`` ou ``{"channels": [...]}`` valem opt-in."""
    if value is True:
        return True
    if not isinstance(value, dict):
        return False
    if "enabled" in value:
        return bool(value["enabled"])
    return bool(value.get("channels"))


# ── Helpers ──────────────────────────────────────────────────────────


def _recipients_for_refs(customer_refs: list[str]) -> list[Recipient]:
    refs = [ref for ref in customer_refs if ref]
    if not refs:
        return []
    try:
        from shopman.guestman.models import Customer

        customers = list(
            Customer.objects.filter(ref__in=refs, is_active=True).exclude(phone="")
        )
    except Exception:
        logger.warning("audience.customer_lookup_failed", exc_info=True)
        return []

    return [
        Recipient(phone=c.phone, customer_ref=c.ref, is_vip=_is_vip(c.ref, customer=c))
        for c in customers
    ]


def _is_vip(customer_ref: str, *, customer=None) -> bool:
    """VIP por segmento RFM ou por tier de fidelidade — qualquer um dos dois."""
    if not customer_ref:
        return False
    try:
        if customer is None:
            from shopman.guestman.models import Customer

            customer = Customer.objects.filter(ref=customer_ref).first()
        if customer is None:
            return False

        insight = getattr(customer, "insight", None)
        if insight is not None and insight.rfm_segment in VIP_RFM_SEGMENTS:
            return True

        from shopman.guestman.contrib.loyalty.models import LoyaltyAccount

        tier = (
            LoyaltyAccount.objects.filter(customer=customer)
            .values_list("tier", flat=True)
            .first()
        )
        return tier in VIP_LOYALTY_TIERS
    except Exception:
        logger.debug("audience.vip_check_failed ref=%s", customer_ref, exc_info=True)
        return False


def _merge(by_phone: dict, found: list, *, reason: str) -> None:
    """Somar destinatários deduplicando por telefone e acumulando os motivos."""
    for recipient in found:
        existing = by_phone.get(recipient.phone)
        if existing is None:
            by_phone[recipient.phone] = Recipient(
                phone=recipient.phone,
                customer_ref=recipient.customer_ref,
                reasons=frozenset({reason}),
                is_vip=recipient.is_vip,
            )
            continue
        by_phone[recipient.phone] = Recipient(
            phone=existing.phone,
            # Um match anônimo (só telefone) não apaga o vínculo já conhecido.
            customer_ref=existing.customer_ref or recipient.customer_ref,
            reasons=existing.reasons | {reason},
            is_vip=existing.is_vip or recipient.is_vip,
        )


def _as_date(value):
    from datetime import date, datetime

    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)[:19]).date()
    except ValueError:
        return None
