"""Operator alert command service."""

from __future__ import annotations

from dataclasses import dataclass

from shopman.backstage.services.exceptions import AlertError


@dataclass(frozen=True)
class AlertCounts:
    active: int
    critical: int


def list_active_alerts(*, limit: int | None = None):
    from shopman.backstage.models import OperatorAlert

    qs = OperatorAlert.objects.filter(acknowledged=False).order_by("-created_at")
    if limit is None:
        return list(qs)
    return list(qs[:limit])


def active_counts() -> AlertCounts:
    from shopman.backstage.models import OperatorAlert

    active = OperatorAlert.objects.filter(acknowledged=False)
    return AlertCounts(active=active.count(), critical=active.filter(severity="critical").count())


def create_alert(
    *,
    type: str,
    severity: str = "warning",
    message: str,
    order_ref: str = "",
):
    from shopman.backstage.models import OperatorAlert

    _validate_choice(type, {choice for choice, _ in OperatorAlert.TYPE_CHOICES}, "tipo")
    _validate_choice(severity, {choice for choice, _ in OperatorAlert.SEVERITY_CHOICES}, "severidade")
    if not message.strip():
        raise AlertError("Mensagem do alerta é obrigatória.")

    return OperatorAlert.objects.create(
        type=type,
        severity=severity,
        message=message.strip(),
        order_ref=order_ref,
    )


def ack_alert(pk: int) -> bool:
    from shopman.backstage.models import OperatorAlert

    alert = OperatorAlert.objects.filter(pk=pk).first()
    if alert is None:
        return False
    if alert.acknowledged:
        return True
    alert.acknowledged = True
    alert.save(update_fields=["acknowledged"])
    return True


def escalate_alert(pk: int, *, severity: str = "critical", message: str | None = None):
    from shopman.backstage.models import OperatorAlert

    _validate_choice(severity, {choice for choice, _ in OperatorAlert.SEVERITY_CHOICES}, "severidade")
    alert = OperatorAlert.objects.filter(pk=pk).first()
    if alert is None:
        raise AlertError("Alerta não encontrado.")
    alert.severity = severity
    if message is not None:
        alert.message = message.strip()
    alert.save(update_fields=["severity", "message"] if message is not None else ["severity"])
    return alert


def _validate_choice(value: str, allowed: set[str], label: str) -> None:
    if value not in allowed:
        raise AlertError(f"{label.capitalize()} inválida: {value}")
