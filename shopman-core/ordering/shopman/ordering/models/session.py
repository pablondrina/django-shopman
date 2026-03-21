from __future__ import annotations

import copy
from decimal import Decimal

from django.core.serializers.json import DjangoJSONEncoder
from django.db import models, transaction
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from shopman.ordering.ids import generate_line_id
from shopman.utils.monetary import monetary_mult


# =============================================================================
# CONVENÇÕES DE VALORES MONETÁRIOS E QUANTIDADES
# =============================================================================
#
# VALORES MONETÁRIOS (preços, totais):
#   - Sempre em CENTAVOS (menor unidade indivisível)
#   - Sufixo "_q" significa "quantum" (ex: unit_price_q, total_q, line_total_q)
#   - Tipo: int ou BigIntegerField
#   - Exemplo: R$ 10,00 = 1000 (centavos)
#
# QUANTIDADES (qty):
#   - Decimal nativo para precisão fracionária
#   - Tipo: Decimal ou DecimalField(max_digits=12, decimal_places=3)
#
# SERIALIZAÇÃO JSON:
#   - DecimalEncoder converte Decimal → string apenas para JSON
#   - Em Python, qty permanece como Decimal nativo
#   - Campos JSONField que podem conter Decimal usam encoder=DecimalEncoder
#
# =============================================================================


class DecimalEncoder(DjangoJSONEncoder):
    """JSON encoder that handles Decimal by converting to string for precision."""

    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        return super().default(obj)


class SessionManager(models.Manager):
    """
    Manager para Session com suporte a criação atômica com items.

    Uso:
        session = Session.objects.create(
            session_key="S-1",
            channel=channel,
            items=[{"sku": "SKU", "qty": 2, "unit_price_q": 1000}],
        )
    """

    use_in_migrations = True

    def create(self, **kwargs):
        items = kwargs.pop("items", None)
        with transaction.atomic():
            session = super().create(**kwargs)
            if items is not None:
                session._items_cache = session._normalize_items(items)
                session._persist_items(session._items_cache)
        return session

    def get_or_create(self, defaults=None, **kwargs):
        defaults = defaults or {}
        items = defaults.pop("items", None)
        with transaction.atomic():
            session, created = super().get_or_create(defaults=defaults, **kwargs)
            if created and items is not None:
                session._items_cache = session._normalize_items(items)
                session._persist_items(session._items_cache)
        return session, created


class Session(models.Model):
    objects = SessionManager()
    """
    Unidade mutável pré-commit (carrinho/comanda).

    Items schema:
    [{"line_id": "L-abc123", "sku": "CROISSANT", "qty": 2, "unit_price_q": 1200, "meta": {}}]

    Data schema (checks, issues):
    {
      "checks": {"stock": {"rev": 12, "at": "...", "result": {...}}},
      "issues": [{"id": "ISS-abc", "source": "stock", "code": "stock.insufficient", "blocking": true, "message": "...", "context": {...}}]
    }
    """

    session_key = models.CharField(_("chave da sessão"), max_length=64)
    channel = models.ForeignKey(
        "ordering.Channel", verbose_name=_("canal de venda"), on_delete=models.PROTECT
    )

    handle_type = models.CharField(_("tipo de identificação"), max_length=32, null=True, blank=True)
    handle_ref = models.CharField(_("identificador"), max_length=64, null=True, blank=True)

    state = models.CharField(
        _("status"),
        max_length=16,
        choices=[("open", _("aberta")), ("committed", _("fechada")), ("abandoned", _("abandonada"))],
        default="open",
        db_index=True,
    )

    pricing_policy = models.CharField(
        _("política de preço"),
        max_length=16,
        choices=[("internal", _("interna")), ("external", _("externa"))],
        default="internal",
    )
    edit_policy = models.CharField(
        _("política de edição"),
        max_length=16,
        choices=[("open", _("aberta")), ("locked", _("bloqueada"))],
        default="open",
    )

    rev = models.IntegerField(_("revisão"), default=0, db_index=True)

    data = models.JSONField(_("dados"), default=dict)
    pricing = models.JSONField(_("precificação"), default=dict, blank=True)
    pricing_trace = models.JSONField(_("trace de precificação"), default=list, blank=True)

    commit_token = models.CharField(_("token de commit"), max_length=64, null=True, blank=True, db_index=True)

    opened_at = models.DateTimeField(_("aberta em"), auto_now_add=True)
    committed_at = models.DateTimeField(_("fechada em"), null=True, blank=True)
    updated_at = models.DateTimeField(_("atualizada em"), auto_now=True)

    class Meta:
        app_label = "ordering"
        verbose_name = _("sessão")
        verbose_name_plural = _("sessões")
        constraints = [
            models.UniqueConstraint(fields=["channel", "session_key"], name="ord_uniq_session_channel_key"),
            models.UniqueConstraint(
                fields=["channel", "handle_type", "handle_ref"],
                condition=Q(state="open") & Q(handle_type__isnull=False) & Q(handle_ref__isnull=False),
                name="ord_uniq_open_session_handle",
            ),
        ]

    def __str__(self) -> str:
        if self.handle_ref:
            if self.handle_type:
                handle_type = (
                    str(self.handle_type)
                    .replace("_", " ")
                    .replace("-", " ")
                    .strip()
                    .title()
                )
                return f"{handle_type}: {self.handle_ref}"
            return str(self.handle_ref)
        return f"{self.channel.ref}:{self.session_key}"

    # ------------------------------------------------------------------ items API

    @property
    def items(self) -> list[dict]:
        if not hasattr(self, "_items_cache"):
            self._items_cache = self._load_items_from_lines()
        return copy.deepcopy(getattr(self, "_items_cache", []))

    @items.setter
    def items(self, value: list[dict]):
        self._items_cache = self._normalize_items(value or [])

    def invalidate_items_cache(self) -> None:
        if hasattr(self, "_items_cache"):
            delattr(self, "_items_cache")

    def refresh_from_db(self, *args, **kwargs):
        super().refresh_from_db(*args, **kwargs)
        self.invalidate_items_cache()

    def save(self, *args, **kwargs):
        items_snapshot = getattr(self, "_items_cache", None)
        super().save(*args, **kwargs)
        if items_snapshot is not None:
            self._persist_items(items_snapshot)

    # ------------------------------------------------------------------ internal

    def _load_items_from_lines(self) -> list[dict]:
        payload: list[dict] = []
        for item in self.session_items.order_by("id"):
            payload.append(item.to_payload())
        return payload

    def _normalize_items(self, items: list[dict]) -> list[dict]:
        normalized: list[dict] = []
        for raw in items:
            line_id = raw.get("line_id") or generate_line_id()
            qty = Decimal(str(raw.get("qty", 0)))
            unit_price_q = int(raw.get("unit_price_q", 0) or 0)
            line_total_q = raw.get("line_total_q")
            if line_total_q is None:
                line_total_q = monetary_mult(qty, unit_price_q)
            normalized.append(
                {
                    "line_id": line_id,
                    "sku": raw.get("sku", ""),
                    "name": raw.get("name", ""),
                    "qty": qty,
                    "unit_price_q": unit_price_q,
                    "line_total_q": int(line_total_q),
                    "meta": raw.get("meta", {}) or {},
                }
            )
        return normalized

    def _persist_items(self, items: list[dict]) -> None:
        existing = {si.line_id: si for si in self.session_items.all()}
        seen: set[str] = set()
        for item in items:
            line_id = item["line_id"]
            seen.add(line_id)
            defaults = self._item_defaults(item)
            session_item = existing.get(line_id)
            if session_item:
                updated_fields: list[str] = []
                for field, value in defaults.items():
                    if getattr(session_item, field) != value:
                        setattr(session_item, field, value)
                        updated_fields.append(field)
                if updated_fields:
                    session_item.save(update_fields=updated_fields)
            else:
                SessionItem.objects.create(session=self, line_id=line_id, **defaults)

        for line_id, session_item in existing.items():
            if line_id not in seen:
                session_item.delete()

        self._items_cache = copy.deepcopy(items)

    def _item_defaults(self, item: dict) -> dict:
        qty = Decimal(str(item.get("qty", 0)))
        unit_price_q = int(item.get("unit_price_q", 0) or 0)
        line_total_q = item.get("line_total_q")
        if line_total_q is None:
            line_total_q = monetary_mult(qty, unit_price_q)
        return {
            "sku": item.get("sku", ""),
            "name": item.get("name", ""),
            "qty": qty,
            "unit_price_q": unit_price_q,
            "line_total_q": int(line_total_q),
            "meta": item.get("meta", {}) or {},
        }


class SessionItem(models.Model):
    """Item de uma sessão."""

    session = models.ForeignKey(
        Session,
        on_delete=models.CASCADE,
        related_name="session_items",
        verbose_name=_("sessão"),
    )
    line_id = models.CharField(_("ID da linha"), max_length=64)
    sku = models.CharField(_("SKU"), max_length=64, blank=True, default="")
    name = models.CharField(_("nome"), max_length=200, blank=True, default="")
    qty = models.DecimalField(_("quantidade"), max_digits=12, decimal_places=3)
    unit_price_q = models.BigIntegerField(_("preço unitário (q)"), default=0)
    line_total_q = models.BigIntegerField(_("total da linha (q)"), default=0)
    meta = models.JSONField(_("metadados"), default=dict, blank=True)
    created_at = models.DateTimeField(_("criado em"), auto_now_add=True)
    updated_at = models.DateTimeField(_("atualizado em"), auto_now=True)

    class Meta:
        app_label = "ordering"
        verbose_name = _("item da sessão")
        verbose_name_plural = _("itens da sessão")
        constraints = [
            models.UniqueConstraint(
                fields=["session", "line_id"],
                name="ord_uniq_session_item_line_id",
            ),
            models.CheckConstraint(
                condition=models.Q(qty__gt=0),
                name="ord_session_item_qty_positive",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.line_id} ({self.sku})"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.session.invalidate_items_cache()

    def delete(self, *args, **kwargs):
        session = self.session
        super().delete(*args, **kwargs)
        session.invalidate_items_cache()

    def to_payload(self) -> dict:
        return {
            "line_id": self.line_id,
            "sku": self.sku,
            "name": self.name,
            "qty": self.qty,
            "unit_price_q": self.unit_price_q,
            "line_total_q": self.line_total_q,
            "meta": self.meta or {},
        }
