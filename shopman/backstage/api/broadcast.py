"""
Backstage Broadcast API — o painel de revisão do marketing operacional.

Contrato consumido por `surfaces/broadcast-nuxt` (:3006). Read = projections de
`backstage.projections.broadcast`; write = aprovar/descartar/editar post e CRUD
de regras e modelos. Gate: ``shop.manage_broadcast`` — o gestor de marketing não
é o gestor de pedidos (FOMO-BROADCAST-SPECS §8).

    GET    broadcast/                    → painel (pendentes, recentes, placar)
    GET    broadcast/history/            → tudo que já saiu
    GET    broadcast/options/            → vocabulário do formulário de regra
    GET    broadcast/posts/<pk>/         → um post
    PATCH  broadcast/posts/<pk>/         → editar antes de aprovar
    POST   broadcast/posts/<pk>/approve/ → publicar
    POST   broadcast/posts/<pk>/discard/ → descartar
    GET    broadcast/rules/              → listar         POST → criar
    PATCH  broadcast/rules/<pk>/         → editar         DELETE → apagar
    GET    broadcast/templates/          → listar         POST → criar
    PATCH  broadcast/templates/<pk>/     → editar         DELETE → apagar

Toda decisão de publicação delega a ``shopman.shop.services.broadcast``: a API
não reimplementa o despacho por plataforma nem a régua de expiração.
"""

from __future__ import annotations

import logging

from django.db.models import ProtectedError
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema, extend_schema_view
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.backstage.api.permissions import HasBackstagePermission
from shopman.backstage.api.projections import projection_data
from shopman.backstage.projections import broadcast as broadcast_projection
from shopman.shop.models import BroadcastPost, BroadcastRule, PostStatus, PostTemplate, Trigger
from shopman.shop.services import broadcast as broadcast_service

logger = logging.getLogger(__name__)

_HISTORY_DEFAULT_LIMIT = 100
_HISTORY_MAX_LIMIT = 300

#: Plataformas aceitas numa regra — mesma lista que a tela oferece.
_VALID_PLATFORMS = {ref for ref, _ in broadcast_projection.PLATFORM_CHOICES}


class _BroadcastBase(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "shop.manage_broadcast"


# ── Leitura ──────────────────────────────────────────────────────────


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Broadcast board — pending posts, recent posts, day stats",
        responses={200: OpenApiResponse(description="Painel do gestor de broadcast.")},
    ),
)
class BroadcastBoardView(_BroadcastBase):
    def get(self, request):
        board = broadcast_projection.build_board()
        return Response({"board": projection_data(board)})


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Broadcast history — everything that went out",
        parameters=[OpenApiParameter("limit", int, description="Máximo de itens (default 100).")],
        responses={200: OpenApiResponse(description="Posts publicados, do mais recente.")},
    ),
)
class BroadcastHistoryView(_BroadcastBase):
    def get(self, request):
        posts = broadcast_projection.build_history(limit=_limit(request))
        return Response({"posts": projection_data(posts)})


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Vocabulary for the rule form (triggers, platforms, templates, variables)",
        responses={200: OpenApiResponse(description="Opções do formulário de regra.")},
    ),
)
class BroadcastOptionsView(_BroadcastBase):
    def get(self, request):
        return Response({"options": projection_data(broadcast_projection.build_options())})


# ── Posts ────────────────────────────────────────────────────────────


class BroadcastPostDetailView(_BroadcastBase):
    """Ler um post, ou editá-lo antes de aprovar.

    A edição é a razão de a revisão existir: a IA (ou o template) escreveu, o
    gestor ajusta o tom e só então publica. Post já despachado não se edita —
    reescrever o que o cliente já leu seria mentira retroativa.
    """

    def get(self, request, pk: int):
        post = _post_or_none(pk)
        if post is None:
            return Response({"detail": "Post não encontrado."}, status=404)
        return Response({"post": projection_data(broadcast_projection.build_post(post))})

    def patch(self, request, pk: int):
        post = _post_or_none(pk)
        if post is None:
            return Response({"detail": "Post não encontrado."}, status=404)
        if post.status not in (PostStatus.DRAFT, PostStatus.PENDING_REVIEW):
            return Response(
                {"detail": "Este post já saiu. Não dá para reescrever o que já foi lido."},
                status=400,
            )

        edits, error = _post_edits(request.data)
        if error:
            return Response(error, status=400)
        if not edits:
            return Response({"detail": "Nada para salvar."}, status=400)

        # Pelo serviço, não direto no model: ele reprojeta ``platform_content``
        # a partir do corpo editado. Salvar só ``content`` deixaria a variação
        # por plataforma com o texto velho — o gestor editaria no vazio.
        try:
            post = broadcast_service.update_content(pk, **edits)
        except broadcast_service.BroadcastError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({"ok": True, "post": projection_data(broadcast_projection.build_post(post))})


class BroadcastPostApproveView(_BroadcastBase):
    """Publicar — agora ou na hora marcada.

    O serviço cria uma Directive por plataforma (retry de graça). As edições do
    card vão no MESMO request: salvar e aprovar em duas chamadas abriria a
    janela para publicar a versão anterior.
    """

    def post(self, request, pk: int):
        publish_at, error = _publish_at(request.data.get("publish_at"))
        if error:
            return Response(error, status=400)

        edits, error = _post_edits(request.data)
        if error:
            return Response(error, status=400)

        try:
            if edits:
                broadcast_service.update_content(pk, **edits)
            post = broadcast_service.approve(
                pk, request.user,
                publish_at=publish_at,
                # "Publicar agora" vence a janela preferida da regra; sem ele,
                # aprovar fora do horário aceita a hora que a regra sugeriu.
                respect_schedule=not _as_bool(request.data.get("publish_now")),
            )
        except broadcast_service.BroadcastError as exc:
            return Response({"detail": str(exc)}, status=400)

        logger.info(
            "broadcast.approved user=%s post=%s publish_at=%s",
            request.user.pk, pk, publish_at or "now",
        )
        return Response({
            "ok": True,
            "scheduled": bool(post.publish_at),
            "post": projection_data(broadcast_projection.build_post(post)),
        })


class BroadcastPostDiscardView(_BroadcastBase):
    """Descartar sem publicar. O momento passou, ou o post não presta."""

    def post(self, request, pk: int):
        try:
            post = broadcast_service.discard(pk)
        except broadcast_service.BroadcastError as exc:
            return Response({"detail": str(exc)}, status=400)

        logger.info("broadcast.discarded user=%s post=%s", request.user.pk, pk)
        return Response({"ok": True, "post": projection_data(broadcast_projection.build_post(post))})


# ── Regras ───────────────────────────────────────────────────────────


class BroadcastRuleListView(_BroadcastBase):
    def get(self, request):
        return Response({"rules": projection_data(broadcast_projection.build_rules())})

    def post(self, request):
        fields, error = _rule_fields(request.data, partial=False)
        if error:
            return Response(error, status=400)
        rule = BroadcastRule.objects.create(**fields)
        return Response(
            {"ok": True, "rule": projection_data(broadcast_projection.build_rule(rule))},
            status=201,
        )


class BroadcastRuleDetailView(_BroadcastBase):
    def get(self, request, pk: int):
        rule = _rule_or_none(pk)
        if rule is None:
            return Response({"detail": "Regra não encontrada."}, status=404)
        return Response({"rule": projection_data(broadcast_projection.build_rule(rule))})

    def patch(self, request, pk: int):
        rule = _rule_or_none(pk)
        if rule is None:
            return Response({"detail": "Regra não encontrada."}, status=404)

        fields, error = _rule_fields(request.data, partial=True)
        if error:
            return Response(error, status=400)
        for name, value in fields.items():
            setattr(rule, name, value)
        rule.save()
        return Response({"ok": True, "rule": projection_data(broadcast_projection.build_rule(rule))})

    def delete(self, request, pk: int):
        rule = _rule_or_none(pk)
        if rule is None:
            return Response({"detail": "Regra não encontrada."}, status=404)
        rule.delete()
        return Response({"ok": True, "pk": pk})


# ── Modelos de post ──────────────────────────────────────────────────


class PostTemplateListView(_BroadcastBase):
    def get(self, request):
        return Response({"templates": projection_data(broadcast_projection.build_templates())})

    def post(self, request):
        fields, error = _template_fields(request.data, partial=False)
        if error:
            return Response(error, status=400)
        template = PostTemplate.objects.create(**fields)
        return Response(
            {"ok": True, "template": projection_data(broadcast_projection.build_template(template))},
            status=201,
        )


class PostTemplateDetailView(_BroadcastBase):
    def get(self, request, pk: int):
        template = PostTemplate.objects.filter(pk=pk).first()
        if template is None:
            return Response({"detail": "Modelo não encontrado."}, status=404)
        return Response({"template": projection_data(broadcast_projection.build_template(template))})

    def patch(self, request, pk: int):
        template = PostTemplate.objects.filter(pk=pk).first()
        if template is None:
            return Response({"detail": "Modelo não encontrado."}, status=404)

        fields, error = _template_fields(request.data, partial=True)
        if error:
            return Response(error, status=400)
        for name, value in fields.items():
            setattr(template, name, value)
        template.save()
        return Response(
            {"ok": True, "template": projection_data(broadcast_projection.build_template(template))}
        )

    def delete(self, request, pk: int):
        template = PostTemplate.objects.filter(pk=pk).first()
        if template is None:
            return Response({"detail": "Modelo não encontrado."}, status=404)
        try:
            template.delete()
        except ProtectedError:
            # ``BroadcastRule.template`` é PROTECT: apagar o modelo deixaria
            # regras órfãs disparando no vazio.
            return Response(
                {"detail": "Há regras usando este modelo. Desative ou troque o modelo delas."},
                status=400,
            )
        return Response({"ok": True, "pk": pk})


# ── Validação e leitura de payload ───────────────────────────────────


def _rule_fields(data, *, partial: bool) -> tuple[dict, dict | None]:
    """Campos válidos de uma regra, ou o erro no dialeto canônico."""
    fields: dict = {}

    if not partial or "name" in data:
        name = str(data.get("name") or "").strip()
        if not name:
            return {}, {"detail": "A regra precisa de um nome.", "field": "name"}
        fields["name"] = name

    if not partial or "trigger" in data:
        trigger = str(data.get("trigger") or "").strip()
        if trigger not in Trigger.values:
            return {}, {"detail": "Gatilho desconhecido.", "field": "trigger"}
        fields["trigger"] = trigger

    if not partial or "template_id" in data:
        template = PostTemplate.objects.filter(pk=_as_int(data.get("template_id"))).first()
        if template is None:
            return {}, {"detail": "Modelo de post não encontrado.", "field": "template_id"}
        fields["template"] = template

    if not partial or "platforms" in data:
        platforms, error = _platforms(data.get("platforms"))
        if error:
            return {}, error
        if not platforms:
            return {}, {
                "detail": "Escolha ao menos uma plataforma.",
                "field": "platforms",
            }
        fields["platforms"] = platforms

    for name in ("trigger_filter", "audience_rules", "schedule"):
        if name in data:
            value = data.get(name)
            if not isinstance(value, dict):
                return {}, {"detail": "Configuração inválida.", "field": name}
            fields[name] = value

    if "notify_users" in data:
        fields["notify_users"] = [
            int(uid) for uid in (data.get("notify_users") or []) if str(uid).isdigit()
        ]

    if "requires_approval" in data:
        fields["requires_approval"] = bool(data.get("requires_approval"))
    if "is_active" in data:
        fields["is_active"] = bool(data.get("is_active"))
    if "expires_after_minutes" in data:
        minutes = _as_int(data.get("expires_after_minutes"))
        if minutes is None or minutes < 0:
            return {}, {
                "detail": "O prazo precisa ser um número de minutos (0 = não expira).",
                "field": "expires_after_minutes",
            }
        fields["expires_after_minutes"] = minutes

    return fields, None


def _template_fields(data, *, partial: bool) -> tuple[dict, dict | None]:
    fields: dict = {}

    if not partial or "name" in data:
        name = str(data.get("name") or "").strip()
        if not name:
            return {}, {"detail": "O modelo precisa de um nome.", "field": "name"}
        fields["name"] = name

    if not partial or "body" in data:
        body = str(data.get("body") or "").strip()
        if not body:
            return {}, {"detail": "O modelo precisa de um texto.", "field": "body"}
        fields["body"] = body

    if "image_source" in data:
        source = str(data.get("image_source") or "").strip()
        if source not in PostTemplate.ImageSource.values:
            return {}, {"detail": "Origem de imagem desconhecida.", "field": "image_source"}
        fields["image_source"] = source

    if "platform_variants" in data:
        variants = data.get("platform_variants")
        if not isinstance(variants, dict):
            return {}, {"detail": "Variações inválidas.", "field": "platform_variants"}
        fields["platform_variants"] = variants

    if "variables" in data:
        fields["variables"] = _string_list(data.get("variables"))
    if "ai_prompt" in data:
        fields["ai_prompt"] = str(data.get("ai_prompt") or "").strip()
    if "use_ai_generation" in data:
        fields["use_ai_generation"] = bool(data.get("use_ai_generation"))
    if "is_active" in data:
        fields["is_active"] = bool(data.get("is_active"))

    return fields, None


def _post_edits(data) -> tuple[dict, dict | None]:
    """Edições do card. Chave ausente ≠ campo apagado — só muda o que veio."""
    edits: dict = {}

    if "body" in data:
        body = str(data.get("body") or "").strip()
        if not body:
            return {}, {"detail": "O texto do post não pode ficar vazio.", "field": "body"}
        edits["body"] = body
    if "hashtags" in data:
        edits["hashtags"] = _string_list(data.get("hashtags"))
    if "image_url" in data:
        edits["image_url"] = str(data.get("image_url") or "").strip()
    if "platforms" in data:
        platforms, error = _platforms(data.get("platforms"))
        if error:
            return {}, error
        if not platforms:
            return {}, {"detail": "Escolha ao menos uma plataforma.", "field": "platforms"}
        edits["platforms"] = platforms

    return edits, None


def _publish_at(raw) -> tuple[object | None, dict | None]:
    """ISO 8601 → datetime aware. Vazio = publicar agora."""
    if raw in (None, ""):
        return None, None

    from django.utils import timezone
    from django.utils.dateparse import parse_datetime

    parsed = parse_datetime(str(raw))
    if parsed is None:
        return None, {
            "detail": "Data inválida. Use o formato ISO (2026-07-18T07:00).",
            "field": "publish_at",
        }
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed, None


def _platforms(raw) -> tuple[list[str], dict | None]:
    if not isinstance(raw, list | tuple):
        return [], {"detail": "Plataformas inválidas.", "field": "platforms"}
    platforms = [str(item).strip() for item in raw if str(item).strip()]
    unknown = [item for item in platforms if item not in _VALID_PLATFORMS]
    if unknown:
        return [], {
            "detail": f"Plataforma desconhecida: {', '.join(unknown)}.",
            "field": "platforms",
        }
    return platforms, None


def _string_list(raw) -> list[str]:
    if isinstance(raw, str):
        raw = raw.split(",")
    if not isinstance(raw, list | tuple):
        return []
    return [str(item).strip().lstrip("#") for item in raw if str(item).strip()]


def _post_or_none(pk: int) -> BroadcastPost | None:
    return BroadcastPost.objects.select_related("rule", "template", "approved_by").filter(pk=pk).first()


def _rule_or_none(pk: int) -> BroadcastRule | None:
    return BroadcastRule.objects.select_related("template").filter(pk=pk).first()


def _as_bool(value) -> bool:
    """JSON manda ``true``; form-data manda ``"true"``. Os dois valem."""
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "on")
    return bool(value)


def _as_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _limit(request) -> int:
    raw = request.query_params.get("limit")
    try:
        return max(1, min(int(raw), _HISTORY_MAX_LIMIT)) if raw else _HISTORY_DEFAULT_LIMIT
    except (TypeError, ValueError):
        return _HISTORY_DEFAULT_LIMIT
