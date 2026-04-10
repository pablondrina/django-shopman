"""
Stockman Admin — basic fallback (works without Unfold).

For the Unfold-styled version, add stockman.contrib.admin_unfold' to INSTALLED_APPS.
When the Unfold contrib is loaded, this module does nothing (avoids double registration).

Provides read-only views for production debugging:
- Position: list + edit
- Quant: read-only (sku, position, quantity, held, available)
- Move: read-only audit trail (timestamp, delta, reason)
- Hold: read-only with "release" action
- StockAlert: configurable min stock triggers
"""

import logging

from django.apps import apps
from django.contrib import admin
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)

# Skip registration if the Unfold contrib is installed (it will register its own admins)
if not apps.is_installed('shopman.stockman.contrib.admin_unfold'):
    from shopman.stockman.models import Batch, Hold, HoldStatus, Move, Position, Quant, StockAlert

    # =========================================================================
    # POSITION ADMIN
    # =========================================================================

    @admin.register(Position)
    class PositionAdmin(admin.ModelAdmin):
        """Position admin — editable."""

        list_display = ['ref', 'name', 'kind', 'is_saleable', 'is_default']
        list_filter = ['kind', 'is_saleable']
        search_fields = ['ref', 'name']
        readonly_fields = ['created_at', 'updated_at']

    # =========================================================================
    # QUANT ADMIN (read-only)
    # =========================================================================

    @admin.register(Quant)
    class QuantAdmin(admin.ModelAdmin):
        """Quant admin — read-only. Stock only changes via Stock service."""

        list_display = ['__str__', 'sku', 'position', 'target_date', 'quantity_display',
                        'held_display', 'available_display']
        list_filter = ['position', 'target_date']
        search_fields = ['sku']
        readonly_fields = ['sku', 'position', 'target_date',
                           'batch', '_quantity', 'metadata', 'created_at', 'updated_at']
        date_hierarchy = 'target_date'
        ordering = ['-target_date', 'position']

        def has_add_permission(self, request):
            return False

        def has_change_permission(self, request, obj=None):
            return False

        def has_delete_permission(self, request, obj=None):
            return False

        @admin.display(description=_('Quantidade'))
        def quantity_display(self, obj):
            return obj.quantity

        @admin.display(description=_('Reservado'))
        def held_display(self, obj):
            return obj.held

        @admin.display(description=_('Disponível'))
        def available_display(self, obj):
            return obj.available

    # =========================================================================
    # MOVE ADMIN (read-only audit trail)
    # =========================================================================

    @admin.register(Move)
    class MoveAdmin(admin.ModelAdmin):
        """Move admin — read-only. Immutable audit trail."""

        list_display = ['timestamp', 'quant', 'delta', 'reason', 'user']
        list_filter = ['timestamp', 'user']
        search_fields = ['reason']
        ordering = ['-timestamp']
        readonly_fields = ['quant', 'delta', 'reason', 'metadata', 'timestamp', 'user']
        date_hierarchy = 'timestamp'

        def has_add_permission(self, request):
            return False

        def has_change_permission(self, request, obj=None):
            return False

        def has_delete_permission(self, request, obj=None):
            return False

    # =========================================================================
    # HOLD ADMIN (read-only with release action)
    # =========================================================================

    @admin.register(Hold)
    class HoldAdmin(admin.ModelAdmin):
        """Hold admin — read-only with release action."""

        list_display = ['id', 'sku', 'quantity', 'target_date',
                        'status', 'is_demand_display', 'expires_at']
        list_filter = ['status', 'target_date']
        search_fields = ['sku']
        readonly_fields = ['sku', 'quant', 'target_date',
                           'quantity', 'status', 'expires_at',
                           'metadata', 'created_at', 'resolved_at']
        actions = ['release_holds']

        def has_add_permission(self, request):
            return False

        def has_change_permission(self, request, obj=None):
            return False

        def has_delete_permission(self, request, obj=None):
            return False

        @admin.display(description=_('Demanda?'), boolean=True)
        def is_demand_display(self, obj):
            return obj.is_demand

        @admin.action(description=_('Liberar holds selecionados'))
        def release_holds(self, request, queryset):
            from shopman.stockman import stock

            count = 0
            for hold in queryset.filter(status__in=[HoldStatus.PENDING, HoldStatus.CONFIRMED]):
                try:
                    stock.release(hold.hold_id, reason='Liberado via admin')
                    count += 1
                except Exception as exc:
                    logger.warning("release_holds: failed to release %s: %s", hold.hold_id, exc)

            self.message_user(request, _('{count} hold(s) liberado(s).').format(count=count))

    # =========================================================================
    # STOCK ALERT ADMIN
    # =========================================================================

    @admin.register(StockAlert)
    class StockAlertAdmin(admin.ModelAdmin):
        """StockAlert admin — configurable min stock triggers."""

        list_display = ['__str__', 'sku', 'min_quantity', 'position', 'is_active', 'last_triggered_at']
        list_filter = ['is_active', 'position']
        search_fields = ['sku']
        readonly_fields = ['last_triggered_at', 'created_at', 'updated_at']

    # =========================================================================
    # BATCH ADMIN
    # =========================================================================

    @admin.register(Batch)
    class BatchAdmin(admin.ModelAdmin):
        """Batch admin — lot traceability."""

        list_display = ['ref', 'sku', 'production_date', 'expiry_date',
                        'supplier', 'is_expired_display']
        list_filter = ['expiry_date', 'production_date']
        search_fields = ['ref', 'sku', 'supplier']
        readonly_fields = ['created_at']

        @admin.display(description=_('Expirado?'), boolean=True)
        def is_expired_display(self, obj):
            return obj.is_expired
