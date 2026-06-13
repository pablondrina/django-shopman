"""Shop admin — singleton with branding, colors, typography."""

from __future__ import annotations

import json
import logging
from datetime import date, time
from decimal import Decimal

from django import forms
from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from unfold.admin import ModelAdmin
from unfold.widgets import (
    UnfoldAdminColorInputWidget,
    UnfoldAdminDateWidget,
    UnfoldAdminDecimalFieldWidget,
    UnfoldAdminIntegerFieldWidget,
    UnfoldAdminSelectWidget,
    UnfoldAdminTextInputWidget,
    UnfoldAdminTimeWidget,
)

from shopman.shop import dynamic_collections
from shopman.shop.admin.widgets import FontPreviewWidget
from shopman.shop.colors import oklch_to_hex
from shopman.shop.models import NotificationTemplate, Shop

logger = logging.getLogger(__name__)

OPENING_HOUR_DAYS = (
    ("monday", "Segunda"),
    ("tuesday", "Terça"),
    ("wednesday", "Quarta"),
    ("thursday", "Quinta"),
    ("friday", "Sexta"),
    ("saturday", "Sábado"),
    ("sunday", "Domingo"),
)

OPENING_STATUS_CHOICES = (
    ("open", "Aberto"),
    ("closed", "Fechado"),
)

NOTIFICATION_BACKEND_CHOICES = (
    ("console", "Console"),
    ("manychat", "Manychat"),
    ("email", "E-mail"),
    ("sms", "SMS"),
    ("webhook", "Webhook"),
    ("none", "Nenhum"),
)

DEFAULTS_DYNAMIC_COLLECTION_ROWS = 5
DEFAULTS_PICKUP_SLOT_ROWS = 5
DEFAULTS_CLOSED_DATE_ROWS = 8


def _opening_field(day: str, suffix: str) -> str:
    return f"opening_hours_{day}_{suffix}"


def _defaults_dynamic_collection_field(index: int) -> str:
    return f"defaults_dynamic_collection_{index}"


def _defaults_pickup_field(index: int, suffix: str) -> str:
    return f"defaults_pickup_slot_{index}_{suffix}"


def _defaults_closed_date_field(index: int, suffix: str) -> str:
    return f"defaults_closed_date_{index}_{suffix}"


def _dynamic_collection_choices() -> tuple[tuple[str, str], ...]:
    choices = []
    for ref in dynamic_collections.all_refs():
        resolver = dynamic_collections.get(ref)
        label = resolver.meta.label if resolver else ref
        choices.append((ref, label))
    return tuple(choices)


def _format_admin_time(value) -> str:
    if isinstance(value, time):
        return value.strftime("%H:%M")
    raw = str(value or "").strip()
    if not raw:
        return ""
    return raw[:5]


def _format_admin_date(value) -> str:
    if isinstance(value, date):
        return value.isoformat()
    raw = str(value or "").strip()
    return raw[:10] if raw else ""


def _shop_defaults(instance: Shop) -> dict:
    defaults = getattr(instance, "defaults", None) or {}
    return defaults if isinstance(defaults, dict) else {}


def _q_to_reais(value_q) -> Decimal | None:
    """Cents → Reais for the admin field initial (``0``/empty → blank)."""
    try:
        cents = int(value_q)
    except (TypeError, ValueError):
        return None
    return (Decimal(cents) / 100) if cents else None


def _reais_to_q(value) -> int:
    """Reais → cents for persistence (``None``/blank → ``0`` = policy off)."""
    if value is None:
        return 0
    return int((Decimal(value) * 100).to_integral_value())


# Shop.defaults["rules"] policies edited as typed Reais fields → stored as cents.
DEFAULTS_RULE_Q_FIELDS = (
    ("defaults_rules_minimum_order_q", "minimum_order_q"),
    ("defaults_rules_delivery_minimum_q", "delivery_minimum_q"),
    ("defaults_rules_free_delivery_above_q", "free_delivery_above_q"),
)


def _defaults_form_fields() -> dict[str, forms.Field]:
    fields: dict[str, forms.Field] = {
        "defaults_notifications_backend": forms.ChoiceField(
            label="Canal padrão de notificações",
            required=False,
            choices=NOTIFICATION_BACKEND_CHOICES,
            widget=UnfoldAdminSelectWidget,
        ),
        "defaults_max_preorder_days": forms.IntegerField(
            label="Máximo de dias para encomenda",
            required=False,
            min_value=0,
            max_value=365,
            widget=UnfoldAdminIntegerFieldWidget,
        ),
        "defaults_rules_minimum_order_q": forms.DecimalField(
            label="Pedido mínimo geral (R$)",
            required=False,
            min_value=Decimal("0"),
            max_digits=8,
            decimal_places=2,
            widget=UnfoldAdminDecimalFieldWidget,
            help_text="Mínimo para finalizar qualquer pedido. 0 ou vazio = sem mínimo.",
        ),
        "defaults_rules_delivery_minimum_q": forms.DecimalField(
            label="Pedido mínimo para entrega (R$)",
            required=False,
            min_value=Decimal("0"),
            max_digits=8,
            decimal_places=2,
            widget=UnfoldAdminDecimalFieldWidget,
            help_text="Mínimo só para entrega (retirada nunca tem mínimo). 0 ou vazio = sem mínimo.",
        ),
        "defaults_rules_free_delivery_above_q": forms.DecimalField(
            label="Frete grátis acima de (R$)",
            required=False,
            min_value=Decimal("0"),
            max_digits=8,
            decimal_places=2,
            widget=UnfoldAdminDecimalFieldWidget,
            help_text="Taxa de entrega zera a partir deste valor. 0 ou vazio = desligado.",
        ),
        "defaults_pickup_rounding_minutes": forms.IntegerField(
            label="Arredondamento dos horários",
            required=False,
            min_value=1,
            max_value=240,
            widget=UnfoldAdminIntegerFieldWidget,
            help_text="Em minutos. Ex.: 30 gera janelas arredondadas a cada meia hora.",
        ),
        "defaults_pickup_history_days": forms.IntegerField(
            label="Histórico usado para sugestão",
            required=False,
            min_value=0,
            max_value=365,
            widget=UnfoldAdminIntegerFieldWidget,
        ),
        "defaults_pickup_fallback_slot": forms.CharField(
            label="Slot fallback",
            required=False,
            widget=UnfoldAdminTextInputWidget,
            help_text="Ref de um dos slots abaixo. Ex.: slot-09.",
        ),
        "defaults_season_hot_months": forms.CharField(
            label="Meses quentes",
            required=False,
            widget=UnfoldAdminTextInputWidget,
            help_text="Números de 1 a 12 separados por vírgula.",
        ),
        "defaults_season_mild_months": forms.CharField(
            label="Meses amenos",
            required=False,
            widget=UnfoldAdminTextInputWidget,
            help_text="Números de 1 a 12 separados por vírgula.",
        ),
        "defaults_season_cold_months": forms.CharField(
            label="Meses frios",
            required=False,
            widget=UnfoldAdminTextInputWidget,
            help_text="Números de 1 a 12 separados por vírgula.",
        ),
        "defaults_high_demand_multiplier": forms.DecimalField(
            label="Multiplicador de alta demanda",
            required=False,
            min_value=Decimal("0"),
            max_digits=5,
            decimal_places=2,
            widget=UnfoldAdminDecimalFieldWidget,
        ),
        "defaults_safety_stock_percent": forms.DecimalField(
            label="Estoque de segurança",
            required=False,
            min_value=Decimal("0"),
            max_value=Decimal("1"),
            max_digits=4,
            decimal_places=2,
            widget=UnfoldAdminDecimalFieldWidget,
            help_text="Percentual em decimal. Ex.: 0,20 para 20%.",
        ),
    }
    for index in range(1, DEFAULTS_DYNAMIC_COLLECTION_ROWS + 1):
        fields[_defaults_dynamic_collection_field(index)] = forms.ChoiceField(
            label=f"Coleção dinâmica {index}",
            required=False,
            choices=(("", "—"),) + _dynamic_collection_choices(),
            widget=UnfoldAdminSelectWidget,
            help_text="A posição define a ordem no cardápio." if index == 1 else "",
        )
    for index in range(1, DEFAULTS_PICKUP_SLOT_ROWS + 1):
        fields[_defaults_pickup_field(index, "ref")] = forms.CharField(
            label=f"Slot {index} ref",
            required=False,
            widget=UnfoldAdminTextInputWidget,
        )
        fields[_defaults_pickup_field(index, "label")] = forms.CharField(
            label=f"Slot {index} rótulo",
            required=False,
            widget=UnfoldAdminTextInputWidget,
        )
        fields[_defaults_pickup_field(index, "starts_at")] = forms.TimeField(
            label=f"Slot {index} início",
            required=False,
            input_formats=["%H:%M"],
            widget=UnfoldAdminTimeWidget(format="%H:%M"),
        )
    for index in range(1, DEFAULTS_CLOSED_DATE_ROWS + 1):
        fields[_defaults_closed_date_field(index, "date")] = forms.DateField(
            label=f"Feriado {index} data",
            required=False,
            input_formats=["%Y-%m-%d"],
            widget=UnfoldAdminDateWidget(format="%Y-%m-%d"),
        )
        fields[_defaults_closed_date_field(index, "label")] = forms.CharField(
            label=f"Feriado {index} rótulo",
            required=False,
            widget=UnfoldAdminTextInputWidget,
        )
    return fields


def _parse_months(value: str, label: str) -> list[int]:
    months: list[int] = []
    for chunk in str(value or "").replace(";", ",").split(","):
        raw = chunk.strip()
        if not raw:
            continue
        try:
            month = int(raw)
        except ValueError as exc:
            raise forms.ValidationError(f"{label}: use apenas números de 1 a 12.") from exc
        if month < 1 or month > 12:
            raise forms.ValidationError(f"{label}: {month} não é um mês válido.")
        if month not in months:
            months.append(month)
    return months


def _months_to_text(months) -> str:
    if not isinstance(months, (list, tuple)):
        return ""
    return ", ".join(str(month) for month in months)


def _defaults_dynamic_collection_admin_rows() -> tuple[tuple[str, ...], ...]:
    return (
        tuple(
            _defaults_dynamic_collection_field(index)
            for index in range(1, min(DEFAULTS_DYNAMIC_COLLECTION_ROWS, 3) + 1)
        ),
        tuple(
            _defaults_dynamic_collection_field(index)
            for index in range(4, DEFAULTS_DYNAMIC_COLLECTION_ROWS + 1)
        ),
    )


def _defaults_pickup_admin_rows() -> tuple[tuple[str, str, str], ...]:
    return tuple(
        (
            _defaults_pickup_field(index, "ref"),
            _defaults_pickup_field(index, "label"),
            _defaults_pickup_field(index, "starts_at"),
        )
        for index in range(1, DEFAULTS_PICKUP_SLOT_ROWS + 1)
    )


def _defaults_closed_date_admin_rows() -> tuple[tuple[str, str], ...]:
    return tuple(
        (
            _defaults_closed_date_field(index, "date"),
            _defaults_closed_date_field(index, "label"),
        )
        for index in range(1, DEFAULTS_CLOSED_DATE_ROWS + 1)
    )


class ShopForm(forms.ModelForm):
    opening_hours_monday_status = forms.ChoiceField(
        label="Segunda",
        choices=OPENING_STATUS_CHOICES,
        widget=UnfoldAdminSelectWidget,
    )
    opening_hours_monday_open = forms.TimeField(
        label="Abre",
        required=False,
        input_formats=["%H:%M"],
        widget=UnfoldAdminTimeWidget(format="%H:%M"),
    )
    opening_hours_monday_close = forms.TimeField(
        label="Fecha",
        required=False,
        input_formats=["%H:%M"],
        widget=UnfoldAdminTimeWidget(format="%H:%M"),
    )
    opening_hours_tuesday_status = forms.ChoiceField(
        label="Terça",
        choices=OPENING_STATUS_CHOICES,
        widget=UnfoldAdminSelectWidget,
    )
    opening_hours_tuesday_open = forms.TimeField(
        label="Abre",
        required=False,
        input_formats=["%H:%M"],
        widget=UnfoldAdminTimeWidget(format="%H:%M"),
    )
    opening_hours_tuesday_close = forms.TimeField(
        label="Fecha",
        required=False,
        input_formats=["%H:%M"],
        widget=UnfoldAdminTimeWidget(format="%H:%M"),
    )
    opening_hours_wednesday_status = forms.ChoiceField(
        label="Quarta",
        choices=OPENING_STATUS_CHOICES,
        widget=UnfoldAdminSelectWidget,
    )
    opening_hours_wednesday_open = forms.TimeField(
        label="Abre",
        required=False,
        input_formats=["%H:%M"],
        widget=UnfoldAdminTimeWidget(format="%H:%M"),
    )
    opening_hours_wednesday_close = forms.TimeField(
        label="Fecha",
        required=False,
        input_formats=["%H:%M"],
        widget=UnfoldAdminTimeWidget(format="%H:%M"),
    )
    opening_hours_thursday_status = forms.ChoiceField(
        label="Quinta",
        choices=OPENING_STATUS_CHOICES,
        widget=UnfoldAdminSelectWidget,
    )
    opening_hours_thursday_open = forms.TimeField(
        label="Abre",
        required=False,
        input_formats=["%H:%M"],
        widget=UnfoldAdminTimeWidget(format="%H:%M"),
    )
    opening_hours_thursday_close = forms.TimeField(
        label="Fecha",
        required=False,
        input_formats=["%H:%M"],
        widget=UnfoldAdminTimeWidget(format="%H:%M"),
    )
    opening_hours_friday_status = forms.ChoiceField(
        label="Sexta",
        choices=OPENING_STATUS_CHOICES,
        widget=UnfoldAdminSelectWidget,
    )
    opening_hours_friday_open = forms.TimeField(
        label="Abre",
        required=False,
        input_formats=["%H:%M"],
        widget=UnfoldAdminTimeWidget(format="%H:%M"),
    )
    opening_hours_friday_close = forms.TimeField(
        label="Fecha",
        required=False,
        input_formats=["%H:%M"],
        widget=UnfoldAdminTimeWidget(format="%H:%M"),
    )
    opening_hours_saturday_status = forms.ChoiceField(
        label="Sábado",
        choices=OPENING_STATUS_CHOICES,
        widget=UnfoldAdminSelectWidget,
    )
    opening_hours_saturday_open = forms.TimeField(
        label="Abre",
        required=False,
        input_formats=["%H:%M"],
        widget=UnfoldAdminTimeWidget(format="%H:%M"),
    )
    opening_hours_saturday_close = forms.TimeField(
        label="Fecha",
        required=False,
        input_formats=["%H:%M"],
        widget=UnfoldAdminTimeWidget(format="%H:%M"),
    )
    opening_hours_sunday_status = forms.ChoiceField(
        label="Domingo",
        choices=OPENING_STATUS_CHOICES,
        widget=UnfoldAdminSelectWidget,
    )
    opening_hours_sunday_open = forms.TimeField(
        label="Abre",
        required=False,
        input_formats=["%H:%M"],
        widget=UnfoldAdminTimeWidget(format="%H:%M"),
    )
    opening_hours_sunday_close = forms.TimeField(
        label="Fecha",
        required=False,
        input_formats=["%H:%M"],
        widget=UnfoldAdminTimeWidget(format="%H:%M"),
    )

    locals().update(_defaults_form_fields())

    class Meta:
        model = Shop
        fields = "__all__"
        widgets = {
            "primary_color": UnfoldAdminColorInputWidget,
            "secondary_color": UnfoldAdminColorInputWidget,
            "accent_color": UnfoldAdminColorInputWidget,
            "neutral_color": UnfoldAdminColorInputWidget,
            "neutral_dark_color": UnfoldAdminColorInputWidget,
            "heading_font": FontPreviewWidget(sample_text="Aa Bb Cc \u2014 O sabor que encanta"),
            "body_font": FontPreviewWidget(sample_text="O p\u00e3o fresco de cada dia, feito com amor e tradi\u00e7\u00e3o."),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields.pop("opening_hours", None)
        self.fields.pop("defaults", None)

        opening_hours = getattr(self.instance, "opening_hours", None) or {}
        if not isinstance(opening_hours, dict):
            opening_hours = {}

        for day, _label in OPENING_HOUR_DAYS:
            entry = opening_hours.get(day) if isinstance(opening_hours.get(day), dict) else {}
            opens_at = _format_admin_time(entry.get("open"))
            closes_at = _format_admin_time(entry.get("close"))
            self.fields[_opening_field(day, "status")].initial = "open" if opens_at and closes_at else "closed"
            self.fields[_opening_field(day, "open")].initial = opens_at
            self.fields[_opening_field(day, "close")].initial = closes_at

        self._set_defaults_initial(_shop_defaults(self.instance))

    def _set_defaults_initial(self, defaults: dict) -> None:
        menu = defaults.get("menu") if isinstance(defaults.get("menu"), dict) else {}
        notifications = defaults.get("notifications") if isinstance(defaults.get("notifications"), dict) else {}
        pickup_config = (
            defaults.get("pickup_slot_config")
            if isinstance(defaults.get("pickup_slot_config"), dict)
            else {}
        )
        seasons = defaults.get("seasons") if isinstance(defaults.get("seasons"), dict) else {}

        dynamic_refs = list(menu.get("dynamic_collections") or [])
        for index, ref in enumerate(dynamic_refs[:DEFAULTS_DYNAMIC_COLLECTION_ROWS], start=1):
            self.fields[_defaults_dynamic_collection_field(index)].initial = ref
        self.fields["defaults_notifications_backend"].initial = notifications.get("backend") or "console"
        self.fields["defaults_max_preorder_days"].initial = defaults.get("max_preorder_days", 30)
        self.fields["defaults_pickup_rounding_minutes"].initial = pickup_config.get("rounding_minutes", 30)
        self.fields["defaults_pickup_history_days"].initial = pickup_config.get("history_days", 30)
        self.fields["defaults_pickup_fallback_slot"].initial = pickup_config.get("fallback_slot", "")
        self.fields["defaults_season_hot_months"].initial = _months_to_text(seasons.get("hot"))
        self.fields["defaults_season_mild_months"].initial = _months_to_text(seasons.get("mild"))
        self.fields["defaults_season_cold_months"].initial = _months_to_text(seasons.get("cold"))
        self.fields["defaults_high_demand_multiplier"].initial = defaults.get("high_demand_multiplier")
        self.fields["defaults_safety_stock_percent"].initial = defaults.get("safety_stock_percent")

        rules = defaults.get("rules") if isinstance(defaults.get("rules"), dict) else {}
        for field_name, key in DEFAULTS_RULE_Q_FIELDS:
            self.fields[field_name].initial = _q_to_reais(rules.get(key))

        pickup_slots = defaults.get("pickup_slots") if isinstance(defaults.get("pickup_slots"), list) else []
        for index, slot in enumerate(pickup_slots[:DEFAULTS_PICKUP_SLOT_ROWS], start=1):
            if not isinstance(slot, dict):
                continue
            self.fields[_defaults_pickup_field(index, "ref")].initial = slot.get("ref", "")
            self.fields[_defaults_pickup_field(index, "label")].initial = slot.get("label", "")
            self.fields[_defaults_pickup_field(index, "starts_at")].initial = _format_admin_time(slot.get("starts_at"))

        closed_dates = defaults.get("closed_dates") if isinstance(defaults.get("closed_dates"), list) else []
        dated_entries = [
            entry
            for entry in closed_dates
            if isinstance(entry, dict) and entry.get("date")
        ]
        for index, closed_date in enumerate(dated_entries[:DEFAULTS_CLOSED_DATE_ROWS], start=1):
            self.fields[_defaults_closed_date_field(index, "date")].initial = _format_admin_date(
                closed_date.get("date")
            )
            self.fields[_defaults_closed_date_field(index, "label")].initial = closed_date.get("label", "")

    def clean(self):
        cleaned_data = super().clean()
        for day, label in OPENING_HOUR_DAYS:
            status = cleaned_data.get(_opening_field(day, "status"))
            opens_at = cleaned_data.get(_opening_field(day, "open"))
            closes_at = cleaned_data.get(_opening_field(day, "close"))
            if status != "open":
                continue
            if not opens_at or not closes_at:
                raise forms.ValidationError(f"Informe abertura e fechamento para {label}, ou marque como fechado.")
            if opens_at >= closes_at:
                raise forms.ValidationError(f"Em {label}, o horário de abertura precisa ser anterior ao fechamento.")
        self._clean_defaults(cleaned_data)
        return cleaned_data

    def _clean_defaults(self, cleaned_data: dict) -> None:
        dynamic_refs: set[str] = set()
        for index in range(1, DEFAULTS_DYNAMIC_COLLECTION_ROWS + 1):
            field = _defaults_dynamic_collection_field(index)
            ref = cleaned_data.get(field)
            if not ref:
                continue
            if ref in dynamic_refs:
                self.add_error(field, "Esta coleção já foi usada em outra posição.")
            dynamic_refs.add(ref)

        slot_refs: set[str] = set()
        for index in range(1, DEFAULTS_PICKUP_SLOT_ROWS + 1):
            ref_field = _defaults_pickup_field(index, "ref")
            label_field = _defaults_pickup_field(index, "label")
            starts_at_field = _defaults_pickup_field(index, "starts_at")
            ref = (cleaned_data.get(ref_field) or "").strip()
            label = (cleaned_data.get(label_field) or "").strip()
            starts_at = cleaned_data.get(starts_at_field)
            has_any_value = bool(ref or label or starts_at)
            if not has_any_value:
                continue
            if not ref:
                self.add_error(ref_field, "Informe o ref do slot.")
            elif ref in slot_refs:
                self.add_error(ref_field, "Este ref já foi usado em outro slot.")
            else:
                slot_refs.add(ref)
            if not label:
                self.add_error(label_field, "Informe o rótulo do slot.")
            if not starts_at:
                self.add_error(starts_at_field, "Informe o horário inicial do slot.")

        fallback_slot = (cleaned_data.get("defaults_pickup_fallback_slot") or "").strip()
        if fallback_slot and fallback_slot not in slot_refs:
            self.add_error("defaults_pickup_fallback_slot", "Use o ref de um dos slots configurados.")

        for index in range(1, DEFAULTS_CLOSED_DATE_ROWS + 1):
            date_field = _defaults_closed_date_field(index, "date")
            label_field = _defaults_closed_date_field(index, "label")
            closed_date = cleaned_data.get(date_field)
            label = (cleaned_data.get(label_field) or "").strip()
            if label and not closed_date:
                self.add_error(date_field, "Informe a data deste feriado ou remova o rótulo.")

        for key, label in (
            ("hot", "Meses quentes"),
            ("mild", "Meses amenos"),
            ("cold", "Meses frios"),
        ):
            field = f"defaults_season_{key}_months"
            try:
                cleaned_data[field] = _parse_months(cleaned_data.get(field), label)
            except forms.ValidationError as exc:
                self.add_error(field, exc)

    def _existing_extra_pickup_slots(self) -> list[dict]:
        pickup_slots = _shop_defaults(self.instance).get("pickup_slots")
        if not isinstance(pickup_slots, list):
            return []
        return [slot for slot in pickup_slots[DEFAULTS_PICKUP_SLOT_ROWS:] if isinstance(slot, dict)]

    def _existing_extra_closed_dates(self) -> list[dict]:
        closed_dates = _shop_defaults(self.instance).get("closed_dates")
        if not isinstance(closed_dates, list):
            return []
        dated_entries_seen = 0
        extra_entries = []
        for entry in closed_dates:
            if not isinstance(entry, dict):
                continue
            if entry.get("date"):
                dated_entries_seen += 1
                if dated_entries_seen <= DEFAULTS_CLOSED_DATE_ROWS:
                    continue
            extra_entries.append(entry)
        return extra_entries

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.opening_hours = {
            day: {
                "open": _format_admin_time(self.cleaned_data.get(_opening_field(day, "open"))),
                "close": _format_admin_time(self.cleaned_data.get(_opening_field(day, "close"))),
            }
            for day, _label in OPENING_HOUR_DAYS
            if self.cleaned_data.get(_opening_field(day, "status")) == "open"
        }
        instance.defaults = self._build_defaults()
        if commit:
            instance.save()
            self.save_m2m()
        return instance

    def _build_defaults(self) -> dict:
        defaults = dict(_shop_defaults(self.instance))

        menu = defaults.get("menu") if isinstance(defaults.get("menu"), dict) else {}
        menu = dict(menu)
        menu["dynamic_collections"] = [
            ref
            for index in range(1, DEFAULTS_DYNAMIC_COLLECTION_ROWS + 1)
            if (ref := self.cleaned_data.get(_defaults_dynamic_collection_field(index)))
        ]
        defaults["menu"] = menu

        notifications = (
            defaults.get("notifications")
            if isinstance(defaults.get("notifications"), dict)
            else {}
        )
        notifications = dict(notifications)
        backend = self.cleaned_data.get("defaults_notifications_backend") or "console"
        notifications["backend"] = backend
        defaults["notifications"] = notifications

        pickup_slots = []
        for index in range(1, DEFAULTS_PICKUP_SLOT_ROWS + 1):
            ref = (self.cleaned_data.get(_defaults_pickup_field(index, "ref")) or "").strip()
            label = (self.cleaned_data.get(_defaults_pickup_field(index, "label")) or "").strip()
            starts_at = self.cleaned_data.get(_defaults_pickup_field(index, "starts_at"))
            if not (ref and label and starts_at):
                continue
            pickup_slots.append({
                "ref": ref,
                "label": label,
                "starts_at": _format_admin_time(starts_at),
            })
        pickup_slots.extend(self._existing_extra_pickup_slots())
        defaults["pickup_slots"] = pickup_slots

        pickup_config = (
            defaults.get("pickup_slot_config")
            if isinstance(defaults.get("pickup_slot_config"), dict)
            else {}
        )
        pickup_config = dict(pickup_config)
        pickup_config["rounding_minutes"] = self.cleaned_data.get("defaults_pickup_rounding_minutes") or 30
        pickup_config["history_days"] = self.cleaned_data.get("defaults_pickup_history_days") or 30
        fallback_slot = (self.cleaned_data.get("defaults_pickup_fallback_slot") or "").strip()
        if fallback_slot:
            pickup_config["fallback_slot"] = fallback_slot
        else:
            pickup_config.pop("fallback_slot", None)
        defaults["pickup_slot_config"] = pickup_config

        defaults["max_preorder_days"] = self.cleaned_data.get("defaults_max_preorder_days")
        if defaults["max_preorder_days"] is None:
            defaults["max_preorder_days"] = 30

        closed_dates = []
        for index in range(1, DEFAULTS_CLOSED_DATE_ROWS + 1):
            closed_date = self.cleaned_data.get(_defaults_closed_date_field(index, "date"))
            label = (self.cleaned_data.get(_defaults_closed_date_field(index, "label")) or "").strip()
            if not closed_date:
                continue
            entry = {"date": _format_admin_date(closed_date)}
            if label:
                entry["label"] = label
            closed_dates.append(entry)
        closed_dates.extend(self._existing_extra_closed_dates())
        defaults["closed_dates"] = closed_dates

        seasons = defaults.get("seasons") if isinstance(defaults.get("seasons"), dict) else {}
        seasons = dict(seasons)
        seasons["hot"] = self.cleaned_data.get("defaults_season_hot_months") or []
        seasons["mild"] = self.cleaned_data.get("defaults_season_mild_months") or []
        seasons["cold"] = self.cleaned_data.get("defaults_season_cold_months") or []
        defaults["seasons"] = seasons

        for field, key in (
            ("defaults_high_demand_multiplier", "high_demand_multiplier"),
            ("defaults_safety_stock_percent", "safety_stock_percent"),
        ):
            value = self.cleaned_data.get(field)
            if value is None:
                defaults.pop(key, None)
            else:
                defaults[key] = str(value)

        rules = defaults.get("rules") if isinstance(defaults.get("rules"), dict) else {}
        rules = dict(rules)
        for field_name, key in DEFAULTS_RULE_Q_FIELDS:
            rules[key] = _reais_to_q(self.cleaned_data.get(field_name))
        defaults["rules"] = rules

        return defaults


def _oklch_raw_to_hex(raw: str) -> str:
    """Convert OKLCH raw string '0.550 0.150 85.0' to hex color."""
    parts = raw.split()
    if len(parts) == 3:
        return oklch_to_hex(float(parts[0]), float(parts[1]), float(parts[2]))
    return "#888888"


def _token_value_to_hex(val: str) -> str:
    """design_tokens: 'R G B' (0–255) ou legado OKLCH tripla → hex."""
    parts = val.split()
    if len(parts) == 3:
        try:
            r, g, b = int(parts[0]), int(parts[1]), int(parts[2])
            if 0 <= r <= 255 and 0 <= g <= 255 and 0 <= b <= 255:
                return f"#{r:02x}{g:02x}{b:02x}"
        except ValueError:
            pass
        if "." in parts[0]:
            return _oklch_raw_to_hex(val)
    return "#888888"


@admin.register(Shop)
class ShopAdmin(ModelAdmin):
    form = ShopForm
    readonly_fields = ("color_preview", "storefront_preview")

    fieldsets = (
        ("Identidade", {
            "fields": ("name", "legal_name", "document"),
        }),
        ("Endereço", {
            "fields": (
                "formatted_address", "route", "street_number", "complement",
                "neighborhood", "city", "state_code", "postal_code",
                "country", "country_code", "latitude", "longitude", "place_id",
            ),
            "description": "Endereço no padrão Google Places. Preencha 'endereço completo' OU os campos individuais.",
        }),
        ("Contato", {
            "fields": ("phone", "email", "default_ddd"),
        }),
        ("Operação", {
            "fields": (
                "currency",
                "timezone",
                ("opening_hours_monday_status", "opening_hours_monday_open", "opening_hours_monday_close"),
                ("opening_hours_tuesday_status", "opening_hours_tuesday_open", "opening_hours_tuesday_close"),
                ("opening_hours_wednesday_status", "opening_hours_wednesday_open", "opening_hours_wednesday_close"),
                ("opening_hours_thursday_status", "opening_hours_thursday_open", "opening_hours_thursday_close"),
                ("opening_hours_friday_status", "opening_hours_friday_open", "opening_hours_friday_close"),
                ("opening_hours_saturday_status", "opening_hours_saturday_open", "opening_hours_saturday_close"),
                ("opening_hours_sunday_status", "opening_hours_sunday_open", "opening_hours_sunday_close"),
            ),
            "description": "Horários gravados em Shop.opening_hours, editados aqui como campos por dia.",
        }),
        ("Branding", {
            "fields": ("brand_name", "short_name", "tagline", "description", "logo"),
        }),
        ("Conteúdo padrão do PDP", {
            "fields": ("conservation_tips_default", "food_safety_notice"),
            "description": (
                "Texto exibido na seção de conservação do PDP quando o produto "
                "não tiver dica específica. O aviso de produção compartilhada "
                "aparece na seção de ingredientes."
            ),
        }),
        ("Paleta de Cores", {
            "fields": (
                "primary_color", "secondary_color", "accent_color",
                "neutral_color", "neutral_dark_color", "color_mode",
                "color_preview",
            ),
            "description": (
                "Seletor de cor (Unfold) para primária, secundária, destaque e neutros. "
                "Cores derivadas automaticamente da primária se deixadas em branco. "
                "Neutra claro: fundo no modo claro; neutra escuro: fundo no modo escuro. "
                "Use 'Automático' para seguir o tema do sistema. "
                "Abaixo, preview da paleta gerada (claro + escuro)."
            ),
        }),
        ("Tipografia & Forma", {
            "fields": ("heading_font", "body_font", "border_radius"),
            "description": (
                "Fontes com preview ao vivo (Google Fonts). Raio dos cantos aplica-se a cards e botões."
            ),
        }),
        ("Preview do storefront (WP-S4)", {
            "fields": ("storefront_preview",),
            "description": (
                "Página inicial em iframe (mesma origem). Salve o formulário e clique em "
                "<strong>Atualizar preview</strong> para ver cores e tipografia sem sair do admin."
            ),
        }),
        ("Redes Sociais", {
            "fields": ("social_links",),
            "description": "Cole as URLs completas das redes sociais. Ícones são detectados automaticamente.",
        }),
        ("Defaults de negócio — cardápio e canais", {
            "fields": (
                "defaults_notifications_backend",
            ) + _defaults_dynamic_collection_admin_rows(),
            "classes": ("collapse",),
            "description": (
                "Configurações gravadas em Shop.defaults, editadas como campos estruturados. "
                "As coleções dinâmicas vêm do registry canônico do core; a posição define a ordem."
            ),
        }),
        ("Defaults de negócio — pedido e entrega", {
            "fields": (
                "defaults_rules_minimum_order_q",
                "defaults_rules_delivery_minimum_q",
                "defaults_rules_free_delivery_above_q",
            ),
            "classes": ("collapse",),
            "description": (
                "Políticas em Reais gravadas em Shop.defaults.rules (centavos). "
                "0 ou vazio desliga a regra. O mínimo de entrega e o frete grátis "
                "valem só para entrega; a taxa por região fica nas Zonas de Entrega."
            ),
        }),
        ("Defaults de negócio — retirada e encomendas", {
            "fields": (
                ("defaults_max_preorder_days", "defaults_pickup_rounding_minutes", "defaults_pickup_history_days"),
                "defaults_pickup_fallback_slot",
            ) + _defaults_pickup_admin_rows(),
            "classes": ("collapse",),
            "description": "Slots padrão de retirada e janela máxima para encomendas.",
        }),
        ("Defaults de negócio — feriados e fechamentos", {
            "fields": _defaults_closed_date_admin_rows(),
            "classes": ("collapse",),
            "description": "Datas de fechamento usadas pelo calendário de negócio e checkout.",
        }),
        ("Defaults de negócio — produção", {
            "fields": (
                ("defaults_season_hot_months", "defaults_season_mild_months", "defaults_season_cold_months"),
                ("defaults_high_demand_multiplier", "defaults_safety_stock_percent"),
            ),
            "classes": ("collapse",),
            "description": "Parâmetros usados por sugestões operacionais e estoque de segurança.",
        }),
        ("Integrações", {
            "fields": ("integrations",),
            "classes": ("collapse",),
            "description": (
                "Seleção de adapters Admin-configurável. Sobreescreve settings.py. "
                "Exemplo: {\"payment\": {\"pix\": \"shopman.shop.adapters.payment_efi\"}}."
            ),
        }),
    )

    @admin.display(description="Preview da paleta (Oxbow → RGB)")
    def color_preview(self, obj):
        """Swatches dos tokens (canais RGB no storefront)."""
        if not obj or not obj.pk:
            return "Salve a loja para ver a paleta."

        tokens = obj.design_tokens
        dark = tokens.get("dark", {})

        # Token groups to preview
        groups = [
            ("Primária", [
                ("primary", "Primary"),
                ("primary_hover", "Hover"),
                ("secondary", "Secondary"),
                ("accent", "Accent"),
            ]),
            ("Superfícies", [
                ("background", "Background"),
                ("surface", "Surface"),
                ("muted", "Muted"),
                ("border", "Border"),
            ]),
            ("Texto", [
                ("foreground", "Foreground"),
                ("foreground_muted", "Muted"),
            ]),
            ("Status", [
                ("success", "Success"),
                ("warning", "Warning"),
                ("error", "Error"),
                ("info", "Info"),
            ]),
        ]

        html_parts = ['<div style="display:flex;flex-direction:column;gap:12px;margin-top:4px">']

        for group_label, items in groups:
            html_parts.append(
                f'<div><strong style="font-size:11px;text-transform:uppercase;'
                f'letter-spacing:0.05em;color:#6b7280">{group_label}</strong>'
                f'<div style="display:flex;gap:6px;margin-top:4px">'
            )
            for token_key, label in items:
                raw = tokens.get(token_key, "128 128 128")
                hex_color = _token_value_to_hex(raw)
                dark_raw = dark.get(token_key, raw)
                dark_hex = _token_value_to_hex(dark_raw)

                html_parts.append(
                    f'<div style="text-align:center">'
                    f'<div style="display:flex;border-radius:6px;overflow:hidden;border:1px solid #e5e7eb">'
                    f'<div style="width:36px;height:36px;background:{hex_color}" title="Light: {hex_color}"></div>'
                    f'<div style="width:36px;height:36px;background:{dark_hex}" title="Dark: {dark_hex}"></div>'
                    f'</div>'
                    f'<div style="font-size:10px;color:#9ca3af;margin-top:2px">{label}</div>'
                    f'</div>'
                )
            html_parts.append('</div></div>')

        html_parts.append('</div>')
        return mark_safe("".join(html_parts))

    @admin.display(description="Preview ao vivo (iframe)")
    def storefront_preview(self, obj):
        """Iframe da home — requer X-Frame-Options: SAMEORIGIN na HomeView."""
        if not obj or not obj.pk:
            return format_html(
                '<p class="help">Salve a loja para carregar o preview do storefront.</p>'
            )

        from django.urls import reverse

        try:
            url = reverse("storefront:home")
        except Exception:
            logger.debug("shop.storefront_preview degraded; using fallback", exc_info=True)
            url = "/"

        url_json = mark_safe(json.dumps(url))
        return format_html(
            '<div class="storefront-admin-preview" style="max-width:100%">'
            '<p style="margin:0 0 8px;font-size:12px;color:#6b7280">'
            "A home pública permite iframe apenas neste site (SAMEORIGIN)."
            "</p>"
            '<div style="display:flex;gap:8px;align-items:center;margin-bottom:8px;flex-wrap:wrap">'
            '<button type="button" class="button" id="storefront-preview-refresh">'
            "Atualizar preview"
            "</button>"
            "</div>"
            '<iframe id="storefront-preview-iframe" src="{}" title="Storefront" '
            'style="width:100%;min-height:min(70vh,640px);border:1px solid #e5e7eb;'
            'border-radius:8px;background:#fff"></iframe>'
            "<script>"
            "(function(){{"
            'var f=document.getElementById("storefront-preview-iframe");'
            'var b=document.getElementById("storefront-preview-refresh");'
            "var u={};"
            "if(b&&f){{b.addEventListener('click',function(){{"
            'var sep=u.indexOf("?")>=0?"&":"?";'
            'f.src=u+sep+"__pv="+Date.now();'
            "}});}}"
            "}})();"
            "</script>"
            "</div>",
            url,
            url_json,
        )

    def has_add_permission(self, request):
        return not Shop.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        obj = Shop.objects.first()
        if obj:
            return self.changeform_view(request, str(obj.pk), extra_context=extra_context)
        return super().changelist_view(request, extra_context=extra_context)


@admin.register(NotificationTemplate)
class NotificationTemplateAdmin(ModelAdmin):
    list_display = ("event", "subject", "is_active")
    list_filter = ("is_active",)
    search_fields = ("event", "subject", "body")
    list_editable = ("is_active",)
    fields = ("event", "subject", "body", "is_active")
    readonly_fields = ("event",)
