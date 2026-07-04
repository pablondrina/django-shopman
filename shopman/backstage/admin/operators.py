"""Admin de credenciais de operador (PIN) — reset e desbloqueio pelo gerente.

Gestão de operador é canônica no Admin/Unfold. A credencial (PIN) é genérica
(doorman); a POLÍTICA de operador (PIN temporário + trocar-no-1º-uso) vive no
backstage, que pode importar doorman. "Resetar PIN" gera um temporário mostrado
UMA vez ao gerente e marca ``must_change`` — o operador é forçado a trocá-lo no
próximo uso. O PIN nunca é revelado (só o digest é guardado); o temporário
aparece uma vez na mensagem para o gerente repassar.

Gateado por ``backstage.manage_operators``. Provisionar o PRIMEIRO PIN de um
operador novo continua pela CLI (``set_operator_pin``) ou pelo próprio reset.
"""

from __future__ import annotations

from django.contrib import admin, messages
from shopman.doorman.models import PinCredential, PinCredentialError
from shopman.utils import unfold_badge
from unfold.admin import ModelAdmin

from shopman.backstage.services.operator import reset_operator_pin

MANAGE_OPERATORS = "backstage.manage_operators"


@admin.register(PinCredential)
class PinCredentialAdmin(ModelAdmin):
    list_display = ("operator_display", "state_display", "must_change_display", "last_verified_at", "updated_at")
    search_fields = ("user__username", "user__first_name", "user__last_name")
    readonly_fields = (
        "user", "pin_hash", "badge_hash", "attempts", "max_attempts",
        "locked_until", "must_change", "last_verified_at", "created_at", "updated_at",
    )
    ordering = ["user__first_name", "user__username"]
    actions = ["reset_pin", "unlock_pin"]
    compressed_fields = True

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user")

    @admin.display(description="Operador")
    def operator_display(self, obj):
        return obj.user.get_full_name().strip() or obj.user.get_username()

    @admin.display(description="Situação")
    def state_display(self, obj):
        if obj.is_locked:
            return unfold_badge("bloqueado", "red")
        return unfold_badge("ativo", "green")

    @admin.display(description="Trocar no 1º uso")
    def must_change_display(self, obj):
        return unfold_badge("sim", "yellow") if obj.must_change else unfold_badge("não", "base")

    @admin.action(description="Resetar PIN (gera temporário)")
    def reset_pin(self, request, queryset):
        temps: list[str] = []
        for cred in queryset.select_related("user"):
            try:
                temp = reset_operator_pin(cred.user)
            except PinCredentialError as exc:
                self.message_user(request, f"{cred.user.get_username()}: {exc}", level=messages.ERROR)
                continue
            temps.append(f"{cred.user.get_username()}: {temp}")
        if temps:
            self.message_user(
                request,
                "PIN temporário (anote e informe ao operador — não será mostrado de novo): "
                + " · ".join(temps),
                level=messages.WARNING,
            )

    @admin.action(description="Desbloquear PIN")
    def unlock_pin(self, request, queryset):
        count = 0
        for cred in queryset:
            cred.unlock()
            count += 1
        self.message_user(request, f"{count} credencial(is) desbloqueada(s).")

    def has_add_permission(self, request):
        # Sem hash à mão: o primeiro PIN vem do reset (temporário) ou da CLI.
        return False

    def has_change_permission(self, request, obj=None):
        return request.user.has_perm(MANAGE_OPERATORS)

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm(MANAGE_OPERATORS)

    def has_module_permission(self, request):
        return request.user.has_perm(MANAGE_OPERATORS)

    def has_delete_permission(self, request, obj=None):
        return request.user.has_perm(MANAGE_OPERATORS)
