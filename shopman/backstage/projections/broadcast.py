"""
Projeção do Broadcast para o gestor — o lado REVISÃO do marketing operacional.

A operação gera o post; o gestor decide se ele sai. Esta projeção é o que a
superfície `surfaces/broadcast-nuxt` lê: os posts que pedem decisão agora, os
que já saíram, e as regras/modelos que governam tudo isso.

Read-only. Frozen dataclasses convertidos por ``backstage.api.projections``.

Duas escolhas deliberadas:

- **Contagem, nunca destinatário.** ``audience`` traz só números (o serviço já
  persiste assim, sem PII). A superfície formata a frase; o backend não manda
  string pronta.
- **Prazo em minutos, não instante.** Frescor de fornada é efêmero: o card
  precisa mostrar "expira em 12 min", e um ISO cru obrigaria a superfície a
  reimplementar a régua de expiração.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from django.utils import timezone

from shopman.shop.models import (
    BroadcastPost,
    BroadcastRule,
    PostStatus,
    PostTemplate,
    Trigger,
)

#: Plataformas que uma regra pode alvejar, na ordem em que aparecem no formulário.
PLATFORM_CHOICES: tuple[tuple[str, str], ...] = (
    ("instagram", "Instagram"),
    ("facebook", "Facebook"),
    ("google_business", "Google Meu Negócio"),
    ("whatsapp", "WhatsApp"),
    ("tv", "TV da loja"),
)

#: Janela do "publicados recentemente" no painel.
RECENT_WINDOW = timedelta(hours=24)


@dataclass(frozen=True)
class PlatformResultProjection:
    """Como foi em UMA plataforma. Uma falha no Instagram não some do painel."""

    platform: str
    label: str
    status: str  # published | pending_manual | failed | queued
    detail: str
    url: str


@dataclass(frozen=True)
class BroadcastPostProjection:
    pk: int
    status: str
    status_label: str
    body: str
    image_url: str
    hashtags: tuple[str, ...]
    link: str
    platforms: tuple[str, ...]
    audience: dict
    audience_total: int
    platform_results: tuple[PlatformResultProjection, ...]
    trigger: str
    trigger_label: str
    rule_name: str
    template_name: str
    sku: str
    created_at: str
    expires_at: str
    expires_in_minutes: int  # -1 = não expira
    published_at: str
    approved_by: str


@dataclass(frozen=True)
class BroadcastStatsProjection:
    """Números do dia. Poucos e honestos — não é dashboard de engajamento."""

    pending_count: int
    published_today: int
    audience_reached_today: int
    failed_today: int


@dataclass(frozen=True)
class BroadcastBoardProjection:
    pending: tuple[BroadcastPostProjection, ...]
    recent: tuple[BroadcastPostProjection, ...]
    stats: BroadcastStatsProjection


@dataclass(frozen=True)
class BroadcastRuleProjection:
    pk: int
    name: str
    trigger: str
    trigger_label: str
    trigger_filter: dict
    template_id: int
    template_name: str
    platforms: tuple[str, ...]
    audience_rules: dict
    schedule: dict
    requires_approval: bool
    expires_after_minutes: int
    is_active: bool


@dataclass(frozen=True)
class PostTemplateProjection:
    pk: int
    name: str
    body: str
    variables: tuple[str, ...]
    use_ai_generation: bool
    image_source: str
    is_active: bool


@dataclass(frozen=True)
class ChoiceProjection:
    value: str
    label: str


@dataclass(frozen=True)
class BroadcastOptionsProjection:
    """O que o formulário de regra precisa saber sem hardcodar o domínio."""

    triggers: tuple[ChoiceProjection, ...]
    platforms: tuple[ChoiceProjection, ...]
    templates: tuple[PostTemplateProjection, ...]
    variables: tuple[str, ...]


# ── Posts ────────────────────────────────────────────────────────────


def _platform_label(platform: str) -> str:
    return dict(PLATFORM_CHOICES).get(platform, platform)


def _expires_in_minutes(post: BroadcastPost, *, now) -> int:
    """Minutos até caducar. -1 = não expira; 0 = já passou da hora."""
    if not post.expires_at:
        return -1
    remaining = (post.expires_at - now).total_seconds() / 60
    return max(0, int(remaining))


def _result_detail(result: dict) -> str:
    """O PORQUÊ, venha da chave que vier.

    O handler grava ``reason`` no pending_manual e ``error`` na falha (nunca um
    ``detail`` genérico). Ler só uma das chaves deixaria o gestor com um "falhou"
    mudo — justamente a informação que ele precisa para agir.
    """
    for key in ("detail", "reason", "error"):
        value = result.get(key)
        if value:
            return str(value)

    # WhatsApp não falha em bloco: ele conta entregas. "38 enviados, 2 falharam"
    # é o resultado real de uma onda.
    if "sent" in result:
        sent = int(result.get("sent") or 0)
        failed = int(result.get("failed") or 0)
        parts = [f"{sent} enviados"]
        if failed:
            parts.append(f"{failed} falharam")
        return ", ".join(parts)
    return ""


def _platform_results(post: BroadcastPost) -> tuple[PlatformResultProjection, ...]:
    """Resultado por plataforma, com as ainda sem resposta marcadas como `queued`.

    Plataforma alvejada e sem resultado não some da lista: silêncio no painel
    esconde exatamente o caso que o gestor precisa ver.
    """
    results = post.platform_results or {}
    return tuple(
        PlatformResultProjection(
            platform=platform,
            label=_platform_label(platform),
            status=str((results.get(platform) or {}).get("status") or "queued"),
            detail=_result_detail(results.get(platform) or {}),
            url=str((results.get(platform) or {}).get("url") or ""),
        )
        for platform in (post.platforms or [])
    )


def _iso(value) -> str:
    return value.isoformat() if value else ""


def build_post(post: BroadcastPost, *, now=None) -> BroadcastPostProjection:
    now = now or timezone.now()
    content = post.content or {}
    context = post.trigger_context or {}
    audience = post.audience or {}
    approver = post.approved_by

    return BroadcastPostProjection(
        pk=post.pk,
        status=post.status,
        status_label=post.get_status_display(),
        body=str(content.get("body") or ""),
        image_url=str(content.get("image_url") or ""),
        hashtags=tuple(content.get("hashtags") or ()),
        link=str(content.get("link") or ""),
        platforms=tuple(post.platforms or ()),
        audience=dict(audience),
        audience_total=int(audience.get("total") or 0),
        platform_results=_platform_results(post),
        trigger=post.rule.trigger if post.rule_id else "",
        trigger_label=post.rule.get_trigger_display() if post.rule_id else "",
        rule_name=post.rule.name if post.rule_id else "",
        template_name=post.template.name if post.template_id else "",
        sku=str(context.get("sku") or ""),
        created_at=_iso(post.created_at),
        expires_at=_iso(post.expires_at),
        expires_in_minutes=_expires_in_minutes(post, now=now),
        published_at=_iso(post.published_at),
        approved_by=(approver.get_full_name() or approver.username) if approver else "",
    )


def _posts_queryset():
    return BroadcastPost.objects.select_related("rule", "template", "approved_by")


def build_board(*, now=None) -> BroadcastBoardProjection:
    """Painel do gestor: o que pede decisão, o que já saiu, e o placar do dia."""
    now = now or timezone.now()
    today = timezone.localdate()

    pending = [
        post
        for post in _posts_queryset().filter(status=PostStatus.PENDING_REVIEW)
        if not post.is_expired(now=now)
    ]
    recent = list(
        _posts_queryset().filter(
            status__in=(PostStatus.PUBLISHED, PostStatus.PUBLISHING, PostStatus.FAILED),
            created_at__gte=now - RECENT_WINDOW,
        )[:50]
    )

    published_today = [
        post for post in recent
        if post.published_at and timezone.localtime(post.published_at).date() == today
    ]
    reached = sum(int((post.audience or {}).get("total") or 0) for post in published_today)

    return BroadcastBoardProjection(
        pending=tuple(build_post(post, now=now) for post in pending),
        recent=tuple(build_post(post, now=now) for post in recent),
        stats=BroadcastStatsProjection(
            pending_count=len(pending),
            published_today=len(published_today),
            audience_reached_today=reached,
            failed_today=sum(1 for post in recent if post.status == PostStatus.FAILED),
        ),
    )


def build_history(*, limit: int = 100, now=None) -> tuple[BroadcastPostProjection, ...]:
    """Tudo que já saiu (ou tentou sair), do mais recente para o mais antigo."""
    now = now or timezone.now()
    posts = _posts_queryset().filter(
        status__in=(PostStatus.PUBLISHED, PostStatus.PUBLISHING, PostStatus.FAILED)
    )[:limit]
    return tuple(build_post(post, now=now) for post in posts)


# ── Regras e modelos ─────────────────────────────────────────────────


def build_rule(rule: BroadcastRule) -> BroadcastRuleProjection:
    return BroadcastRuleProjection(
        pk=rule.pk,
        name=rule.name,
        trigger=rule.trigger,
        trigger_label=rule.get_trigger_display(),
        trigger_filter=dict(rule.trigger_filter or {}),
        template_id=rule.template_id,
        template_name=rule.template.name if rule.template_id else "",
        platforms=tuple(rule.platforms or ()),
        audience_rules=dict(rule.audience_rules or {}),
        schedule=dict(rule.schedule or {}),
        requires_approval=rule.requires_approval,
        expires_after_minutes=rule.expires_after_minutes,
        is_active=rule.is_active,
    )


def build_rules() -> tuple[BroadcastRuleProjection, ...]:
    rules = BroadcastRule.objects.select_related("template").all()
    return tuple(build_rule(rule) for rule in rules)


def build_template(template: PostTemplate) -> PostTemplateProjection:
    return PostTemplateProjection(
        pk=template.pk,
        name=template.name,
        body=template.body,
        variables=tuple(template.variables or ()),
        use_ai_generation=template.use_ai_generation,
        image_source=template.image_source,
        is_active=template.is_active,
    )


def build_templates() -> tuple[PostTemplateProjection, ...]:
    return tuple(build_template(template) for template in PostTemplate.objects.all())


def build_options() -> BroadcastOptionsProjection:
    from shopman.shop.services.broadcast import available_variables

    return BroadcastOptionsProjection(
        triggers=tuple(
            ChoiceProjection(value=value, label=label) for value, label in Trigger.choices
        ),
        platforms=tuple(
            ChoiceProjection(value=value, label=label) for value, label in PLATFORM_CHOICES
        ),
        templates=build_templates(),
        variables=available_variables(),
    )
