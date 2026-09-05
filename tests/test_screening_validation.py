from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from surface_atlas.screening_merge import merge_screening_collections
from surface_atlas.validator import validate_workspace


REPOSITORY = Path(__file__).resolve().parents[1]
SYNTHETIC = REPOSITORY / "examples" / "synthetic-atlas"
SCREEN_MERGE = REPOSITORY / "examples" / "screen-merge"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def copy_workspace(tmp_path: Path) -> Path:
    destination = tmp_path / "atlas"
    shutil.copytree(SYNTHETIC, destination)
    return destination


def screening_payload(atlas: Path) -> dict:
    return load(atlas / "screening-results.json")


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (
            {"source_runs": [None]},
            "screening-results.json: source runs must be objects",
        ),
        (
            {
                "source_runs": [
                    {"run_id": "screen-a"},
                    {"run_id": "screen-a"},
                ]
            },
            "screening-results.json: source run IDs must be non-empty and unique",
        ),
        (
            {
                "source_runs": [{"run_id": "screen-a", "screen_id": "screen-a"}],
                "confirmation_contexts": [
                    {"run_id": "screen-a", "screen_id": "screen-b"}
                ],
            },
            "screening-results.json: confirmation screen_id does not match its source run",
        ),
        (
            {
                "source_runs": [{"run_id": "screen-a"}],
                "confirmation_contexts": [],
                "records": [
                    {"screening_result_id": "legacy-screen", "run_id": "screen-unknown"}
                ],
            },
            "screening-results.json: each record must reference a source run",
        ),
    ],
)
def test_validator_rejects_malformed_or_crossed_screening_scopes(
    tmp_path: Path, change: dict, message: str
) -> None:
    atlas = copy_workspace(tmp_path)
    payload = screening_payload(atlas)
    payload.update(change)
    save(atlas / "screening-results.json", payload)

    result = validate_workspace(atlas)

    assert result["valid"] is False
    assert message in result["errors"]


def test_validator_requires_screening_atlas_id_to_match_plan(tmp_path: Path) -> None:
    atlas = copy_workspace(tmp_path)
    payload = screening_payload(atlas)
    payload["atlas_id"] = "another-atlas"
    save(atlas / "screening-results.json", payload)

    result = validate_workspace(atlas)

    assert result["valid"] is False
    assert "screening-results.json: atlas_id does not match atlas-plan.json" in result["errors"]


def test_validator_accepts_merged_synthetic_screening_fixture(tmp_path: Path) -> None:
    atlas = copy_workspace(tmp_path)
    merged = merge_screening_collections(
        [SCREEN_MERGE / "run-a.json", SCREEN_MERGE / "run-b.json"]
    )
    save(atlas / "screening-results.json", merged)

    result = validate_workspace(atlas)

    assert result["valid"] is True, result["errors"]
    assert result["errors"] == []


def test_validator_accepts_legacy_envelope_less_screening_records(tmp_path: Path) -> None:
    atlas = copy_workspace(tmp_path)
    payload = screening_payload(atlas)

    assert "source_run" not in payload
    assert "source_runs" not in payload
    assert payload["records"][0]["screening_result_id"]

    result = validate_workspace(atlas)

    assert result["valid"] is True, result["errors"]
    assert result["errors"] == []
