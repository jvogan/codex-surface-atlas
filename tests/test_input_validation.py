from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

import pytest

from surface_atlas import report_builder
from surface_atlas.report import ReportError, build_report
from surface_atlas.validator import validate_workspace


REPOSITORY = Path(__file__).resolve().parents[1]
SYNTHETIC = REPOSITORY / "examples" / "synthetic-atlas"
ATLAS_ID = "synthetic-surface-atlas"


def copy_workspace(tmp_path: Path, name: str = "atlas") -> Path:
    destination = tmp_path / name
    shutil.copytree(SYNTHETIC, destination)
    return destination


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


@pytest.mark.parametrize("filename", ["atlas-plan.json", "search-ledger.json", "capabilities.json"])
def test_validator_rejects_non_object_top_level(tmp_path: Path, filename: str) -> None:
    atlas = copy_workspace(tmp_path)
    save(atlas / filename, [])

    result = validate_workspace(atlas)

    assert result["valid"] is False
    assert f"{filename}: top level must be an object" in result["errors"]


def test_validator_reports_invalid_utf8_without_raising(tmp_path: Path) -> None:
    atlas = copy_workspace(tmp_path)
    (atlas / "targets.json").write_bytes(b"\xff\xfe")
    (atlas / ".surface-atlas-local.json").write_bytes(b"\xff\xfe")

    result = validate_workspace(atlas)

    assert result["valid"] is False
    assert "invalid UTF-8 in targets.json" in result["errors"]
    assert "invalid UTF-8 in .surface-atlas-local.json" in result["errors"]


@pytest.mark.parametrize("disease", ["disease name", None, [], 1, True])
def test_validator_rejects_non_object_disease(tmp_path: Path, disease: object) -> None:
    atlas = copy_workspace(tmp_path)
    plan = load(atlas / "atlas-plan.json")
    plan["disease"] = disease
    save(atlas / "atlas-plan.json", plan)

    result = validate_workspace(atlas)

    assert result["valid"] is False
    assert "atlas-plan.json: disease must be an object" in result["errors"]


def test_validator_allows_omitted_optional_disease(tmp_path: Path) -> None:
    atlas = copy_workspace(tmp_path)
    plan = load(atlas / "atlas-plan.json")
    plan.pop("disease")
    save(atlas / "atlas-plan.json", plan)

    result = validate_workspace(atlas)

    assert result["valid"] is True, result["errors"]


def test_validator_requires_collection_specific_ids_and_detects_duplicates(tmp_path: Path) -> None:
    atlas = copy_workspace(tmp_path)
    targets = load(atlas / "targets.json")
    first = dict(targets["records"][0])
    first.pop("target_id")
    first["entity_id"] = "E-WRONG-NAMESPACE"
    targets["records"][0] = first
    targets["records"].append(dict(targets["records"][1]))
    save(atlas / "targets.json", targets)

    result = validate_workspace(atlas)

    assert result["valid"] is False
    assert any("records[0].target_id must be a non-empty string" in error for error in result["errors"])
    assert any("duplicate record ID T-LANTERN" in error for error in result["errors"])


def test_validator_checks_safe_atlas_id_and_unresolved_count(tmp_path: Path) -> None:
    atlas = copy_workspace(tmp_path)
    for path in atlas.glob("*.json"):
        payload = load(path)
        if "atlas_id" in payload:
            payload["atlas_id"] = "../escape"
            save(path, payload)
    ledger = load(atlas / "search-ledger.json")
    ledger["counts"]["unresolved_records"] = 2
    save(atlas / "search-ledger.json", ledger)

    result = validate_workspace(atlas)

    assert result["valid"] is False
    assert any("atlas_id must contain 3-64 lowercase" in error for error in result["errors"])
    assert any("unresolved_records does not equal" in error for error in result["errors"])


def test_validator_rejects_blank_and_duplicate_query_ids(tmp_path: Path) -> None:
    atlas = copy_workspace(tmp_path)
    ledger = load(atlas / "search-ledger.json")
    source = dict(ledger["sources"][0])
    duplicate = dict(source)
    blank = dict(source)
    blank["query_id"] = "   "
    ledger["sources"] = [source, duplicate, blank]
    save(atlas / "search-ledger.json", ledger)

    result = validate_workspace(atlas)

    assert result["valid"] is False
    assert any("duplicate query_id" in error for error in result["errors"])
    assert "search-ledger.json: sources[2].query_id is required" in result["errors"]


@pytest.mark.parametrize(
    "case",
    ["missing-records", "records-object", "non-object-record", "duplicate-id", "missing-id", "invalid-utf8"],
)
def test_report_rejects_malformed_collections_without_a_partial_run(tmp_path: Path, case: str) -> None:
    atlas = copy_workspace(tmp_path)
    path = atlas / "targets.json"
    payload = load(path)
    if case == "missing-records":
        payload.pop("records")
        save(path, payload)
    elif case == "records-object":
        payload["records"] = {}
        save(path, payload)
    elif case == "non-object-record":
        payload["records"].append("not an object")
        save(path, payload)
    elif case == "duplicate-id":
        payload["records"].append(dict(payload["records"][0]))
        save(path, payload)
    elif case == "missing-id":
        payload["records"][0].pop("target_id")
        save(path, payload)
    else:
        path.write_bytes(b"\xff\xfe")

    output_root = tmp_path / "reports"
    with pytest.raises(ReportError):
        build_report(atlas, output_root=output_root, run_id="rejected-input")

    assert not (output_root / ATLAS_ID / "rejected-input").exists()
    staging_parent = output_root / ATLAS_ID
    assert not staging_parent.exists() or not list(staging_parent.glob(".rejected-input.*"))


def test_report_removes_staging_run_after_late_artifact_failure(tmp_path: Path) -> None:
    atlas = copy_workspace(tmp_path)
    artifact = atlas / "artifact.txt"
    artifact.write_text("synthetic artifact", encoding="utf-8")
    targets = load(atlas / "targets.json")
    targets["records"][0]["artifacts"] = [
        {"path": artifact.name, "bytes": artifact.stat().st_size, "sha256": "0" * 64}
    ]
    save(atlas / "targets.json", targets)
    output_root = tmp_path / "reports"

    with pytest.raises(ReportError, match="artifact integrity check failed"):
        build_report(atlas, output_root=output_root, run_id="bad-artifact")

    assert not (output_root / ATLAS_ID / "bad-artifact").exists()
    assert not list((output_root / ATLAS_ID).glob(".bad-artifact.*"))


def test_report_does_not_follow_handoff_symlinks(tmp_path: Path) -> None:
    atlas = copy_workspace(tmp_path)
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps({"request_id": "OUTSIDE-SYMLINK-MARKER"}), encoding="utf-8")
    handoffs = atlas / "handoffs"
    handoffs.mkdir()
    (handoffs / "outside.json").symlink_to(outside)

    result = build_report(atlas, output_root=tmp_path / "reports", run_id="safe-handoffs")
    run_directory = Path(result["run_directory"])
    exported_text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in run_directory.rglob("*")
        if path.is_file()
    )

    assert "OUTSIDE-SYMLINK-MARKER" not in exported_text
    assert not (run_directory / "data" / "handoffs" / "handoffs" / "outside.json").exists()


def test_report_neutralizes_spreadsheet_formula_cells(tmp_path: Path) -> None:
    atlas = copy_workspace(tmp_path)
    targets = load(atlas / "targets.json")
    targets["records"][0]["preferred_name"] = "=1+1"
    save(atlas / "targets.json", targets)

    result = build_report(atlas, output_root=tmp_path / "reports", run_id="csv-safe")
    with (Path(result["run_directory"]) / "data" / "targets.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))

    assert rows[0]["name"] == "'=1+1"


def test_report_preserves_screening_result_ids(tmp_path: Path) -> None:
    atlas = copy_workspace(tmp_path)
    expected_id = load(atlas / "screening-results.json")["records"][0]["screening_result_id"]

    result = build_report(atlas, output_root=tmp_path / "reports", run_id="screening-id")
    with (Path(result["run_directory"]) / "data" / "screening-results.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        first = next(csv.DictReader(handle))

    assert first["id"] == expected_id


def test_only_http_source_schemes_become_links() -> None:
    records = [
        {
            "sources": [
                {"label": "script", "url": "javascript:alert(1)"},
                {"label": "inline", "url": "data:text/html,unsafe"},
                {"label": "local", "url": "file:///tmp/private"},
                {"label": "web", "url": "https://example.test/evidence"},
            ]
        }
    ]

    rendered = report_builder.render_source_list(records)

    assert 'href="https://example.test/evidence"' in rendered
    assert 'href="javascript:' not in rendered
    assert 'href="data:' not in rendered
    assert 'href="file:' not in rendered
