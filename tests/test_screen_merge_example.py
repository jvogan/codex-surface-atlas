from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


EXAMPLE = Path(__file__).parents[1] / "examples" / "screen-merge"
INPUTS = (EXAMPLE / "run-a.json", EXAMPLE / "run-b.json")
SCHEMA_VERSION = "codex-surface-screening-result-collection/v0.1"
CLAIM_CEILING = "computational-screening-hypothesis"


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_inputs_keep_independent_planned_runs_and_scoped_controls() -> None:
    payloads = [read(path) for path in INPUTS]
    run_ids = {payload["source_run"]["run_id"] for payload in payloads}
    result_ids = set()

    assert len(run_ids) == 2
    for payload in payloads:
        assert payload["schema_version"] == SCHEMA_VERSION
        assert payload["atlas_id"] == "synthetic-surface-atlas"
        assert payload["claim_ceiling"] == CLAIM_CEILING
        assert payload["summary"]["execution_complete"] is False
        assert payload["summary"]["claim_ceiling"] == CLAIM_CEILING
        assert payload["source_run"]["execution_state"] == "planned"
        assert payload["confirmation_context"]["state"] == "requested-but-unrun"
        assert payload["confirmation_context"]["requested"] is True
        assert len(payload["records"]) == 2
        assert {record["screen_role"] for record in payload["records"]} == {
            "prospective",
            "reference-control",
        }
        for record in payload["records"]:
            result_ids.add(record["screening_result_id"])
            assert record["run_id"] == payload["source_run"]["run_id"]
            assert record["target_id"] == "T-EMBER"
            assert record["site_id"] == "SITE-EMBER-LOOP"
            assert record["molecule_id"] in {"M-EMBER-01", "M-LANTERN-01"}
            assert record["model_version"]
            assert record["scoring_function"]
            assert record["score_units"]
            assert record["route"] == payload["source_run"]["route"]
            assert record["execution_state"] == "planned"
            assert record["pose_score"] is None
            assert record["control_status"] == "requested-but-unrun"
            assert record["confirmation_context"]["state"] == "requested-but-unrun"
            assert record["claim_ceiling"] == CLAIM_CEILING

    assert len(result_ids) == 4


def test_inputs_contain_only_invented_records_without_sequences_or_private_paths() -> None:
    combined = "\n".join(path.read_text(encoding="utf-8") for path in INPUTS)
    lowered = combined.lower()

    assert "sequence" not in lowered
    assert "accession" not in lowered
    assert "provider" not in lowered
    assert "/users/" not in lowered
    assert "/volumes/" not in lowered
    assert "mucin" not in lowered
    assert "clinical" not in lowered
    assert "credential" not in lowered
    assert "synthetic" in lowered


def test_merge_cli_preserves_run_and_control_scope(tmp_path: Path) -> None:
    output = tmp_path / "merged-screening-results.json"
    before = {path: path.read_bytes() for path in INPUTS}
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "surface_atlas",
            "merge-screens",
            *(str(path) for path in INPUTS),
            "--output",
            str(output),
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PYTHONPATH": os.pathsep.join(
                filter(
                    None,
                    [str(Path(__file__).parents[1] / "src"), os.environ.get("PYTHONPATH", "")],
                )
            ),
        },
    )

    assert result.returncode == 0, result.stderr
    merged = read(output)
    assert merged["schema_version"] == SCHEMA_VERSION
    assert merged["atlas_id"] == "synthetic-surface-atlas"
    assert merged["claim_ceiling"] == CLAIM_CEILING
    assert merged["summary"] == {
        "execution_complete": False,
        "record_count": 4,
        "run_count": 2,
    }
    assert len(merged["records"]) == 4
    assert len(merged["source_runs"]) == 2
    assert len(merged["confirmation_contexts"]) == 2
    assert {run["run_id"] for run in merged["source_runs"]} == {
        "synthetic-screen-run-a",
        "synthetic-screen-run-b",
    }
    assert {
        record["screening_result_id"] for record in merged["records"]
    } == {
        "SCR-EMBER-A-PROSPECTIVE",
        "SCR-EMBER-A-REFERENCE",
        "SCR-EMBER-B-PROSPECTIVE",
        "SCR-EMBER-B-REFERENCE",
    }
    for record in merged["records"]:
        assert record["execution_state"] == "planned"
        assert record["pose_score"] is None
        assert record["confirmation_context"]["state"] == "requested-but-unrun"
    assert {path: path.read_bytes() for path in INPUTS} == before
