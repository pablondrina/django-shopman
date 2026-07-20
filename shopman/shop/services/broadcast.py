"""BroadcastService — evento operacional vira conteúdo, conteúdo vira post.

O fluxo inteiro (FOMO-BROADCAST-SPECS §2.2):

    fornada concluída → evaluate() → casa BroadcastRules → resolve conteúdo
    → resolve audiência → cria BroadcastPost → notifica o gestor
    → approve() → Directives por plataforma

Duas escolhas estruturais:

- **Directive por plataforma.** Publicar é I/O externo e falível. Cada
  plataforma vira uma Directive com dedupe_key própria, então retry e
  idempotência vêm de graça do Core (ADR-003) e uma falha no Instagram não
  derruba o Google Business.
- **A audiência é resolvida na criação, mas os destinatários não são
  persistidos.** ``BroadcastPost.audience`` guarda só contagens; a lista real
  é recalculada no despacho. Post que dorme 20 min esperando aprovação não
  pode disparar para uma audiência congelada e vencida.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from shopman.shop.directives import BROADCAST_NOTIFY, BROADCAST_POST, create_deduped
from shopman.shop.models import (
    QUALITY_LEVELS,
    BroadcastPost,
    BroadcastRule,
    PostStatus,
)
from shopman.shop.services import audience as audience_service
from shopman.shop.services import broadcast_schedule

logger = logging.getLogger(__name__)

#: Plataformas que publicam conteúdo (vs. notificar audiência direta).
POSTING_PLATFORMS = ("instagram", "facebook", "google_business")


class BroadcastError(Exception):
    """Erro de negócio do broadcast (post inexistente, estado inválido)."""


# ── Avaliação ────────────────────────────────────────────────────────


def evaluate(trigger: str, context: dict | None = None) -> list[BroadcastPost]:
    """Avaliar as regras ativas de um trigger e criar os posts que couberem.

    Args:
        trigger: valor de ``Trigger`` (ex.: ``production_finished``).
        context: snapshot do evento — ``sku``, ``quality``, ``quantity``,
            ``work_order_ref``, ``available_qty``…

    Returns:
        Os posts criados. Lista vazia é resposta normal (nenhuma regra casou).
    """
    context = dict(context or {})
    rules = BroadcastRule.objects.filter(trigger=trigger, is_active=True).select_related(
        "template"
    )

    posts = []
    for rule in rules:
        try:
            if not matches_filter(rule, context):
                continue
            posts.append(_create_post(rule, context))
        except Exception:
            # Uma regra quebrada não pode calar as outras nem derrubar a
            # transação da fornada que a disparou.
            logger.warning(
                "broadcast.rule_failed rule=%s trigger=%s", rule.pk, trigger, exc_info=True
            )
    return posts


def _create_post(rule: BroadcastRule, context: dict) -> BroadcastPost:
    sku = context.get("sku", "")
    content = resolve_content(rule.template, context)
    resolved = audience_service.resolve(sku, rule.audience_rules)

    # Fora da janela preferida, o post nasce com hora marcada. Vale para os dois
    # caminhos: no automático o ``dispatch_due`` abre a porta na hora; no que
    # exige revisão a hora fica como sugestão da regra, e o gestor confirma ou
    # atropela.
    publish_at = broadcast_schedule.next_publish_at(rule.schedule)

    post = BroadcastPost.objects.create(
        rule=rule,
        template=rule.template,
        status=PostStatus.PENDING_REVIEW if rule.requires_approval else PostStatus.APPROVED,
        content=content,
        platform_content=_platform_content(rule.template, content),
        platforms=list(rule.platforms or []),
        audience=resolved.summary(),
        trigger_context=context,
        publish_at=publish_at,
        expires_at=_expiry(rule),
    )

    if rule.requires_approval:
        notify_reviewers(rule, post)
    elif publish_at is None:
        dispatch(post)
    return post


def matches_filter(rule: BroadcastRule, context: dict) -> bool:
    """Condições extras do ``trigger_filter``. Filtro ausente = casa sempre."""
    rule_filter = rule.trigger_filter or {}

    collections = rule_filter.get("collections")
    if collections:
        item_collections = context.get("collections") or []
        if not any(ref in collections for ref in item_collections):
            return False

    skus = rule_filter.get("skus")
    if skus and context.get("sku") not in skus:
        return False

    quality_min = rule_filter.get("quality_min")
    if quality_min and not _quality_at_least(context.get("quality"), quality_min):
        return False

    max_remaining = rule_filter.get("max_remaining")
    if max_remaining is not None:
        try:
            if int(context.get("available_qty") or 0) > int(max_remaining):
                return False
        except (TypeError, ValueError):
            return False

    return True


def _quality_at_least(quality, minimum) -> bool:
    """Hierarquia excelente > bom > regular. Qualidade não informada = "bom"."""
    quality = str(quality or "bom")
    if quality not in QUALITY_LEVELS or minimum not in QUALITY_LEVELS:
        return False
    return QUALITY_LEVELS.index(quality) >= QUALITY_LEVELS.index(minimum)


def _expiry(rule: BroadcastRule):
    minutes = int(rule.expires_after_minutes or 0)
    if minutes <= 0 or not rule.requires_approval:
        return None
    return timezone.now() + timedelta(minutes=minutes)


# ── Conteúdo ─────────────────────────────────────────────────────────


def resolve_content(template, context: dict) -> dict:
    """Renderizar o template com as variáveis do evento."""
    variables = resolve_variables(context)
    body = render(template.body, variables)
    return {
        "body": body,
        "hashtags": variables["hashtags_list"],
        "link": variables["link"],
        "image_url": _image_url(template, context),
        "variables": {k: v for k, v in variables.items() if not k.endswith("_list")},
    }


def _platform_content(template, content: dict) -> dict:
    """Só grava override onde o template realmente diverge do corpo padrão."""
    out = {}
    for platform, variant in (template.platform_variants or {}).items():
        if not isinstance(variant, dict) or not variant.get("body"):
            continue
        out[platform] = {**variant, "body": content["body"]}
    return out


def render(body: str, variables: dict) -> str:
    """Substituir ``{{var}}`` pelos valores. Variável desconhecida vira vazio.

    Deixar o ``{{cru}}`` na tela seria pior que o silêncio: o gestor aprovaria
    sem perceber e o cliente veria o template.
    """
    import re

    def _replace(match):
        return str(variables.get(match.group(1).strip(), ""))

    rendered = re.sub(r"\{\{\s*([\w_]+)\s*\}\}", _replace, body or "")
    # Um {{preco}} vazio no meio da frase deixa espaço duplo.
    return re.sub(r"[ \t]{2,}", " ", rendered).strip()


def resolve_variables(context: dict) -> dict:
    """As variáveis disponíveis para um template (FOMO-BROADCAST-SPECS §3.2)."""
    sku = context.get("sku", "")
    product = _product(sku)
    hashtags = _hashtags(product)

    return {
        "produto": getattr(product, "name", "") or sku,
        "sku": sku,
        "preco": _price(product),
        "hashtags": " ".join(f"#{tag}" for tag in hashtags),
        "hashtags_list": hashtags,
        "link": _product_link(sku),
        "estoque": str(context.get("available_qty", "") or ""),
        "quantidade": str(context.get("quantity", "") or ""),
        "horario": timezone.localtime().strftime("%Hh%M"),
        "loja": _brand_name(),
        "qualidade": str(context.get("quality", "") or ""),
    }


def available_variables() -> tuple[str, ...]:
    """Nomes válidos num template — documentação viva para o Admin."""
    return (
        "produto", "sku", "preco", "hashtags", "link",
        "estoque", "quantidade", "horario", "loja", "qualidade",
    )


def _product(sku: str):
    if not sku:
        return None
    try:
        from shopman.shop.projections import catalog_context

        return catalog_context.get_product(sku)
    except Exception:
        logger.debug("broadcast.product_lookup_failed sku=%s", sku, exc_info=True)
        return None


def _price(product) -> str:
    if product is None:
        return ""
    try:
        from shopman.utils.monetary import format_money

        price_q = int(getattr(product, "base_price_q", 0) or 0)
        return f"R$ {format_money(price_q)}" if price_q else ""
    except Exception:
        logger.debug("broadcast.price_failed", exc_info=True)
        return ""


def _hashtags(product) -> list[str]:
    """Hashtags do PIM social, em ``Product.metadata["social"]["hashtags"]``.

    Leitura direta do JSONField (schema em docs/reference/data-schemas.md) em
    vez de importar ``offerman.contrib.social``: o shop consome APIs públicas
    do kernel, nunca submódulos internos.
    """
    metadata = getattr(product, "metadata", None)
    if not isinstance(metadata, dict):
        return []
    social = metadata.get("social")
    if not isinstance(social, dict):
        return []
    tags = social.get("hashtags") or []
    return [str(tag) for tag in tags if str(tag).strip()]


def _product_link(sku: str) -> str:
    if not sku:
        return ""
    try:
        from shopman.shop.services import storefront_links

        return storefront_links.product_url(sku)
    except Exception:
        logger.debug("broadcast.link_failed sku=%s", sku, exc_info=True)
        return ""


def _brand_name() -> str:
    try:
        from shopman.shop.models import Shop

        shop = Shop.load()
        return (getattr(shop, "brand_name", "") or getattr(shop, "name", "")) if shop else ""
    except Exception:
        logger.debug("broadcast.brand_failed", exc_info=True)
        return ""


def _image_url(template, context: dict) -> str:
    source = getattr(template, "image_source", "product")
    if source == "none":
        return ""
    if source == "custom":
        return str((template.platform_variants or {}).get("image_url") or "")
    product = _product(context.get("sku", ""))
    return str(getattr(product, "image_url", "") or "")


# ── Aprovação e despacho ─────────────────────────────────────────────


def approve(post_id: int, user, *, publish_at=None, respect_schedule: bool = True) -> BroadcastPost:
    """Gestor aprova e o post sai. Idempotente para quem clica duas vezes.

    Com ``publish_at`` no futuro, o post fica APROVADO e agendado: quem
    despacha é ``dispatch_due`` no ciclo de manutenção. Reagendar um post que
    ainda não saiu é permitido (só muda a hora); um já despachado, não.

    Sem ``publish_at``, a hora sugerida pela regra na criação (janela preferida)
    é honrada — aprovar às 5h um post cuja regra pede 7h agenda para as 7h.
    ``respect_schedule=False`` é o "Publicar agora" do gestor, que vence a
    janela.
    """
    try:
        post = BroadcastPost.objects.get(pk=post_id)
    except BroadcastPost.DoesNotExist as exc:
        raise BroadcastError("Post não encontrado.") from exc

    now = timezone.now()
    if publish_at is None and respect_schedule:
        publish_at = post.publish_at
    scheduled = publish_at is not None and publish_at > now

    if post.status in (PostStatus.PUBLISHED, PostStatus.PUBLISHING):
        return post
    if post.status == PostStatus.APPROVED and not post.publish_at:
        # Já despachado (aprovação imediata anterior) — nada a refazer.
        return post
    if post.status == PostStatus.EXPIRED or post.is_expired(now=now):
        raise BroadcastError("Este post expirou. O momento dele já passou.")

    post.status = PostStatus.APPROVED
    post.approved_by = user if getattr(user, "pk", None) else None
    post.approved_at = now
    post.publish_at = publish_at if scheduled else None
    post.save(update_fields=["status", "approved_by", "approved_at", "publish_at"])

    if not scheduled:
        dispatch(post)
    return post


def update_content(
    post_id: int, *, body=None, hashtags=None, platforms=None, image_url=None
) -> BroadcastPost:
    """Editar o post antes de aprovar. Só o que o gestor de fato mexeu.

    Texto gerado por regra é rascunho, não sentença: o gestor ajusta o tom e as
    plataformas no próprio card. Depois de sair, não se reescreve o passado.
    """
    try:
        post = BroadcastPost.objects.get(pk=post_id)
    except BroadcastPost.DoesNotExist as exc:
        raise BroadcastError("Post não encontrado.") from exc

    if post.status not in (PostStatus.DRAFT, PostStatus.PENDING_REVIEW):
        raise BroadcastError("Este post não está mais em revisão.")

    content = dict(post.content or {})
    if body is not None:
        content["body"] = str(body)
    if hashtags is not None:
        content["hashtags"] = [str(tag).strip() for tag in hashtags if str(tag).strip()]
    if image_url is not None:
        content["image_url"] = str(image_url)

    post.content = content
    post.platform_content = _platform_content(post.template, content) if post.template_id else {}
    if platforms is not None:
        post.platforms = [str(platform) for platform in platforms]
    post.save(update_fields=["content", "platform_content", "platforms"])
    return post


def discard(post_id: int) -> BroadcastPost:
    """Descartar um post pendente sem publicar."""
    try:
        post = BroadcastPost.objects.get(pk=post_id)
    except BroadcastPost.DoesNotExist as exc:
        raise BroadcastError("Post não encontrado.") from exc

    post.status = PostStatus.EXPIRED
    post.save(update_fields=["status"])
    return post


def dispatch(post: BroadcastPost) -> int:
    """Enfileirar uma Directive por plataforma. Retorna quantas foram criadas."""
    post.status = PostStatus.PUBLISHING
    post.save(update_fields=["status"])

    created = 0
    for platform in post.platforms or []:
        if platform in POSTING_PLATFORMS:
            created += _queue_post(post, platform)
        elif platform == "whatsapp":
            created += _queue_notify(post)
        elif platform == "tv":
            _push_tv(post)
            created += 1
        else:
            logger.warning("broadcast.unknown_platform post=%s platform=%s", post.pk, platform)

    if not created:
        logger.info("broadcast.nothing_dispatched post=%s", post.pk)
    return created


def _queue_post(post: BroadcastPost, platform: str) -> int:
    directive = create_deduped(
        BROADCAST_POST,
        payload={"post_id": post.pk, "platform": platform},
        dedupe_key=f"broadcast:{post.pk}:{platform}",
    )
    return 1 if directive else 0


def _queue_notify(post: BroadcastPost) -> int:
    """WhatsApp: uma onda por directive. VIP-first vira duas, com atraso.

    A audiência é resolvida de novo no handler, não aqui: entre a criação do
    post e a aprovação, favoritos e alertas mudam.

    O plano sai de ``AudienceResult.waves()``: o VIP abre, o geral espera
    ``vip_first_minutes``, e quem tem hora habitual conhecida ganha onda própria
    dentro da janela da regra (F11 + F12). Sem VIP na audiência a divisão por
    privilégio é abandonada lá dentro, para ninguém esperar à toa.

    A resolução aqui serve só para *planejar* as ondas; quem envia resolve de
    novo com ``audience.select_wave(sku, rules, wave_key)``, porque entre a
    aprovação e o disparo favoritos e alertas mudam. Por isso a onda-base sai
    mesmo com audiência vazia agora: quem entrar na fila do "me avise" no
    intervalo ainda é alcançado, e o envio no-op se ela seguir vazia.
    """
    rules = (post.rule.audience_rules or {}) if post.rule_id else {}
    sku = (post.trigger_context or {}).get("sku", "")

    waves = audience_service.resolve(sku, rules).waves()

    created = 0
    for wave in waves:
        directive = create_deduped(
            BROADCAST_NOTIFY,
            payload={
                "post_id": post.pk,
                "wave": wave.key,
                "sku": sku,
                "waves_expected": len(waves),
            },
            dedupe_key=f"broadcast:{post.pk}:wa:{wave.key}",
            available_at=(
                timezone.now() + timedelta(minutes=wave.delay_minutes)
                if wave.delay_minutes
                else None
            ),
        )
        created += 1 if directive else 0
    return created


def _push_tv(post: BroadcastPost) -> None:
    """TVs/menuboards: push direto, sem API externa nem credencial.

    Registra o resultado na hora (não há Directive nem handler para a TV), para
    que ``_settle`` consiga fechar um post que mistura TV e plataformas.
    """
    results = dict(post.platform_results or {})
    results["tv"] = {"status": "published"}
    post.platform_results = results
    post.save(update_fields=["platform_results"])

    def _send():
        try:
            from django_eventstream import send_event

            send_event(
                "broadcast-tv",
                "broadcast-post",
                {"post_id": post.pk, "body": post.body, "image_url": post.content.get("image_url", "")},
            )
        except ImportError:
            logger.warning("django_eventstream ausente; push de TV ignorado")
        except Exception:
            logger.warning("broadcast.tv_push_failed post=%s", post.pk, exc_info=True)

    transaction.on_commit(_send)


# ── Notificação do gestor ────────────────────────────────────────────


def notify_reviewers(rule: BroadcastRule, post: BroadcastPost) -> int:
    """Criar ``UserNotification`` acionável para quem pode aprovar.

    Destinatários: ``rule.notify_users`` quando declarado, senão todo mundo
    com ``shop.manage_broadcast``. Retorna quantas notificações criou.
    """
    from shopman.shop.models import NotificationCategory, UserNotification

    users = _reviewers(rule)
    if not users:
        logger.warning("broadcast.no_reviewers post=%s rule=%s", post.pk, rule.pk)
        return 0

    total = post.audience.get("total", 0)
    message = post.body
    if total:
        message = f"{message}\n\nAudiência: {total} cliente(s)."

    created = 0
    for user in users:
        notification = UserNotification.objects.create(
            user=user,
            category=NotificationCategory.BROADCAST,
            title=f"Post pronto para revisão: {rule.name}",
            message=message,
            action_url=f"/broadcast/posts/{post.pk}/",
            action_data={"broadcast_post_id": post.pk},
            is_actionable=True,
        )
        push_user_notification(notification)
        created += 1
    return created


def _reviewers(rule: BroadcastRule):
    from django.contrib.auth import get_user_model

    User = get_user_model()
    explicit = [int(uid) for uid in (rule.notify_users or []) if str(uid).isdigit()]
    if explicit:
        return list(User.objects.filter(pk__in=explicit, is_active=True))

    from django.db.models import Q

    return list(
        User.objects.filter(
            Q(is_superuser=True)
            | Q(user_permissions__codename="manage_broadcast")
            | Q(groups__permissions__codename="manage_broadcast"),
            is_active=True,
        ).distinct()
    )


def push_user_notification(notification) -> None:
    """Push SSE no canal pessoal ``user-<id>`` (ADR-016: só avisa que chegou)."""
    payload = {"id": notification.pk, "category": notification.category}
    user_id = notification.user_id

    def _send():
        try:
            from django_eventstream import send_event

            send_event(f"user-{user_id}", "user-notification", payload)
        except ImportError:
            return
        except Exception:
            logger.warning("broadcast.user_push_failed user=%s", user_id, exc_info=True)

    transaction.on_commit(_send)


# ── Manutenção ───────────────────────────────────────────────────────


def dispatch_due(*, now=None) -> int:
    """Despachar os posts agendados cuja hora chegou. Retorna quantos saíram.

    ``publish_at`` volta a NULL no despacho: é a marca de "ainda não saiu", e
    zerá-la impede que um ciclo seguinte despache o mesmo post de novo.
    """
    now = now or timezone.now()
    due = BroadcastPost.objects.filter(
        status=PostStatus.APPROVED, publish_at__isnull=False, publish_at__lte=now
    )

    dispatched = 0
    for post in due:
        try:
            post.publish_at = None
            post.save(update_fields=["publish_at"])
            dispatch(post)
            dispatched += 1
        except Exception:
            logger.warning("broadcast.scheduled_dispatch_failed post=%s", post.pk, exc_info=True)
    return dispatched


def expire_stale_posts(*, now=None) -> int:
    """Caducar posts pendentes que passaram do prazo. Retorna quantos."""
    now = now or timezone.now()
    return BroadcastPost.objects.filter(
        status=PostStatus.PENDING_REVIEW,
        expires_at__isnull=False,
        expires_at__lte=now,
    ).update(status=PostStatus.EXPIRED)
