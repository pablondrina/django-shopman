"""
Stockman Admin with Unfold theme.

This module provides Unfold-styled admin classes for Stockman models.
To use, add 'stocking.contrib.admin_unfold' to INSTALLED_APPS after 'stockman'.

The admins will automatically register the Unfold versions.
"""

import logging

from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from unfold.decorators import action, display
from unfold.enums import ActionVariant

logger = logging.getLogger(__name__)

from unfold.contrib.filters.admin.datetime_filters import RangeDateFilter

from shopman.utils.contrib.admin_unfold.badges import unfold_badge, unfold_badge_numeric
from shopman.utils.contrib.admin_unfold.base import BaseModelAdmin
from shopman.utils.formatting import format_quantity
from shopman.stocking.models import Batch, Position, Quant, Move, Hold, HoldStatus, StockAlert


# =============================================================================
# CUSTOM FILTERS
# =============================================================================


class BelowMinimumFilter(admin.SimpleListFilter):
    """Custom filter: show only quants below their configured stock alert minimum."""
    title = _("Abaixo do mínimo")
    parameter_name = "below_minimum"

    def lookups(self, request, model_admin):
        return [("1", _("Sim"))]

    def queryset(self, request, queryset):
        if self.value() != "1":
            return queryset
        from django.db.models import Exists, OuterRef
        # Subquery: exists an active alert where quant's sku matches and
        # (alert has no position OR alert position matches quant position)
        # and quant's available < alert min_quantity.
        # Since available = _quantity - held (computed), we approximate with _quantity.
        # For exact results we collect IDs in a single pass.
        alerts = StockAlert.objects.filter(is_active=True).select_related("position")
        if not alerts.exists():
            return queryset.none()
        below_pks = set()
        # Build a dict: (sku, position_id|None) -> min_quantity for all active alerts
        alert_map: dict[tuple[str, int | None], 'Decimal'] = {}
        for alert in alerts:
            key = (alert.sku, alert.position_id)
            alert_map[key] = alert.min_quantity
        # Single query to get all relevant quants
        alert_skus = {k[0] for k in alert_map}
        for q in queryset.filter(sku__in=alert_skus).select_related("position"):
            # Check position-specific alert first, then global alert
            for key in [(q.sku, q.position_id), (q.sku, None)]:
                if key in alert_map and q.available < alert_map[key]:
                    below_pks.add(q.pk)
                    break
        return queryset.filter(pk__in=below_pks) if below_pks else queryset.none()


class HasStockFilter(admin.SimpleListFilter):
    """Custom filter: exclude quants with zero quantity."""
    title = _("Apenas com estoque")
    parameter_name = "has_stock"

    def lookups(self, request, model_admin):
        return [("1", _("Sim"))]

    def queryset(self, request, queryset):
        if self.value() == "1":
            return queryset.exclude(_quantity=0)
        return queryset


# =============================================================================
# HELPERS
# =============================================================================


def _format_datetime(dt):
    """Format datetime as DD/MM/AA . HH:MM."""
    if dt:
        return dt.strftime('%d/%m/%y · %H:%M')
    return '-'


def _format_date(d):
    """Format date as DD/MM/AA."""
    if d:
        return d.strftime('%d/%m/%y')
    return '-'


# =============================================================================
# POSITION ADMIN
# =============================================================================


@admin.register(Position)
class PositionAdmin(BaseModelAdmin):
    """Admin for Position model."""

    list_display = ['ref', 'name', 'kind', 'is_saleable']
    list_filter = ['kind', 'is_saleable']
    search_fields = ['ref', 'name']
    readonly_fields = ['created_at', 'updated_at']

    # Unfold options
    compressed_fields = True
    warn_unsaved_form = True


# =============================================================================
# SALDO (QUANT) ADMIN
# =============================================================================


@admin.register(Quant)
class QuantAdmin(BaseModelAdmin):
    """Admin for Saldo/Quant model (read-only).

    Saldos should only be modified via stock.add(), stock.remove() etc.
    to maintain audit trail via Movimentação records.
    """

    list_display = ['sku', 'position', 'target_date_display', 'quantity_display', 'held_display', 'available_display', 'batch_display', 'expiry_display']
    list_filter = ['position', 'target_date', BelowMinimumFilter, HasStockFilter]
    search_fields = ['sku', 'batch']
    readonly_fields = ['sku', 'position', 'target_date', '_quantity', 'created_at', 'updated_at']
    date_hierarchy = 'target_date'
    ordering = ['-target_date', 'position']

    # Unfold options
    compressed_fields = True

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @display(description=_('Data'))
    def target_date_display(self, obj):
        """Display target_date in DD/MM/AA format."""
        return _format_date(obj.target_date)

    @display(description=_('Quantidade'))
    def quantity_display(self, obj):
        return format_quantity(obj.quantity)

    @display(description=_('Reservado'))
    def held_display(self, obj):
        """Display reserved quantity with Unfold badge."""
        held = obj.held
        formatted = format_quantity(held)
        if held > 0:
            return unfold_badge_numeric(formatted, 'yellow')
        else:
            return unfold_badge_numeric(formatted, 'base')

    @display(description=_('Disponivel'))
    def available_display(self, obj):
        """Display available quantity with Unfold badge."""
        available = obj.available
        formatted = format_quantity(available)
        if available > 0:
            return unfold_badge_numeric(formatted, 'green')
        elif available == 0:
            return unfold_badge_numeric(formatted, 'base')
        else:
            return unfold_badge_numeric(formatted, 'red')

    @display(description=_('Lote'))
    def batch_display(self, obj):
        """Display batch reference."""
        return obj.batch or '-'

    @display(description=_('Validade'))
    def expiry_display(self, obj):
        """Display expiry date from Batch model, with color badge."""
        if not obj.batch:
            return '-'
        try:
            batch_obj = Batch.objects.filter(ref=obj.batch).only('expiry_date').first()
            if not batch_obj or not batch_obj.expiry_date:
                return '-'
            formatted = _format_date(batch_obj.expiry_date)
            if batch_obj.is_expired:
                return unfold_badge(formatted, 'red')
            return formatted
        except Exception:
            return '-'


# =============================================================================
# MOVIMENTAÇÃO (MOVE) ADMIN
# =============================================================================


@admin.register(Move)
class MoveAdmin(BaseModelAdmin):
    """Admin for Movimentação/Move model (read-only)."""

    list_display = ['timestamp_display', 'quant_display', 'delta_display', 'reason', 'user']
    list_filter = [('timestamp', RangeDateFilter), 'user']
    list_filter_submit = True
    search_fields = ['reason']
    readonly_fields = ['quant', 'delta', 'reason', 'metadata', 'timestamp', 'user']
    ordering = ['-timestamp']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    # Unfold options
    compressed_fields = True

    @display(description=_('Data e Hora'))
    def timestamp_display(self, obj):
        """Display timestamp in DD/MM/AA . HH:MM format."""
        return _format_datetime(obj.timestamp)

    @display(description=_('Saldo'))
    def quant_display(self, obj):
        return obj.quant.sku if obj.quant else '?'

    @display(description=_('Variacao'))
    def delta_display(self, obj):
        """Display delta with Unfold badge."""
        formatted = format_quantity(abs(obj.delta))
        if obj.delta > 0:
            return unfold_badge_numeric(f'+{formatted}', 'green')
        else:
            return unfold_badge_numeric(f'-{formatted}', 'red')


# =============================================================================
# RESERVA (HOLD) ADMIN
# =============================================================================


@admin.register(Hold)
class HoldAdmin(BaseModelAdmin):
    """Admin for Reserva/Hold model (read-only).

    Reservas should only be created via stock.reserve() and released via stock.release()
    to maintain proper inventory accounting. Admin actions allow releasing holds.
    """

    list_display = ['id', 'sku', 'quantity', 'target_date_display', 'status_display', 'is_demand_display', 'expires_at_display']
    list_filter = ['status', 'target_date']
    search_fields = ['sku']
    readonly_fields = ['hold_id', 'sku', 'quant', 'target_date', 'quantity', 'status', 'is_demand', 'expires_at', 'metadata', 'created_at', 'resolved_at']
    actions = ['release_holds']
    actions_row = ['release_hold_row']

    # Unfold options
    compressed_fields = True

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @display(description=_('Status'))
    def status_display(self, obj):
        """Display status with Unfold badge."""
        status_map = {
            HoldStatus.PENDING: ('PENDENTE', 'base'),
            HoldStatus.CONFIRMED: ('CONFIRMADO', 'blue'),
            HoldStatus.FULFILLED: ('ATENDIDO', 'green'),
            HoldStatus.RELEASED: ('LIBERADO', 'base'),
        }
        label, color = status_map.get(obj.status, (obj.get_status_display().upper(), 'base'))
        return unfold_badge(label, color)

    @display(description=_('Data'))
    def target_date_display(self, obj):
        """Display target_date in DD/MM/AA format."""
        return _format_date(obj.target_date)

    @display(description=_('Expira em'))
    def expires_at_display(self, obj):
        """Display expires_at in DD/MM/AA . HH:MM format."""
        return _format_datetime(obj.expires_at)

    @display(description=_('Demanda?'), boolean=True)
    def is_demand_display(self, obj):
        return obj.is_demand

    @admin.action(description=_('Liberar holds selecionados'))
    def release_holds(self, request, queryset):
        from shopman.stocking import stock

        count = 0
        for hold in queryset.filter(status__in=[HoldStatus.PENDING, HoldStatus.CONFIRMED]):
            try:
                stock.release(hold.hold_id, reason='Liberado via admin')
                count += 1
            except (ValueError, LookupError) as exc:
                logger.warning("release_holds: failed to release %s: %s", hold.hold_id, exc)

        self.message_user(request, _('{count} hold(s) liberado(s).').format(count=count))

    @action(
        description=_("Liberar"),
        url_path="release-hold",
        icon="lock_open",
        variant=ActionVariant.WARNING,
    )
    def release_hold_row(self, request, object_id):
        hold = self.get_object(request, object_id)
        if hold is None:
            messages.error(request, _("Hold não encontrado."))
            return HttpResponseRedirect(reverse("admin:stocking_hold_changelist"))

        if hold.status not in (HoldStatus.PENDING, HoldStatus.CONFIRMED):
            messages.warning(request, _("Este hold não está ativo."))
            return HttpResponseRedirect(reverse("admin:stocking_hold_changelist"))

        from shopman.stocking import stock

        try:
            stock.release(hold.hold_id, reason='Liberado via admin')
            messages.success(request, _("Hold liberado."))
        except (ValueError, LookupError) as exc:
            messages.error(request, str(exc))

        return HttpResponseRedirect(reverse("admin:stocking_hold_changelist"))


# =============================================================================
# STOCK ALERT ADMIN
# =============================================================================


@admin.register(StockAlert)
class StockAlertAdmin(BaseModelAdmin):
    """Admin for StockAlert model."""

    list_display = ['__str__', 'sku', 'min_quantity', 'position', 'is_active_display', 'last_triggered_at_display']
    list_filter = ['is_active', 'position']
    search_fields = ['sku']
    readonly_fields = ['last_triggered_at', 'created_at', 'updated_at']

    compressed_fields = True
    warn_unsaved_form = True

    @display(description=_('Ativo'))
    def is_active_display(self, obj):
        if obj.is_active:
            return unfold_badge('ATIVO', 'green')
        return unfold_badge('INATIVO', 'base')

    @display(description=_('Último Disparo'))
    def last_triggered_at_display(self, obj):
        return _format_datetime(obj.last_triggered_at)


# =============================================================================
# BATCH (LOT) ADMIN
# =============================================================================


@admin.register(Batch)
class BatchAdmin(BaseModelAdmin):
    """Admin for Batch/Lot model."""

    list_display = ['ref', 'sku', 'production_date_display',
                    'expiry_date_display', 'supplier', 'is_expired_display']
    list_filter = ['expiry_date', 'production_date']
    search_fields = ['ref', 'sku', 'supplier']
    readonly_fields = ['created_at']

    compressed_fields = True
    warn_unsaved_form = True

    @display(description=_('Produção'))
    def production_date_display(self, obj):
        return _format_date(obj.production_date)

    @display(description=_('Validade'))
    def expiry_date_display(self, obj):
        return _format_date(obj.expiry_date)

    @display(description=_('Expirado'))
    def is_expired_display(self, obj):
        if obj.is_expired:
            return unfold_badge('EXPIRADO', 'red')
        return unfold_badge('VÁLIDO', 'green')
