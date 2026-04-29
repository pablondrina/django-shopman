"""Guardrails for canonical Django Unfold Admin templates."""

from __future__ import annotations

import subprocess
import sys


def test_admin_console_templates_do_not_hand_roll_visual_controls_or_tokens() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/check_unfold_canonical.py"],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
