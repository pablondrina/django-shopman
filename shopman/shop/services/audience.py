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

O envio sai em **ondas** (``AudienceResult.waves()``): o VIP abre, o geral vem
depois do atraso configurado, e quem tem hora habitual conhecida
(``CustomerInsight.preferred_hour``) pode ser adiado até ela — nunca além da
janela da regra, porque fornada quente não espera o dia inteiro.
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
    #: Hora habitual de compra (0-23), de ``CustomerInsight.preferred_hour``.
    #: ``None`` para quem ainda não tem padrão — esse recebe na hora.
    preferred_hour: int | None = None


@dataclass(frozen=True)
class Wave:
    """Uma leva de envio: quem recebe, e daqui a quantos minutos.

    ``key`` é o identificador estável que viaja na Directive. O handler de
    despacho volta com ele em ``select_wave`` para reconstruir a lista, porque
    entre a criação do post e o envio a audiência muda.
    """

    key: str
    recipients: tuple[Recipient, ...] = ()
    delay_minutes: int = 0


@dataclass(frozen=True)
class AudienceResult:
    """Audiência resolvida, já dividida em ondas."""

    general: tuple[Recipient, ...] = ()
    vip: tuple[Recipient, ...] = ()
    vip_delay_minutes: int = 0
    preferred_hour_window_hours: int = 0
    counts: dict = field(default_factory=dict)

    @property
    def total(self) -> int:
        return len(self.general) + len(self.vip)

    def all_recipients(self) -> tuple[Recipient, ...]:
        return tuple(self.vip) + tuple(self.general)

    def waves(self, *, now=None) -> tuple[Wave, ...]:
        """Planejar as levas de envio. Determinístico para um dado ``now``.

        Duas dimensões se combinam: o grupo (VIP abre, geral espera
        ``vip_delay_minutes``) e a hora habitual de cada pessoa. Quem não tem
        hora habitual utilizável fica na leva-base do seu grupo; quem tem sai
        numa leva própria daquela hora.

        A **estrutura** das ondas vem da config; a **participação**, da
        resolução no envio. Por isso a onda-base de cada grupo sai sempre,
        mesmo vazia agora: entre este planejamento e o disparo a fila do "me
        avise" cresce, e um VIP que só se qualifica depois ainda encontra a
        onda VIP esperando por ele. Colapsar o split porque a lista está vazia
        neste instante jogaria fora justamente o privilégio que a regra pede.

        Só as ondas de hora habitual dependem de gente existir, porque elas
        nascem das pessoas que já estão na lista.
        """
        now = now or timezone.localtime()
        groups = (
            [("vip", self.vip, 0), ("general", self.general, self.vip_delay_minutes)]
            if self.vip_delay_minutes > 0
            else [("all", self.all_recipients(), 0)]
        )

        waves: list[Wave] = []
        for name, recipients, base_delay in groups:
            # A chave None (onda-base) existe sempre; as de hora, só com gente.
            buckets: dict[int | None, list[Recipient]] = {None: []}
            for recipient in recipients:
                deferral = _defer_minutes(
                    recipient.preferred_hour,
                    now=now,
                    window_hours=self.preferred_hour_window_hours,
                )
                # A hora habitual só adia; nunca antecipa o que o grupo já deve.
                key = recipient.preferred_hour if deferral > base_delay else None
                buckets.setdefault(key, []).append(recipient)

            for hour, members in sorted(buckets.items(), key=lambda kv: (kv[0] is not None, kv[0])):
                if hour is None:
                    waves.append(Wave(key=name, recipients=tuple(members), delay_minutes=base_delay))
                    continue
                if not members:
                    continue
                delay = _defer_minutes(
                    hour, now=now, window_hours=self.preferred_hour_window_hours
                )
                waves.append(
                    Wave(key=f"{name}@{hour}", recipients=tuple(members), delay_minutes=delay)
                )
        return tuple(waves)

    def summary(self) -> dict:
        """Resumo persistível em ``BroadcastPost.audience`` (só números, sem PII)."""
        return {
            **self.counts,
            "vip_count": len(self.vip),
            "general_count": len(self.general),
            "vip_delay_minutes": self.vip_delay_minutes,
            "wave_count": len(self.waves()),
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
    window = max(int(rules.get("preferred_hour_window_hours") or 0), 0)

    vip_delay = int(rules.get("vip_first_minutes") or 0)
    if vip_delay <= 0:
        return AudienceResult(
            general=tuple(recipients), preferred_hour_window_hours=window, counts=counts
        )

    vips = tuple(r for r in recipients if r.is_vip)
    general = tuple(r for r in recipients if not r.is_vip)
    return AudienceResult(
        general=general,
        vip=vips,
        vip_delay_minutes=vip_delay,
        preferred_hour_window_hours=window,
        counts=counts,
    )


def select_wave(sku: str, rules: dict | None, wave_key: str, *, now=None) -> tuple[Recipient, ...]:
    """Os destinatários de uma onda, resolvidos agora.

    Contrato de despacho: a Directive carrega só ``wave_key``, e quem envia
    volta aqui. Onda que sumiu (ninguém mais se encaixa) devolve tupla vazia,
    que é resposta normal, não erro.
    """
    result = resolve(sku, rules)
    for wave in result.waves(now=now):
        if wave.key == wave_key:
            return wave.recipients
    return ()


def _defer_minutes(preferred_hour, *, now, window_hours: int) -> int:
    """Minutos até a hora habitual do cliente, ou 0 para enviar já.

    Adia só para frente e só dentro da janela: hora que já passou hoje não
    empurra a mensagem para amanhã (a novidade teria envelhecido), e hora
    distante demais também não. Fora desses limites, enviar agora é melhor
    que enviar tarde.
    """
    if preferred_hour is None or window_hours <= 0:
        return 0
    try:
        hour = int(preferred_hour)
    except (TypeError, ValueError):
        return 0
    if not 0 <= hour <= 23:
        return 0

    target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    minutes = int((target - now).total_seconds() // 60)
    if minutes <= 0 or minutes > window_hours * 60:
        return 0
    return minutes


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
        customer_ref = (customer_ref or "").strip()
        is_vip, preferred_hour = _profile(customer_ref)
        out.append(
            Recipient(
                phone=phone,
                customer_ref=customer_ref,
                is_vip=is_vip,
                preferred_hour=preferred_hour,
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
                preferred_hour=getattr(insight, "preferred_hour", None),
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
            Customer.objects.filter(ref__in=refs, is_active=True)
            .exclude(phone="")
            .select_related("insight")
        )
    except Exception:
        logger.warning("audience.customer_lookup_failed", exc_info=True)
        return []

    out = []
    for customer in customers:
        is_vip, preferred_hour = _profile(customer.ref, customer=customer)
        out.append(
            Recipient(
                phone=customer.phone,
                customer_ref=customer.ref,
                is_vip=is_vip,
                preferred_hour=preferred_hour,
            )
        )
    return out


def _profile(customer_ref: str, *, customer=None) -> tuple[bool, int | None]:
    """``(is_vip, preferred_hour)`` de um cliente, numa passada só.

    As duas respostas saem do mesmo ``CustomerInsight``, então lê-las juntas
    evita repetir a consulta para cada destinatário.
    """
    if not customer_ref:
        return False, None
    try:
        if customer is None:
            from shopman.guestman.models import Customer

            customer = Customer.objects.filter(ref=customer_ref).first()
        if customer is None:
            return False, None

        insight = getattr(customer, "insight", None)
        preferred_hour = getattr(insight, "preferred_hour", None) if insight else None

        if insight is not None and insight.rfm_segment in VIP_RFM_SEGMENTS:
            return True, preferred_hour

        from shopman.guestman.contrib.loyalty.models import LoyaltyAccount

        tier = (
            LoyaltyAccount.objects.filter(customer=customer)
            .values_list("tier", flat=True)
            .first()
        )
        return tier in VIP_LOYALTY_TIERS, preferred_hour
    except Exception:
        logger.debug("audience.profile_failed ref=%s", customer_ref, exc_info=True)
        return False, None


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
                preferred_hour=recipient.preferred_hour,
            )
            continue
        by_phone[recipient.phone] = Recipient(
            phone=existing.phone,
            # Um match anônimo (só telefone) não apaga o vínculo já conhecido.
            customer_ref=existing.customer_ref or recipient.customer_ref,
            reasons=existing.reasons | {reason},
            is_vip=existing.is_vip or recipient.is_vip,
            # Idem para a hora habitual: a primeira conhecida vale.
            preferred_hour=(
                existing.preferred_hour
                if existing.preferred_hour is not None
                else recipient.preferred_hour
            ),
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
