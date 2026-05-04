from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "lint_omotenashi_copy.py"
SPEC = importlib.util.spec_from_file_location("lint_omotenashi_copy", SCRIPT)
lint_omotenashi_copy = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(lint_omotenashi_copy)


def test_lint_omotenashi_copy_ignores_multiline_alpine_attributes(tmp_path):
    template = tmp_path / "sample.html"
    template.write_text(
        """
        <div x-data="{
          tick() {
            const diff = Math.max(0, Math.floor((Date.now() - start) / 1000));
            this.label = 'Atualizado há ' + diff + 's';
          }
        }">
          <span x-text="label"></span>
        </div>
        """,
        encoding="utf-8",
    )

    assert lint_omotenashi_copy.lint_file(template) == []


def test_lint_omotenashi_copy_flags_visible_unwrapped_text(tmp_path):
    template = tmp_path / "sample.html"
    template.write_text(
        "<p>Você pode colar o código. Ao completar, a confirmação é automática.</p>",
        encoding="utf-8",
    )

    assert lint_omotenashi_copy.lint_file(template) == [
        (
            1,
            "<p>Você pode colar o código. Ao completar, a confirmação é automática.</p>",
        )
    ]
