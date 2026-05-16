from __future__ import annotations

import json

from scripts import check_release_readiness as readiness


def test_readiness_report_allows_external_blockers_in_default_mode():
    report = readiness.ReadinessReport(
        strict_external=False,
        checks=(
            readiness.ReadinessCheck(
                id="local",
                title="Local",
                status="passed",
                message="ok",
            ),
            readiness.ReadinessCheck(
                id="external",
                title="External",
                status="blocked_external",
                message="needs credentials",
            ),
        ),
    )

    assert report.status == "passed_with_external_blockers"
    assert report.external_blocked
    assert not report.blocking


def test_readiness_report_blocks_external_in_strict_mode():
    report = readiness.ReadinessReport(
        strict_external=True,
        checks=(
            readiness.ReadinessCheck(
                id="external",
                title="External",
                status="blocked_external",
                message="needs staging",
            ),
        ),
    )

    assert report.status == "blocked_external"
    assert report.blocking


def test_manual_qa_evidence_check_passes_when_file_exists(tmp_path):
    evidence = tmp_path / "manual-qa.md"
    evidence.write_text("# QA\n", encoding="utf-8")

    check = readiness._manual_qa_check(str(evidence))

    assert check.status == "passed"
    assert check.details["evidence"] == str(evidence)


def test_main_outputs_json_and_uses_blocking_exit(monkeypatch, capsys):
    report = readiness.ReadinessReport(
        strict_external=True,
        checks=(
            readiness.ReadinessCheck(
                id="external",
                title="External",
                status="blocked_external",
                message="needs staging",
            ),
        ),
    )
    monkeypatch.setattr(readiness, "build_report", lambda **kwargs: report)

    exit_code = readiness.main(["--strict-external", "--json"])

    data = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert data["status"] == "blocked_external"
    assert data["counts"]["blocked_external"] == 1
