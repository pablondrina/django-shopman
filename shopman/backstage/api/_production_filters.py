"""Query-param parsing for the production reports API (manager persona).

The ``/reports`` page of the production-nuxt app (``fournil.``) drives the
``api/v1/backstage/production/reports/`` endpoint with a free-form query
string; this module normalizes it into the filter dict consumed by
``build_production_reports``/``export_reports_csv`` (invalid kinds fall back
to ``history``, invalid dates to the trailing 7-day window).
"""

from __future__ import annotations

from datetime import date, timedelta

from django.utils import timezone

VALID_REPORT_KINDS = ("history", "operator_productivity", "recipe_waste")


def report_filters(request) -> dict:
    today = timezone.localdate()
    raw_from = (request.GET.get("date_from") or (today - timedelta(days=6)).isoformat()).strip()
    raw_to = (request.GET.get("date_to") or today.isoformat()).strip()
    raw_kind = (request.GET.get("report_kind") or request.GET.get("kind") or "history").strip()

    date_from = _coerce_iso_date(raw_from, fallback=today - timedelta(days=6))
    date_to = _coerce_iso_date(raw_to, fallback=today)
    if date_from > date_to:
        date_from, date_to = date_to, date_from

    return {
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "recipe_ref": (request.GET.get("recipe_ref") or "").strip(),
        "position_ref": (request.GET.get("position_ref") or "").strip(),
        "operator_ref": (request.GET.get("operator_ref") or "").strip(),
        "status": (request.GET.get("status") or "").strip(),
        "report_kind": raw_kind if raw_kind in VALID_REPORT_KINDS else "history",
    }


def _coerce_iso_date(raw: str, *, fallback: date) -> date:
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return fallback
