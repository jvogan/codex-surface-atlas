from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

import pytest

from surface_atlas.report import ReportError, build_report
from surface_atlas.report_builder import render_screening_table, render_target_screening_table


REPOSITORY = Path(__file__).resolve().parents[1]
SYNTHETIC = REPOSITORY / "examples" / "synthetic-atlas"


def screening_records() -> list[dict]:
    return [
        {
            "screening_result_id": "RESULT-ZERO",
            "run_id": "run-zeta",
            "screen_role": "negative_control",
            "molecule_id": "M-ZERO",
            "target_id": "T-LANTERN",
            "site_id": "SITE-ZERO",
            "site": "legacy site ignored when site_id is present",
            "route": "synthetic-route",
            "model_version": "synthetic-model-v1",
            "scoring_function": "zero-score",
            "score_units": "kcal/mol",
            "pose_score": 0,
            "control_status": "passed",
            "execution_state": "complete",
            "failure_reason": None,
        },
        {
            "screening_result_id": "RESULT-NULL",
            "run_id": "run-alpha",
            "screen_role": "prospective",
            "molecule_id": "M-NULL",
            "target_id": "T-LANTERN",
            "site": "legacy extracellular site",
            "route": "synthetic-route",
            "model_version": "synthetic-model-v2",
            "scoring_function": "null-score",
            "score_units": "arbitrary units",
            "pose_score": None,
            "control_status": "not run",
            "execution_state": "failed",
            "failure_reason": "Synthetic pose generation failed",
        },
    ]


def test_screening_tables_show_run_role_site_and_score_context_without_ranking() -> None:
    records = screening_records()

    rendered = render_screening_table(records, {})
    target_rendered = render_target_screening_table(
        records, "T-LANTERN", "Lantern adhesion protein", {}
    )

    for html in (rendered, target_rendered):
        assert "Run ID" in html
        assert "Role" in html
        assert "Score method / units" in html
        assert "Control status" in html
        assert "run-zeta" in html
        assert "run-alpha" in html
        assert "negative-control" in html
        assert "prospective" in html
        assert "SITE-ZERO" in html
        assert "legacy extracellular site" in html
        assert "legacy site ignored when site_id is present" not in html
        assert "zero-score · kcal/mol" in html
        assert "zero-score 0 kcal/mol" in html
        assert "null-score · arbitrary units" in html
        assert "Synthetic pose generation failed" in html
        assert html.index("RESULT-ZERO") < html.index("RESULT-NULL")
        assert '<option value="8">Score method / units</option>' not in html


def test_screening_csv_has_explicit_run_role_site_score_status_and_failure_columns(
    tmp_path: Path,
) -> None:
    atlas = tmp_path / "atlas"
    shutil.copytree(SYNTHETIC, atlas)
    records = screening_records()
    screening_path = atlas / "screening-results.json"
    payload = json.loads(screening_path.read_text(encoding="utf-8"))
    payload["source_runs"] = [
        {"run_id": "run-zeta", "screen_id": "screen-zeta"},
        {"run_id": "run-alpha", "screen_id": "screen-alpha"},
    ]
    payload["confirmation_contexts"] = []
    payload["records"] = records
    screening_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    result = build_report(atlas, output_root=tmp_path / "reports", run_id="screening-columns")
    run_directory = Path(result["run_directory"])
    with (run_directory / "data" / "screening-results.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fieldnames = reader.fieldnames or []

    assert [row["id"] for row in rows] == ["RESULT-ZERO", "RESULT-NULL"]
    for field in (
        "run_id",
        "screen_role",
        "site_id",
        "site",
        "scoring_function",
        "score_units",
        "pose_score",
        "score",
        "control_status",
        "execution_state",
        "failure_reason",
    ):
        assert field in fieldnames
    assert rows[0]["run_id"] == "run-zeta"
    assert rows[0]["screen_role"] == "negative-control"
    assert rows[0]["site_id"] == "SITE-ZERO"
    assert rows[0]["site"] == "legacy site ignored when site_id is present"
    assert rows[0]["pose_score"] == "0"
    assert rows[0]["score"] == "0"
    assert rows[0]["control_status"] == "passed"
    assert rows[1]["site_id"] == "legacy extracellular site"
    assert rows[1]["pose_score"] == ""
    assert rows[1]["failure_reason"] == "Synthetic pose generation failed"
    assert '"pose_score":null' in rows[1]["raw_json"]

    exported = json.loads(
        (run_directory / "data" / "screening-results.json").read_text(encoding="utf-8")
    )
    assert exported["source_runs"] == payload["source_runs"]
    assert exported["records"] == records
    target_page = next(run_directory.glob("target-*lantern*.html")).read_text(encoding="utf-8")
    assert "Run ID" in target_page
    assert target_page.index("run-zeta") < target_page.index("run-alpha")


def test_report_overwrite_error_does_not_disclose_output_path(tmp_path: Path) -> None:
    output_root = tmp_path / "absolute-output-location" / "reports"
    build_report(SYNTHETIC, output_root=output_root, run_id="existing-run")

    with pytest.raises(ReportError) as captured:
        build_report(SYNTHETIC, output_root=output_root, run_id="existing-run")

    message = str(captured.value)
    assert "refusing to overwrite" in message
    assert str(output_root) not in message
    assert "existing-run" not in message
