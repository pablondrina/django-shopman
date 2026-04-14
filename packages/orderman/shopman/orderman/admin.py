from __future__ import annotations

import logging

from django.contrib import admin, messages
from django.db import models
from django.http import HttpRequest, HttpResponseRedirect
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

# Unfold is optional - fallback to standard Django admin if not installed
try:
    from unfold.admin import ModelAdmin as UnfoldModelAdmin
    from unfold.contrib.filters.admin.choice_filters import ChoicesRadioFilter
    from unfold.contrib.filters.admin.datetime_filters import RangeDateFilter
    from unfold.contrib.filters.admin.numeric_filters import RangeNumericFilter
    from unfold.decorators import action as unfold_action, display as unfold_display
    from unfold.enums import ActionVariant
    from unfold.sections import TableSection

    UNFOLD_AVAILABLE = True
    ModelAdmin = UnfoldModelAdmin

    # Use unfold decorators
    def action(func=None, **kwargs):
        return unfold_action(func, **kwargs) if func else unfold_action(**kwargs)

    def display(**kwargs):
        return unfold_display(**kwargs)

except ImportError:
    UNFOLD_AVAILABLE = False
    ModelAdmin = admin.ModelAdmin

    class ActionVariant:
        DEFAULT = "default"
        SUCCESS = "success"
        DANGER = "danger"
        WARNING = "warning"

    class TableSection:
        pass

    # Fallback for filters — must inherit FieldListFilter for tuple-style
    # list_filter entries like ("field", ChoicesRadioFilter) to pass
    # Django 5.x system checks (admin.E115).
    class RangeDateFilter(admin.FieldListFilter):
        """Fallback date range filter."""
        pass

    class RangeNumericFilter(admin.FieldListFilter):
        """Fallback numeric range filter."""
        pass

    class ChoicesRadioFilter(admin.FieldListFilter):
        """Fallback filter when Unfold is not available.

        Standard Django FieldListFilter — renders as default dropdown.
        Unfold's version renders radio buttons, but behavior is identical.
        """
        pass

    # Fallback decorators that work with standard Django admin
    def action(func=None, **kwargs):
        """Fallback action decorator."""
        django_kwargs = {}
        if "description" in kwargs:
            django_kwargs["description"] = kwargs["description"]
        if func:
            return admin.action(**django_kwargs)(func)
        return admin.action(**django_kwargs)

    def display(**kwargs):
        """Fallback display decorator."""
        django_kwargs = {}
        if "description" in kwargs:
            django_kwargs["description"] = kwargs["description"]
        if "ordering" in kwargs:
            django_kwargs["ordering"] = kwargs["ordering"]
        if "boolean" in kwargs:
            django_kwargs["boolean"] = kwargs["boolean"]
        return admin.display(**django_kwargs)

from shopman.utils.monetary import format_money

from shopman.orderman import registry
from shopman.orderman.exceptions import CommitError, IssueResolveError, SessionError
from shopman.orderman.ids import generate_idempotency_key
from shopman.orderman.models import (
    Directive,
    Fulfillment,
    FulfillmentItem,
    IdempotencyKey,
    Order,
    OrderEvent,
    OrderItem,
    Session,
)
from shopman.orderman.services import CommitService, ResolveService


logger = logging.getLogger(__name__)


# =============================================================================
# ACTIONS DETAIL (botões no nível do breadcrumb)
# =============================================================================


def history_action(modeladmin, request, object_id):
    """Action que redireciona para o histórico do objeto."""
    url = reverse(
        f"admin:{modeladmin.model._meta.app_label}_{modeladmin.model._meta.model_name}_history",
        args=[object_id],
    )
    return HttpResponseRedirect(url)


class CanalVendaFilter(admin.SimpleListFilter):
    title = _("canal")
    parameter_name = "channel_ref"

    def lookups(self, request, model_admin):
        from shopman.models import Channel
        qs = Channel.objects.filter(is_active=True).order_by(
            "display_order", "name", "ref"
        )
        return [(c.ref, c.name or c.ref) for c in qs]

    def queryset(self, request, queryset):
        value = self.value()
        if not value:
            return queryset
        return queryset.filter(channel_ref=value)


@admin.register(Session)
class SessionAdmin(ModelAdmin):
    change_form_template = "orderman/admin/session_change_form.html"
    list_display = (
        "session_key",
        "channel_ref",
        "handle_type",
        "handle_ref",
        "state_badge",
        "rev",
        "updated_at",
    )
    list_filter = (CanalVendaFilter, ("state", ChoicesRadioFilter))
    search_fields = ("session_key", "channel_ref", "handle_type", "handle_ref")
    ordering = ("-updated_at", "-id")
    date_hierarchy = "updated_at"
    list_filter_submit = True
    list_fullwidth = True
    compressed_fields = True
    warn_unsaved_form = True

    # Todos os campos são readonly - Sessões são imutáveis após criação
    # Apenas ações podem modificar o estado (ex: commit)
    readonly_fields = (
        "channel_ref",
        "session_key",
        "session_key_content",
        "session_key_display",
        "state",
        "handle_type",
        "handle_ref",
        "opened_at",
        "updated_at",
        "committed_at",
        "rev",
        "items_display",
        "data",
        "commit_token",
    )

    @display(description=_("chave da sessão"))
    def session_key_content(self, obj: Session) -> str:
        """Exibe session_key na aba Conteúdo (repetido propositalmente para consistência visual)."""
        return obj.session_key if obj else "-"

    @display(description=_("chave da sessão"))
    def session_key_display(self, obj: Session) -> str:
        """Exibe session_key na aba Auditoria (repetido propositalmente para consistência com FrontDeskAdmin)."""
        return obj.session_key if obj else "-"

    @display(description=_("itens"))
    def items_display(self, obj: Session) -> str:
        """Exibe items formatado de forma legível, igual ao campo Dados."""
        if not obj or not obj.items:
            return "-"
        import json
        try:
            formatted = json.dumps(obj.items, indent=2, ensure_ascii=False, sort_keys=False)
            return format_html('<pre class="bg-base-50 border border-base-200 dark:bg-base-800 dark:border-base-700 font-mono overflow-x-auto p-3 rounded-default text-sm">{}</pre>', formatted)
        except Exception:
            logger.debug("JSON format failed for Session.items pk=%s", obj.pk, exc_info=True)
            return str(obj.items)

    actions_detail = ["history_detail_action"]
    actions_submit_line = ["action_commit"]

    @action(description=_("Histórico"), url_path="history-action", icon="history")
    def history_detail_action(self, request, object_id):
        return history_action(self, request, object_id)

    @action(description=_("Finalizar sessão"), url_path="commit-action", icon="check_circle")
    def action_commit(self, request: HttpRequest, obj: Session):
        """Finaliza a sessão, criando o pedido."""
        if obj.state != "open":
            messages.error(request, _("Esta sessão não está aberta."))
            return HttpResponseRedirect(reverse("admin:orderman_session_change", args=[obj.pk]))

        if not obj.items:
            messages.error(request, _("Adicione itens antes de finalizar."))
            return HttpResponseRedirect(reverse("admin:orderman_session_change", args=[obj.pk]))

        idempotency_key = generate_idempotency_key()
        actor = getattr(request.user, "username", None) or "admin"

        try:
            result = CommitService.commit(
                session_key=obj.session_key,
                channel_ref=obj.channel.ref,
                idempotency_key=idempotency_key,
                ctx={"actor": actor},
            )
            order_ref = result.get("order_ref", "")

            # Executa diretivas pós-commit automaticamente (ergonomia no admin)
            # Em produção, workers fazem isso; no admin, executamos inline para melhor UX
            # IMPORTANT: Use select_for_update to prevent race conditions with workers
            from django.db import transaction

            executed_count = 0
            failed_count = 0

            # Process directives one at a time with proper locking
            while True:
                with transaction.atomic():
                    # Get ONE directive with lock (skip locked = workers processing it)
                    directive = (
                        Directive.objects
                        .select_for_update(skip_locked=True)
                        .filter(
                            payload__order_ref=order_ref,
                            status="queued",
                        )
                        .first()
                    )

                    if not directive:
                        break  # No more queued directives

                    handler = registry.get_directive_handler(directive.topic)
                    if handler:
                        # Update status to "running" before executing
                        directive.status = "running"
                        directive.attempts += 1
                        directive.started_at = timezone.now()
                        directive.save(update_fields=["status", "attempts", "started_at", "updated_at"])

                        try:
                            handler.handle(
                                message=directive,
                                ctx={"actor": actor},
                            )
                            # Handler updates status to "done" automatically
                            executed_count += 1
                        except Exception as exc:
                            logger.exception("Erro ao executar diretiva %s #%s", directive.topic, directive.pk)
                            directive.status = "failed"
                            directive.last_error = str(exc)
                            directive.save(update_fields=["status", "last_error", "updated_at"])
                            failed_count += 1
                    else:
                        # No handler, mark as failed
                        directive.status = "failed"
                        directive.last_error = _("Nenhum handler registrado para este tópico.")
                        directive.save(update_fields=["status", "last_error", "updated_at"])
                        failed_count += 1

            # Fetch order PK for admin URL (Django admin requires PK, not ref)
            try:
                order_pk = Order.objects.get(ref=order_ref).pk
            except Order.DoesNotExist:
                order_pk = None

            # Mensagem de sucesso com informação sobre diretivas
            if executed_count > 0:
                messages.success(
                    request,
                    format_html(
                        _('Pedido <strong>{}</strong> criado! {} diretiva(s) executada(s). <a href="{}">Ver pedido</a>'),
                        order_ref,
                        executed_count,
                        reverse("admin:orderman_order_change", args=[order_pk]) if order_pk else "#",
                    ),
                )
            else:
                messages.success(
                    request,
                    format_html(
                        _('Pedido <strong>{}</strong> criado! <a href="{}">Ver pedido</a>'),
                        order_ref,
                        reverse("admin:orderman_order_change", args=[order_pk]) if order_pk else "#",
                    ),
                )

            if failed_count > 0:
                messages.warning(
                    request,
                    _("{} diretiva(s) falharam. Verifique em Diretivas.").format(failed_count),
                )

            # Redireciona para o pedido criado, garantindo que apareça na listagem
            if order_pk:
                return HttpResponseRedirect(reverse("admin:orderman_order_change", args=[order_pk]))
            else:
                # Fallback: redireciona para changelist com filtros
                return HttpResponseRedirect(
                    reverse("admin:orderman_order_changelist") + f"?status__exact=new&ref={order_ref}"
                )
        except CommitError as exc:
            # Se hold expirado ou check desatualizado, refaz verificação automaticamente
            if exc.code in ("hold_expired", "stale_check"):
                recheck_result = self._auto_recheck(request, obj, actor)
                if recheck_result == "committed":
                    # Re-check passou e commit funcionou - redireciona sem mensagem adicional
                    return HttpResponseRedirect(reverse("admin:orderman_session_change", args=[obj.pk]))
                elif recheck_result == "has_issues":
                    # Re-check feito, mas há issues - banner já mostrado
                    messages.warning(
                        request,
                        _("Verificação atualizada. Resolva os problemas abaixo antes de finalizar."),
                    )
                else:
                    # Re-check falhou por outro motivo
                    messages.error(request, exc.message)
            else:
                messages.error(request, exc.message)
        except SessionError as exc:
            messages.error(request, exc.message)
        except Exception:
            logger.exception("Erro ao finalizar sessão %s", obj.session_key)
            messages.error(request, _("Erro ao finalizar sessão."))

        # Sempre redireciona após erro para evitar mensagem de sucesso padrão do Django
        return HttpResponseRedirect(reverse("admin:orderman_session_change", args=[obj.pk]))

    def render_change_form(self, request, context, add=False, change=False, form_url="", obj=None):
        """Remove botões extras de submit."""
        # Remove botões "Salvar e adicionar outro" e "Salvar e continuar editando"
        context["show_save_and_add_another"] = False
        context["show_save_and_continue"] = False
        return super().render_change_form(request, context, add, change, form_url, obj)

    fieldsets = (
        (
            _("Identidade"),
            {"fields": ("session_key", "channel_ref", "handle_type", "handle_ref"), "classes": ("tab",)},
        ),
        (_("Conteúdo"), {"fields": ("session_key_content", "items_display", "data"), "classes": ("tab",)}),
        (
            _("Auditoria"),
            {
                "fields": ("session_key_display", "state", "opened_at", "updated_at", "rev"),
                "classes": ("tab",),
            },
        ),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.order_by("-updated_at", "-id")

    # Cores de referência BADGES:
    # - Azul=#5EB1EF (info), Amarelo=#E2A336 (warning), Verde=#5BB98B (success), Vermelho=#EB8E90 (danger), Cinza=secondary
    # - aberta=azul, fechada=cinza, abandonada=vermelho
    @display(
        description=_("status"),
        label={"aberta": "info", "fechada": "secondary", "abandonada": "danger"},
    )
    def state_badge(self, obj: Session) -> str:
        return obj.get_state_display()

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "<path:object_id>/resolve-issue/<str:issue_id>/<str:action_id>/",
                self.admin_site.admin_view(self.resolve_issue_view),
                name="orderman_session_resolve_issue",
            ),
            path(
                "<path:object_id>/run-check/<str:topic>/",
                self.admin_site.admin_view(self.run_check_view),
                name="orderman_session_run_check",
            ),
        ]
        return custom + urls

    def resolve_issue_view(self, request, object_id, issue_id, action_id):
        session = self.get_object(request, object_id)
        if session is None:
            self.message_user(request, _("Sessão não encontrada."), level="error")
            return HttpResponseRedirect(reverse("admin:orderman_session_changelist"))
        try:
            ResolveService.resolve(
                session_key=session.session_key,
                channel_ref=session.channel.ref,
                issue_id=issue_id,
                action_id=action_id,
                ctx={"actor": getattr(getattr(request, "user", None), "username", None) or "admin"},
            )
            self.message_user(request, _("Action aplicada com sucesso."))
        except IssueResolveError as exc:
            self.message_user(request, f"{exc.message}", level="error")
        except Exception:  # pragma: no cover - logging side-effect
            logger.exception(
                "Falha inesperada ao resolver issue %s/%s para sessão %s",
                issue_id,
                action_id,
                getattr(session, "session_key", object_id),
            )
            self.message_user(
                request,
                _("Falha inesperada ao aplicar action. Verifique os logs."),
                level="error",
            )
        return HttpResponseRedirect(
            reverse("admin:orderman_session_change", args=[object_id])
        )

    def run_check_view(self, request, object_id, topic):
        session = self.get_object(request, object_id)
        if session is None:
            self.message_user(request, _("Sessão não encontrada."), level="error")
            return HttpResponseRedirect(reverse("admin:orderman_session_changelist"))

        handler = registry.get_directive_handler(topic)
        if handler is None:
            self.message_user(request, _("Nenhum handler registrado para o tópico informado."), level="error")
            return HttpResponseRedirect(reverse("admin:orderman_session_change", args=[object_id]))

        directive = Directive.objects.create(
            topic=topic,
            status="running",
            started_at=timezone.now(),
            attempts=1,
            payload={
                "session_key": session.session_key,
                "channel_ref": session.channel.ref,
                "rev": session.rev,
                "items": session.items,
            },
        )

        try:
            handler.handle(message=directive, ctx={"actor": getattr(getattr(request, "user", None), "username", None) or "admin"})
            self.message_user(request, _("Check executado com sucesso."))
        except Exception as exc:  # pragma: no cover - handler errors logged?
            logger.exception("Falha ao processar %s para sessão %s", topic, session.session_key)
            directive.status = "failed"
            directive.last_error = str(exc)
            directive.save(update_fields=["status", "last_error", "updated_at"])
            self.message_user(request, f"Erro ao executar check: {exc}", level="error")

        return HttpResponseRedirect(reverse("admin:orderman_session_change", args=[object_id]))

    def _auto_recheck(self, request, session, actor: str) -> str:
        """
        Refaz verificações e tenta commit novamente se possível.

        Chamado automaticamente quando um commit falha por hold expirado
        ou check desatualizado.

        Returns:
            "committed": Commit realizado com sucesso após re-check
            "has_issues": Re-check feito mas há issues bloqueantes
            "failed": Re-check ou commit falhou por outro motivo
        """
        # O kernel não acessa ChannelConfig do framework.
        # Checks específicos por canal são responsabilidade do admin do framework.
        required_checks: list = []
        checks_config: dict = {}

        # Executa todos os checks requeridos
        for check_code in required_checks:
            check_opts = checks_config.get(check_code, {})
            topic = check_opts.get("directive_topic") or f"{check_code}.hold"

            handler = registry.get_directive_handler(topic)
            if handler is None:
                continue

            # Cria e executa diretiva inline
            directive = Directive.objects.create(
                topic=topic,
                status="running",
                started_at=timezone.now(),
                attempts=1,
                payload={
                    "session_key": session.session_key,
                    "channel_ref": session.channel.ref,
                    "rev": session.rev,
                    "items": session.items,
                },
            )

            try:
                handler.handle(message=directive, ctx={"actor": actor})
            except Exception as exc:
                logger.exception("auto_recheck: Falha ao executar %s para sessão %s", topic, session.session_key)
                directive.status = "failed"
                directive.last_error = str(exc)
                directive.save(update_fields=["status", "last_error", "updated_at"])
                return "failed"

        # Recarrega sessão para ver resultado dos checks
        session.refresh_from_db()

        # Verifica se há issues bloqueantes
        issues = session.data.get("issues", [])
        blocking = [i for i in issues if i.get("blocking")]
        if blocking:
            return "has_issues"

        # Tenta commit novamente com nova chave de idempotência
        new_idempotency_key = generate_idempotency_key()
        try:
            result = CommitService.commit(
                session_key=session.session_key,
                channel_ref=session.channel.ref,
                idempotency_key=new_idempotency_key,
                ctx={"actor": actor},
            )
            self.message_user(
                request,
                _("Verificação atualizada. Sessão commitada com sucesso. Ordem %(ref)s criada.") % {"ref": result.get("order_ref")},
            )
            return "committed"
        except CommitError as exc:
            logger.warning("auto_recheck: Commit falhou após re-check para sessão %s: %s", session.session_key, exc.message)
            self.message_user(request, f"{exc.message}", level="error")
            return "failed"
        except Exception:
            logger.exception("auto_recheck: Falha inesperada ao commit após re-check para sessão %s", session.session_key)
            return "failed"
    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        extra_context = extra_context or {}
        if object_id:
            obj = self.get_object(request, object_id)
            if obj:
                extra_context["issue_actions"] = obj.data.get("issues", [])
                manual_checks: list[dict] = []
                # O kernel não acessa ChannelConfig do framework.
                required_checks: list = []
                checks_config: dict = {}
                for code in required_checks:
                    check_opts = checks_config.get(code, {})
                    topic = check_opts.get("directive_topic") or f"{code}.hold"
                    manual_checks.append(
                        {
                            "code": code,
                            "topic": topic,
                            "label": check_opts.get("label") or code,
                        }
                    )
                extra_context["manual_checks"] = manual_checks
        extra_context.setdefault("issue_actions", [])
        extra_context.setdefault("manual_checks", [])
        extra_context.setdefault("can_commit_session", False)
        return super().changeform_view(request, object_id, form_url, extra_context)

    def changelist_view(self, request, extra_context=None):
        # UX: tab padrão = "Abertas" quando não há nenhum filtro explícito.
        if request.method == "GET" and not request.GET:
            return HttpResponseRedirect(f"{request.path}?state__exact=open")

        # UX: date_hierarchy default = hoje quando o operador não escolheu data.
        if request.method == "GET" and self.date_hierarchy:
            field = str(self.date_hierarchy)
            year_p = f"{field}__year"
            month_p = f"{field}__month"
            day_p = f"{field}__day"
            if not any(p in request.GET for p in (year_p, month_p, day_p)):
                today = timezone.localdate()
                q = request.GET.copy()
                q[year_p] = str(today.year)
                q[month_p] = str(today.month)
                q[day_p] = str(today.day)
                return HttpResponseRedirect(f"{request.path}?{q.urlencode()}")

        # Supra-filtro por canal (barra rápida) — preserva contexto e mantém intenção do status (tabs).
        extra_context = extra_context or {}

        from shopman.models import Channel
        channels = list(
            Channel.objects.filter(is_active=True).order_by(
                "display_order", "name", "ref"
            )
        )

        def _qs_for_channel(channel_id: str | None) -> str:
            q = request.GET.copy()
            # Status (tabs): se não houver status explícito, default é "Abertas"
            if "state__exact" not in request.GET:
                q["state__exact"] = "open"
            q.pop("p", None)
            if channel_id:
                q["channel__id__exact"] = str(channel_id)
            else:
                q.pop("channel__id__exact", None)
            return q.urlencode()

        extra_context["channel_quick_filters"] = [
            {
                "id": c.pk,
                "label": c.name or c.ref,
                "ref": c.ref,
                "querystring": _qs_for_channel(str(c.pk)),
            }
            for c in channels
        ]
        extra_context["channel_quick_filters_all"] = _qs_for_channel(None)

        return super().changelist_view(request, extra_context=extra_context)


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = (
        "line_id",
        "sku",
        "name",
        "qty",
        "unit_price_q",
        "line_total_q",
        "meta",
    )
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class OrderEventInline(admin.TabularInline):
    model = OrderEvent
    extra = 0
    readonly_fields = ("type", "actor", "payload", "created_at")
    can_delete = False
    ordering = ("-created_at", "-id")

    def has_add_permission(self, request, obj=None):
        return False


if UNFOLD_AVAILABLE:
    class OrderItemSection(TableSection):
        related_name = "items"
        fields = ["sku", "name", "qty", "unit_price_q", "line_total_q"]
        verbose_name = _("Itens do Pedido")

        def unit_price_q(self, obj):
            return f"R$ {format_money(obj.unit_price_q)}"
        unit_price_q.short_description = _("Preço Unit.")

        def line_total_q(self, obj):
            return f"R$ {format_money(obj.line_total_q)}"
        line_total_q.short_description = _("Total")


class PreorderFilter(admin.SimpleListFilter):
    """Filter orders by preorder status (delivery_date in the future)."""
    title = _("encomenda")
    parameter_name = "preorder"

    def lookups(self, request, model_admin):
        return [
            ("yes", _("Encomendas")),
            ("no", _("Pedidos normais")),
        ]

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.filter(data__is_preorder=True)
        if self.value() == "no":
            return queryset.exclude(data__is_preorder=True)
        return queryset


@admin.register(Order)
class OrderAdmin(ModelAdmin):
    list_display = (
        "ref",
        "channel_ref",
        "handle_ref",
        "status_badge",
        "delivery_date_display",
        "items_count_display",
        "total_display",
        "created_at",
    )
    list_filter = (
        CanalVendaFilter,
        ("status", ChoicesRadioFilter),
        PreorderFilter,
        ("created_at", RangeDateFilter),
        ("total_q", RangeNumericFilter),
    )
    search_fields = ("ref", "channel_ref", "session_key", "handle_ref", "external_ref")
    ordering = ("-created_at", "-id")
    date_hierarchy = "created_at"
    list_filter_submit = True
    list_fullwidth = True
    compressed_fields = True
    warn_unsaved_form = True

    inlines = [OrderItemInline, OrderEventInline]

    actions_detail = ["history_detail_action"]
    actions_row = ["advance_status_row", "cancel_order_row"]
    list_sections = [OrderItemSection] if UNFOLD_AVAILABLE else []

    @action(description=_("Histórico"), url_path="history-action", icon="history")
    def history_detail_action(self, request, object_id):
        return history_action(self, request, object_id)

    @action(
        description=_("Avançar ▸"),
        url_path="advance-status",
        icon="arrow_forward",
        variant=ActionVariant.SUCCESS,
    )
    def advance_status_row(self, request, object_id):
        order = self.get_object(request, object_id)
        if order is None:
            messages.error(request, _("Pedido não encontrado."))
            return HttpResponseRedirect(reverse("admin:orderman_order_changelist"))

        allowed = order.get_allowed_transitions()
        if not allowed:
            messages.warning(request, _("Nenhuma transição disponível para este pedido."))
            return HttpResponseRedirect(reverse("admin:orderman_order_changelist"))

        next_status = allowed[0]
        actor = getattr(request.user, "username", None) or "admin"
        try:
            order.transition_status(next_status, actor=actor)
            messages.success(
                request,
                _("Pedido %(ref)s avançado para %(status)s.") % {
                    "ref": order.ref,
                    "status": order.get_status_display(),
                },
            )
        except Exception as exc:
            messages.error(request, str(exc))

        return HttpResponseRedirect(reverse("admin:orderman_order_changelist"))

    @action(
        description=_("Cancelar ✕"),
        url_path="cancel-order",
        icon="cancel",
        variant=ActionVariant.DANGER,
    )
    def cancel_order_row(self, request, object_id):
        order = self.get_object(request, object_id)
        if order is None:
            messages.error(request, _("Pedido não encontrado."))
            return HttpResponseRedirect(reverse("admin:orderman_order_changelist"))

        if not order.can_transition_to(Order.Status.CANCELLED):
            messages.warning(request, _("Este pedido não pode ser cancelado."))
            return HttpResponseRedirect(reverse("admin:orderman_order_changelist"))

        actor = getattr(request.user, "username", None) or "admin"
        try:
            order.transition_status(Order.Status.CANCELLED, actor=actor)
            messages.success(
                request,
                _("Pedido %(ref)s cancelado.") % {"ref": order.ref},
            )
        except Exception as exc:
            messages.error(request, str(exc))

        return HttpResponseRedirect(reverse("admin:orderman_order_changelist"))

    fieldsets = (
        (
            _("Identidade"),
            {
                "fields": ("ref", "channel_ref", "status", "external_ref"),
                "classes": ("tab",),
            },
        ),
        (
            _("Origem"),
            {"fields": ("session_key", "handle_type", "handle_ref"), "classes": ("tab",)},
        ),
        (_("Valores"), {"fields": ("currency", "total_q"), "classes": ("tab",)}),
        (_("Dados"), {"fields": ("data",), "classes": ("tab",)}),
        (_("Snapshot"), {"fields": ("snapshot",), "classes": ("tab",)}),
        (_("Auditoria"), {"fields": ("created_at", "updated_at"), "classes": ("tab",)}),
    )
    # Todos os campos são readonly - Pedidos são imutáveis após criação
    # Apenas ações podem modificar o estado (ex: avançar status)
    readonly_fields = (
        "ref",
        "channel_ref",
        "session_key",
        "handle_type",
        "handle_ref",
        "external_ref",
        "status",
        "data",
        "snapshot",
        "currency",
        "total_q",
        "created_at",
        "updated_at",
    )

    # Cores de referência BADGES:
    # - Azul=#5EB1EF (info), Amarelo=#E2A336 (warning), Verde=#5BB98B (success), Vermelho=#EB8E90 (danger), Cinza=secondary
    # Status canônicos: new, confirmed, preparing, ready, dispatched, delivered, completed, cancelled, returned
    @display(
        description=_("status"),
        label={
            "novo": "info",
            "confirmado": "info",
            "em preparo": "warning",
            "pronto": "success",
            "despachado": "warning",
            "entregue": "success",
            "concluído": "secondary",
            "cancelado": "danger",
            "devolvido": "danger",
        },
    )
    def status_badge(self, obj: Order) -> str:
        return obj.get_status_display()

    @display(description=_("entrega"))
    def delivery_date_display(self, obj: Order) -> str:
        delivery_date = (obj.data or {}).get("delivery_date")
        if not delivery_date:
            return "-"
        is_preorder = (obj.data or {}).get("is_preorder", False)
        time_slot = (obj.data or {}).get("delivery_time_slot", "")
        label = delivery_date
        if time_slot:
            label += f" ({time_slot})"
        if is_preorder:
            return format_html('<span style="color:#E2A336;font-weight:600">{}</span>', label)
        return label

    @display(description=_("itens"))
    def items_count_display(self, obj: Order) -> str:
        count = obj.items.count()
        return str(count) if count else "-"

    @display(description=_("total"))
    def total_display(self, obj: Order) -> str:
        if obj.total_q:
            return f"{obj.currency} {obj.total_q / 100:.2f}"
        return "-"

    actions = ["advance_selected_status", "cancel_selected"]

    @admin.action(description=_("Avançar status (selecionados)"))
    def advance_selected_status(self, request, queryset):
        """Advance all selected orders to their next status.

        Errors if orders have divergent allowed transitions.
        """
        advanced = 0
        errors = 0
        actor = getattr(request.user, "username", None) or "admin"
        for order in queryset:
            allowed = order.get_allowed_transitions()
            if not allowed:
                errors += 1
                continue
            try:
                order.transition_status(allowed[0], actor=actor)
                advanced += 1
            except Exception:
                errors += 1

        if advanced:
            messages.success(
                request,
                _("%(count)d pedido(s) avançado(s).") % {"count": advanced},
            )
        if errors:
            messages.warning(
                request,
                _("%(count)d pedido(s) não puderam ser avançados.") % {"count": errors},
            )

    @admin.action(description=_("Cancelar selecionados"))
    def cancel_selected(self, request, queryset):
        """Cancel all selected orders (if transition is allowed)."""
        cancelled = 0
        skipped = 0
        actor = getattr(request.user, "username", None) or "admin"
        for order in queryset:
            if not order.can_transition_to(Order.Status.CANCELLED):
                skipped += 1
                continue
            try:
                order.transition_status(Order.Status.CANCELLED, actor=actor)
                cancelled += 1
            except Exception:
                skipped += 1

        if cancelled:
            messages.success(
                request,
                _("%(count)d pedido(s) cancelado(s).") % {"count": cancelled},
            )
        if skipped:
            messages.warning(
                request,
                _("%(count)d pedido(s) não puderam ser cancelados.") % {"count": skipped},
            )

    def changelist_view(self, request, extra_context=None):
        # UX: tab padrão = "Novos" quando não há nenhum filtro explícito.
        # Mas preserva filtros existentes (ex: ref=) se presentes
        if request.method == "GET" and not request.GET:
            return HttpResponseRedirect(f"{request.path}?status__exact=new")
        elif request.method == "GET" and "ref" in request.GET and "status__exact" not in request.GET:
            # Se há filtro por ref mas não há status, adiciona status=new preservando ref
            q = request.GET.copy()
            q["status__exact"] = "new"
            return HttpResponseRedirect(f"{request.path}?{q.urlencode()}")

        # UX: date_hierarchy default = hoje quando o operador não escolheu data.
        if request.method == "GET" and self.date_hierarchy:
            field = str(self.date_hierarchy)
            year_p = f"{field}__year"
            month_p = f"{field}__month"
            day_p = f"{field}__day"
            if not any(p in request.GET for p in (year_p, month_p, day_p)):
                today = timezone.localdate()
                q = request.GET.copy()
                q[year_p] = str(today.year)
                q[month_p] = str(today.month)
                q[day_p] = str(today.day)
                return HttpResponseRedirect(f"{request.path}?{q.urlencode()}")

        # Supra-filtro por canal (barra rápida) — preserva contexto e mantém intenção do status (tabs).
        extra_context = extra_context or {}
        from shopman.models import Channel
        channels = list(
            Channel.objects.filter(is_active=True).order_by(
                "display_order", "name", "ref"
            )
        )

        def _qs_for_channel(channel_id: str | None) -> str:
            q = request.GET.copy()
            if "status__exact" not in request.GET:
                q["status__exact"] = "new"
            # remove alias possível
            q.pop("status", None)
            q.pop("p", None)
            if channel_id:
                q["channel__id__exact"] = str(channel_id)
            else:
                q.pop("channel__id__exact", None)
            return q.urlencode()

        extra_context["channel_quick_filters"] = [
            {
                "id": c.pk,
                "label": c.name or c.ref,
                "ref": c.ref,
                "querystring": _qs_for_channel(str(c.pk)),
            }
            for c in channels
        ]
        extra_context["channel_quick_filters_all"] = _qs_for_channel(None)

        return super().changelist_view(request, extra_context=extra_context)


class HighAttemptsFilter(admin.SimpleListFilter):
    title = "tentativas"
    parameter_name = "high_attempts"

    def lookups(self, request, model_admin):
        return [("yes", "≥ 3 tentativas")]

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.filter(attempts__gte=3)
        return queryset


@admin.register(Directive)
class DirectiveAdmin(ModelAdmin):
    list_display = ("topic", "status_badge", "error_code", "attempts", "available_at", "started_at", "created_at")
    list_filter = (("status", ChoicesRadioFilter), "topic", "error_code", HighAttemptsFilter)
    search_fields = (
        "topic",
        "payload",
        "payload__session_key",
        "payload__order_ref",
        "payload__channel_ref",
        "payload__holds__hold_id",
        "dedupe_key",
    )
    list_filter_submit = True
    ordering = ("-created_at", "-id")
    date_hierarchy = "created_at"
    list_fullwidth = True
    compressed_fields = True
    warn_unsaved_form = True

    actions = ["execute_now_action"]
    actions_row = ["execute_row"]

    fieldsets = (
        (
            _("Diretiva"),
            {"fields": ("topic", "status", "payload", "dedupe_key"), "classes": ("tab",)},
        ),
        (
            _("Execução"),
            {"fields": ("attempts", "available_at", "started_at", "error_code", "last_error"), "classes": ("tab",)},
        ),
        (_("Auditoria"), {"fields": ("created_at", "updated_at"), "classes": ("tab",)}),
    )
    # Todos os campos são readonly - Diretivas são criadas e gerenciadas automaticamente pelo sistema
    # Apenas ações podem modificar o estado (ex: "Executar agora")
    readonly_fields = (
        "topic",
        "status",
        "payload",
        "dedupe_key",
        "attempts",
        "available_at",
        "started_at",
        "error_code",
        "last_error",
        "created_at",
        "updated_at",
    )

    actions_detail = ["history_detail_action"]
    actions_submit_line = ["execute_now_detail_action"]

    @action(description=_("Histórico"), url_path="history-action", icon="history")
    def history_detail_action(self, request, object_id):
        return history_action(self, request, object_id)

    def render_change_form(self, request, context, add=False, change=False, form_url="", obj=None):
        """Remove botões extras de submit."""
        # Remove botões "Salvar e adicionar outro" e "Salvar e continuar editando"
        context["show_save_and_add_another"] = False
        context["show_save_and_continue"] = False
        return super().render_change_form(request, context, add, change, form_url, obj)

    def _execute_directive(self, request, directive: Directive) -> tuple[bool, str | None]:
        """
        Executa a diretiva usando o handler registrado.

        Returns:
            (ok, error_message)
        """
        handler = registry.get_directive_handler(directive.topic)
        if handler is None:
            return False, _("Nenhum handler registrado para este tópico.")

        now = timezone.now()
        if directive.status not in ("queued", "failed"):
            return False, _("A diretiva não está em fila ou com erro.")
        if directive.available_at and directive.available_at > now:
            return False, _("A diretiva ainda não está disponível para execução.")

        Directive.objects.filter(pk=directive.pk).update(
            status="running",
            attempts=models.F("attempts") + 1,
            started_at=now,
            updated_at=now,
        )
        directive.refresh_from_db()

        try:
            handler.handle(
                message=directive,
                ctx={"actor": getattr(getattr(request, "user", None), "username", None) or "admin"},
            )
        except Exception as exc:  # pragma: no cover - logging side-effect
            logger.exception("Falha ao executar diretiva %s #%s", directive.topic, directive.pk)
            directive.status = "failed"
            directive.last_error = str(exc)
            directive.save(update_fields=["status", "last_error", "updated_at"])
            return False, str(exc)

        # Fallback: se o handler não marcou status, finalize como done.
        directive.refresh_from_db()
        if directive.status == "running":
            directive.status = "done"
            directive.last_error = ""
            directive.save(update_fields=["status", "last_error", "updated_at"])
        return True, None

    @action(description=_("Executar agora"), url_path="execute-now", icon="play_arrow")
    def execute_now_detail_action(self, request, object_id):
        directive = self.get_object(request, object_id)
        if directive is None:
            self.message_user(request, _("Diretiva não encontrada."), level="error")
            return HttpResponseRedirect(reverse("admin:orderman_directive_changelist"))

        ok, err = self._execute_directive(request, directive)
        if ok:
            self.message_user(request, _("Diretiva executada."))
        else:
            self.message_user(request, err or _("Falha ao executar diretiva."), level="error")

        return HttpResponseRedirect(reverse("admin:orderman_directive_change", args=[object_id]))

    @action(
        description=_("Executar ▸"),
        url_path="execute-row",
        icon="play_arrow",
        variant=ActionVariant.SUCCESS,
    )
    def execute_row(self, request, object_id):
        directive = self.get_object(request, object_id)
        if directive is None:
            messages.error(request, _("Diretiva não encontrada."))
            return HttpResponseRedirect(reverse("admin:orderman_directive_changelist"))

        if directive.status not in ("queued", "failed"):
            messages.warning(request, _("Diretiva não está em fila ou com erro."))
            return HttpResponseRedirect(reverse("admin:orderman_directive_changelist"))

        ok, err = self._execute_directive(request, directive)
        if ok:
            messages.success(request, _("Diretiva executada."))
        else:
            messages.error(request, err or _("Falha ao executar diretiva."))

        return HttpResponseRedirect(reverse("admin:orderman_directive_changelist"))

    @admin.action(description=_("Executar agora"))
    def execute_now_action(self, request, queryset):
        ok_count = 0
        skip_count = 0
        fail_count = 0

        for directive in queryset:
            ok, err = self._execute_directive(request, directive)
            if ok:
                ok_count += 1
            else:
                if err and "handler" in str(err).lower():
                    skip_count += 1
                else:
                    fail_count += 1

        if ok_count:
            self.message_user(request, _("Diretivas executadas: %(n)s") % {"n": ok_count})
        if skip_count:
            self.message_user(request, _("Diretivas ignoradas (sem handler): %(n)s") % {"n": skip_count}, level="warning")
        if fail_count:
            self.message_user(request, _("Diretivas com erro: %(n)s") % {"n": fail_count}, level="error")

    # Cores de referência BADGES:
    # - Azul=#5EB1EF (info), Amarelo=#E2A336 (warning), Verde=#5BB98B (success), Vermelho=#EB8E90 (danger), Cinza=secondary
    # - em fila=azul, em execução=amarelo, concluído=verde, com erro=vermelho
    @display(
        description=_("status"),
        label={
            "em fila": "info",
            "em execução": "warning",
            "concluído": "success",
            "falhou": "danger",
        },
    )
    def status_badge(self, obj: Directive) -> str:
        return obj.get_status_display()

    # Banner explicativo antes do formulário (hook do Unfold), como no demo v0.5.2
    change_form_before_template = "orderman/admin/directive_before.html"

    # Form customizado removido - todos os campos são readonly agora
    # Se precisar criar novas diretivas manualmente no futuro, pode adicionar form customizado

    def changelist_view(self, request, extra_context=None):
        # UX: tab padrão = "Em fila" quando não há nenhum filtro explícito.
        if request.method == "GET" and not request.GET:
            return HttpResponseRedirect(f"{request.path}?status__exact=queued")

        # UX: date_hierarchy default = hoje quando o operador não escolheu data.
        if request.method == "GET" and self.date_hierarchy:
            field = str(self.date_hierarchy)
            year_p = f"{field}__year"
            month_p = f"{field}__month"
            day_p = f"{field}__day"
            if not any(p in request.GET for p in (year_p, month_p, day_p)):
                today = timezone.localdate()
                q = request.GET.copy()
                q[year_p] = str(today.year)
                q[month_p] = str(today.month)
                q[day_p] = str(today.day)
                return HttpResponseRedirect(f"{request.path}?{q.urlencode()}")

        return super().changelist_view(request, extra_context=extra_context)


@admin.register(IdempotencyKey)
class IdempotencyKeyAdmin(ModelAdmin):
    list_display = (
        "scope",
        "key",
        "status_badge",
        "response_code",
        "expires_at",
        "created_at",
    )
    list_filter = (("status", ChoicesRadioFilter), "scope")
    search_fields = ("scope", "key")
    ordering = ("-created_at",)
    date_hierarchy = "created_at"
    list_filter_submit = True
    list_fullwidth = True
    compressed_fields = True

    fieldsets = (
        (_("Chave"), {"fields": ("scope", "key", "status"), "classes": ("tab",)}),
        (
            _("Resposta"),
            {"fields": ("response_code", "response_body"), "classes": ("tab",)},
        ),
        (_("Auditoria"), {"fields": ("expires_at", "created_at"), "classes": ("tab",)}),
    )
    readonly_fields = ("scope", "key", "response_code", "response_body", "created_at")

    actions_detail = ["history_detail_action"]

    @action(description=_("Histórico"), url_path="history-action", icon="history")
    def history_detail_action(self, request, object_id):
        return history_action(self, request, object_id)

    @display(
        description=_("status"),
        label={"em andamento": "warning", "concluído": "success", "falhou": "danger"},
    )
    def status_badge(self, obj: IdempotencyKey) -> str:
        return obj.get_status_display()


# =============================================================================
# FULFILLMENT ADMIN
# =============================================================================


class FulfillmentItemInline(admin.TabularInline):
    model = FulfillmentItem
    extra = 0
    readonly_fields = ("order_item", "qty")
    fields = ("order_item", "qty")


@admin.register(Fulfillment)
class FulfillmentAdmin(ModelAdmin):
    list_display = ("id", "order", "status_badge", "carrier", "tracking_code", "created_at")
    list_filter = (("status", ChoicesRadioFilter),)
    search_fields = ("order__ref", "tracking_code", "carrier")
    ordering = ("-created_at",)
    date_hierarchy = "created_at"
    list_filter_submit = True
    list_fullwidth = True
    compressed_fields = True
    inlines = [FulfillmentItemInline]

    fieldsets = (
        (_("Pedido"), {"fields": ("order", "status"), "classes": ("tab",)}),
        (
            _("Rastreio"),
            {"fields": ("carrier", "tracking_code", "tracking_url"), "classes": ("tab",)},
        ),
        (_("Detalhes"), {"fields": ("notes", "meta"), "classes": ("tab",)}),
        (
            _("Datas"),
            {"fields": ("created_at", "dispatched_at", "delivered_at"), "classes": ("tab",)},
        ),
    )
    readonly_fields = ("created_at",)

    actions_detail = ["history_detail_action"]

    @action(description=_("Histórico"), url_path="history-action", icon="history")
    def history_detail_action(self, request, object_id):
        return history_action(self, request, object_id)

    @display(
        description=_("status"),
        label={
            "pendente": "info",
            "em andamento": "warning",
            "enviado": "info",
            "entregue": "success",
            "cancelado": "danger",
        },
    )
    def status_badge(self, obj: Fulfillment) -> str:
        return obj.get_status_display()
