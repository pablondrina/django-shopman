"""Permission parity regression — guards the "bug-semente" (SEED-DATA-QUALITY Fase 0).

A runtime gate is dead code the moment it checks a permission that no group
grants: ``user.has_perm("backstage.adjust_cashshift")`` returns ``False`` for
every non-superuser, so the feature silently works only for superusers. That is
exactly what happened before Fase 0 (Gerente lacked ``adjust_cashshift`` and
``manage_operators``).

This module canonizes the fix in two layers:

1. An explicit, readable ``(permission -> expected group)`` table asserted
   against the groups ``setup_groups`` actually builds. This documents intent and
   fails loudly if a specific grant is dropped.
2. A self-maintaining discovery pass that scrapes the real gate modules for the
   permission strings they require and asserts every one is granted to *some*
   group — so a newly added gate whose permission nobody grants fails here, even
   if we forget to update the table above. Perms that are intentionally not on an
   operator group live in an explicit, justified allow-list.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from django.contrib.auth.models import Group
from django.core.management import call_command

# Repo root: this file is <root>/shopman/shop/tests/test_group_permission_parity.py
_REPO_ROOT = Path(__file__).resolve().parents[3]

# Every module that contains a runtime RBAC gate (``user.has_perm(...)`` or an
# equivalent predicate). Kept in sync with the gate inventory in the plan.
GATE_FILES = [
    "shopman/backstage/permissions.py",
    "shopman/shop/services/pos.py",
    "shopman/backstage/admin/operators.py",
    "shopman/backstage/admin/pos.py",
    "shopman/backstage/admin/kds.py",
    "shopman/backstage/admin/closing.py",
    "shopman/backstage/admin/cash_register.py",
    "shopman/backstage/admin_console/closing.py",
    "shopman/backstage/projections/production.py",
]

# Matches a permission literal like "backstage.adjust_cashshift" or
# "shop.manage_orders". f-strings that interpolate a column
# (f"shop.view_production_{column}") contain a brace before the closing quote and
# therefore do NOT match here — they are covered explicitly in the parity table.
_PERM_LITERAL = re.compile(r'"((?:shop|backstage)\.[a-z_]+)"')

# ---------------------------------------------------------------------------
# Explicit parity table: (permission, {groups that MUST grant it}).
# Derived by reading the gates; each row names the gate it protects.
# ---------------------------------------------------------------------------
PARITY_TABLE: list[tuple[str, set[str]]] = [
    # pos.py::_verify_manager_pin (POS manager approval) + cash adjust
    ("backstage.adjust_cashshift", {"Gerente"}),
    # admin/operators.py::PinCredentialAdmin (reset / provision operator PIN)
    ("backstage.manage_operators", {"Gerente"}),
    # permissions.can_close_day + admin/closing.py + admin_console/closing.py
    ("backstage.perform_closing", {"Gerente"}),
    # permissions.can_operate_pos + admin/pos.py + admin/cash_register.py
    ("backstage.operate_pos", {"Caixa", "Gerente"}),
    # permissions.can_operate_kds + admin/kds.py
    ("backstage.operate_kds", {"Cozinha"}),
    # permissions.can_operate_production (dedicated floor app gate)
    ("backstage.operate_production", {"Cozinha", "Gerente"}),
    # permissions.can_manage_orders (orders API + sidebar)
    ("shop.manage_orders", {"Caixa", "Gerente"}),
    # permissions.can_access_production / can_view_production_reports (full
    # access shortcut). Only Cozinha holds it: Gerente reaches the board through
    # its full set of fine-grained column perms (can_access_board), so it does
    # NOT need the coarse manage_production grant.
    ("shop.manage_production", {"Cozinha"}),
    # resolve_production_access fine-grained columns (f-string perms, not
    # discoverable by the literal scan). Cozinha runs the floor
    # (planned/started/finished); Gerente also plans (suggested) and reconciles
    # (unsold).
    ("shop.view_production_planned", {"Cozinha", "Gerente"}),
    ("shop.edit_production_planned", {"Cozinha", "Gerente"}),
    ("shop.view_production_started", {"Cozinha", "Gerente"}),
    ("shop.edit_production_started", {"Cozinha", "Gerente"}),
    ("shop.view_production_finished", {"Cozinha", "Gerente"}),
    ("shop.edit_production_finished", {"Cozinha", "Gerente"}),
    ("shop.view_production_suggested", {"Gerente"}),
    ("shop.edit_production_suggested", {"Gerente"}),
    ("shop.view_production_unsold", {"Gerente"}),
    ("shop.edit_production_unsold", {"Gerente"}),
]

# ---------------------------------------------------------------------------
# Discovery allow-list: gate permissions that are intentionally NOT granted to
# any operator group. Each MUST be justified — an unjustified entry here would
# hide the very bug this test exists to catch.
# ---------------------------------------------------------------------------
UNGRANTED_BY_DESIGN: dict[str, str] = {
    # can_view_production_reports() accepts this OR shop.manage_production. The
    # OR-alternative (shop.manage_production) is what the operator groups hold
    # (Cozinha/Gerente), so the reports gate is reachable without a dedicated
    # backstage.view_production_reports grant. The perm is a superuser/optional
    # fine-grained hook, deliberately off the default groups.
    "backstage.view_production_reports": (
        "OR-alternative in can_view_production_reports; covered by "
        "shop.manage_production on Cozinha/Gerente."
    ),
}


def _granted_by_group() -> dict[str, set[str]]:
    """group_name -> set of 'app_label.codename' after setup_groups runs."""
    call_command("setup_groups")
    result: dict[str, set[str]] = {}
    for group in Group.objects.prefetch_related(
        "permissions__content_type"
    ):
        result[group.name] = {
            f"{p.content_type.app_label}.{p.codename}"
            for p in group.permissions.all()
        }
    return result


def _discover_gate_perms() -> set[str]:
    """Scrape gate modules for the permission literals they require."""
    found: set[str] = set()
    for rel in GATE_FILES:
        path = _REPO_ROOT / rel
        assert path.exists(), f"gate file missing: {rel} (update GATE_FILES?)"
        found.update(_PERM_LITERAL.findall(path.read_text(encoding="utf-8")))
    return found


@pytest.mark.django_db
def test_parity_table_every_gate_perm_is_granted_to_expected_group():
    """Each gate permission is granted to at least its intended group(s)."""
    granted = _granted_by_group()

    for perm, expected_groups in PARITY_TABLE:
        for group_name in expected_groups:
            assert group_name in granted, (
                f"expected group {group_name!r} does not exist "
                f"(needed to grant {perm!r})"
            )
            assert perm in granted[group_name], (
                f"RBAC parity broken: gate requires {perm!r} but group "
                f"{group_name!r} does not grant it. A user in {group_name!r} "
                f"would hit a dead gate. Add it in setup_groups.py."
            )


@pytest.mark.django_db
def test_discovered_gate_perms_are_covered_by_some_group():
    """Self-maintaining: any gate perm scraped from source must be grantable.

    Guards against adding a new ``has_perm(...)`` gate without wiring the
    permission into any group. Perms intentionally off the operator groups must
    be justified in UNGRANTED_BY_DESIGN.
    """
    granted = _granted_by_group()
    all_granted: set[str] = set().union(*granted.values()) if granted else set()

    discovered = _discover_gate_perms()
    # Sanity: the scan actually found the gates (not a silent no-op).
    assert "backstage.adjust_cashshift" in discovered, (
        "discovery regex found no adjust_cashshift gate — the scan is broken"
    )
    assert "backstage.operate_pos" in discovered

    dead_gates = {
        perm
        for perm in discovered
        if perm not in all_granted and perm not in UNGRANTED_BY_DESIGN
    }
    assert not dead_gates, (
        "Dead RBAC gate(s) found: these permissions are required by a runtime "
        f"gate but granted to NO group: {sorted(dead_gates)}. Either grant them "
        "in setup_groups.py or add a justified entry to UNGRANTED_BY_DESIGN."
    )

    # Keep the allow-list honest: an exception that is actually granted (or no
    # longer a real gate) should be removed so the list stays meaningful.
    for perm in UNGRANTED_BY_DESIGN:
        assert perm not in all_granted, (
            f"{perm!r} is in UNGRANTED_BY_DESIGN but IS granted to a group — "
            "remove the stale exception."
        )
        assert perm in discovered, (
            f"{perm!r} is in UNGRANTED_BY_DESIGN but no gate references it — "
            "remove the stale exception."
        )
