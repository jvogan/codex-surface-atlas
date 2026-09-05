from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import surface_atlas.screening_merge as screening_merge
from surface_atlas.screening_merge import ScreeningMergeError, merge_screening_files


def collection(
    run_id: str,
    result_id: str,
    *,
    atlas_id: str = "fictional-atlas",
    plural_runs: bool = False,
    plural_contexts: bool = False,
) -> dict:
    run = {
        "run_id": run_id,
        "screen_id": f"screen-{run_id}",
        "execution_state": "partial",
        "route": "local-fictional-route",
    }
    record = {
        "screening_result_id": result_id,
        "run_id": run_id,
        "target_id": "T-FICTIONAL",
        "screen_role": "negative-control",
        "seed_observations": [
            {"seed": 7, "score": -4.5, "execution_state": "failed"}
        ],
        "control_status": "retained",
        "failure_reason": "synthetic failure",
    }
    value = {
        "schema_version": screening_merge.SCHEMA,
        "atlas_id": atlas_id,
        "claim_ceiling": screening_merge.CLAIM_CEILING,
        "normalized_at": f"normalized-{run_id}",
        "summary": {"execution_complete": False, "best_score": -4.5, "failed": 1},
        "records": [record],
    }
    if plural_runs:
        value["source_runs"] = [run]
    else:
        value["source_run"] = run
    context = {"protocol": f"protocol-{run_id}", "confirmation_state": "not-started"}
    if plural_contexts:
        value["confirmation_contexts"] = [{"run_id": run_id, **context}]
    else:
        value["confirmation_context"] = context
    return value


def write(path: Path, value: object) -> bytes:
    data = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    path.write_bytes(data)
    return data


def test_merge_preserves_records_and_run_metadata_without_score_aggregation(
    tmp_path: Path,
) -> None:
    first_value = collection("run-one", "result-one")
    second_value = collection(
        "run-two", "result-two", plural_runs=True, plural_contexts=True
    )
    first_value["warnings"] = ["fictional warning"]
    second_value["provenance_extension"] = {"source": "synthetic"}
    first = tmp_path / "opaque-a.json"
    second = tmp_path / "opaque-b.json"
    first_bytes = write(first, first_value)
    second_bytes = write(second, second_value)

    first_output = tmp_path / "merged-a.json"
    second_output = tmp_path / "merged-b.json"
    result = merge_screening_files([first, second], first_output)
    merge_screening_files([first, second], second_output)
    merged = json.loads(first_output.read_text(encoding="utf-8"))

    assert first_output.read_bytes() == second_output.read_bytes()
    assert merged["source_runs"] == [first_value["source_run"], second_value["source_runs"][0]]
    assert merged["records"] == first_value["records"] + second_value["records"]
    assert merged["confirmation_contexts"] == [
        {
            "run_id": "run-one",
            "screen_id": "screen-run-one",
            **first_value["confirmation_context"],
        },
        second_value["confirmation_contexts"][0],
    ]
    assert merged["summary"] == {
        "execution_complete": False,
        "record_count": 2,
        "run_count": 2,
    }
    assert "best_score" not in merged["summary"]
    assert merged["input_summaries"] == [first_value["summary"], second_value["summary"]]
    assert merged["input_normalized_at"] == [
        first_value["normalized_at"],
        second_value["normalized_at"],
    ]
    assert merged["input_collections"] == [
        {
            "input_ordinal": 1,
            "sha256": hashlib.sha256(first_bytes).hexdigest(),
            "bytes": len(first_bytes),
        },
        {
            "input_ordinal": 2,
            "sha256": hashlib.sha256(second_bytes).hexdigest(),
            "bytes": len(second_bytes),
        },
    ]
    assert set(merged["input_collections"][0]) == {"input_ordinal", "sha256", "bytes"}
    assert merged["input_metadata"] == [
        {
            "input_ordinal": 1,
            "envelope": {key: value for key, value in first_value.items() if key != "records"},
        },
        {
            "input_ordinal": 2,
            "envelope": {key: value for key, value in second_value.items() if key != "records"},
        },
    ]
    assert all("records" not in item["envelope"] for item in merged["input_metadata"])
    assert result.sha256 == hashlib.sha256(first_output.read_bytes()).hexdigest()
    assert result.record_count == 2


def test_nested_merge_retains_original_lineage_and_unknown_metadata(tmp_path: Path) -> None:
    first_value = collection("run-one", "result-one")
    second_value = collection("run-two", "result-two")
    third_value = collection("run-three", "result-three")
    first_value["warnings"] = [{"code": "fictional-warning", "detail": "review later"}]
    second_value["provenance_extension"] = {
        "tool": "synthetic-tool",
        "receipt": {"state": "recorded"},
    }
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    third = tmp_path / "third.json"
    write(first, first_value)
    write(second, second_value)
    write(third, third_value)
    first_merge = tmp_path / "first-merge.json"
    final_merge = tmp_path / "final-merge.json"

    merge_screening_files([first, second], first_merge)
    first_merged_value = json.loads(first_merge.read_text(encoding="utf-8"))
    merge_screening_files([first_merge, third], final_merge)
    final_value = json.loads(final_merge.read_text(encoding="utf-8"))

    nested_envelope = final_value["input_metadata"][0]["envelope"]
    assert nested_envelope == {
        key: value for key, value in first_merged_value.items() if key != "records"
    }
    assert nested_envelope["input_collections"] == first_merged_value["input_collections"]
    assert nested_envelope["input_summaries"] == first_merged_value["input_summaries"]
    assert nested_envelope["input_normalized_at"] == first_merged_value["input_normalized_at"]
    assert nested_envelope["input_metadata"][0]["envelope"]["warnings"] == first_value["warnings"]
    assert (
        nested_envelope["input_metadata"][1]["envelope"]["provenance_extension"]
        == second_value["provenance_extension"]
    )
    assert final_value["records"] == (
        first_value["records"] + second_value["records"] + third_value["records"]
    )
    assert "records" not in nested_envelope


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("atlas", "different atlas_id"),
        ("run", "duplicate run_id"),
        ("result", "duplicate screening_result_id"),
        ("record-scope", "outside its source runs"),
        ("record-run-type", "requires a non-empty run_id"),
        ("context-scope", "confirmation context points outside"),
        ("context-screen", "screen_id does not match"),
        ("source-conflict", "conflicting source-run fields"),
        ("context-conflict", "conflicting confirmation-context fields"),
        ("claim", "unsupported claim_ceiling"),
    ],
)
def test_merge_rejects_conflicts(tmp_path: Path, case: str, message: str) -> None:
    first_value = collection("run-one", "result-one")
    second_value = collection("run-two", "result-two")
    if case == "atlas":
        second_value["atlas_id"] = "other-atlas"
    elif case == "run":
        second_value["source_run"]["run_id"] = "run-one"
        second_value["records"][0]["run_id"] = "run-one"
    elif case == "result":
        second_value["records"][0]["screening_result_id"] = "result-one"
    elif case == "record-scope":
        second_value["records"][0]["run_id"] = "run-one"
    elif case == "record-run-type":
        second_value["records"][0]["run_id"] = ["run-two"]
    elif case == "context-scope":
        second_value["confirmation_context"]["run_id"] = "run-one"
    elif case == "context-screen":
        second_value["confirmation_context"]["screen_id"] = "another-screen"
    elif case == "source-conflict":
        second_value["source_runs"] = [second_value["source_run"]]
    elif case == "context-conflict":
        second_value["confirmation_contexts"] = [
            {"run_id": "run-two", "confirmation_state": "not-started"}
        ]
    else:
        second_value["claim_ceiling"] = "observed"
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    write(first, first_value)
    write(second, second_value)
    output = tmp_path / "merged.json"

    with pytest.raises(ScreeningMergeError, match=message):
        merge_screening_files([first, second], output)

    assert not output.exists()


def test_merge_execution_complete_is_present_only_when_known(tmp_path: Path) -> None:
    first_value = collection("run-one", "result-one")
    second_value = collection("run-two", "result-two")
    first_value["summary"]["execution_complete"] = True
    second_value["summary"].pop("execution_complete")
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    write(first, first_value)
    write(second, second_value)

    merge_screening_files([first, second], tmp_path / "merged.json")
    merged = json.loads((tmp_path / "merged.json").read_text(encoding="utf-8"))

    assert "execution_complete" not in merged["summary"]


@pytest.mark.parametrize("unsafe", ["utf8", "nan", "duplicate-key", "directory"])
def test_merge_rejects_unsafe_input_formats(tmp_path: Path, unsafe: str) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    write(first, collection("run-one", "result-one"))
    if unsafe == "utf8":
        second.write_bytes(b"\xff\xfe")
    elif unsafe == "nan":
        text = json.dumps(collection("run-two", "result-two"))
        second.write_text(text.replace('"records":', '"unsafe": NaN, "records":'), encoding="utf-8")
    elif unsafe == "duplicate-key":
        text = json.dumps(collection("run-two", "result-two"))
        second.write_text(text.replace("{", '{"atlas_id":"duplicate",', 1), encoding="utf-8")
    else:
        second.mkdir()

    with pytest.raises(ScreeningMergeError):
        merge_screening_files([first, second], tmp_path / "merged.json")


def test_merge_rejects_symlink_input(tmp_path: Path) -> None:
    first = tmp_path / "first.json"
    real_second = tmp_path / "real-second.json"
    linked_second = tmp_path / "linked-second.json"
    write(first, collection("run-one", "result-one"))
    write(real_second, collection("run-two", "result-two"))
    linked_second.symlink_to(real_second)

    with pytest.raises(ScreeningMergeError, match="must not be a symlink"):
        merge_screening_files([first, linked_second], tmp_path / "merged.json")


def test_merge_refuses_output_alias_or_existing_file(tmp_path: Path) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    first_bytes = write(first, collection("run-one", "result-one"))
    write(second, collection("run-two", "result-two"))

    with pytest.raises(ScreeningMergeError, match="must not alias"):
        merge_screening_files([first, second], first)
    assert first.read_bytes() == first_bytes

    output = tmp_path / "existing.json"
    output.write_text("keep me", encoding="utf-8")
    with pytest.raises(ScreeningMergeError, match="already exists"):
        merge_screening_files([first, second], output)
    assert output.read_text(encoding="utf-8") == "keep me"


def test_atomic_publish_failure_removes_temporary_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    write(first, collection("run-one", "result-one"))
    write(second, collection("run-two", "result-two"))
    output = tmp_path / "merged.json"

    def fail_link(*args: object, **kwargs: object) -> None:
        raise OSError("synthetic link failure")

    monkeypatch.setattr(screening_merge.os, "link", fail_link)
    with pytest.raises(ScreeningMergeError, match="publish output atomically"):
        merge_screening_files([first, second], output)

    assert not output.exists()
    assert not list(tmp_path.glob(".surface-atlas-merge-*"))


def test_merge_screens_cli_emits_machine_readable_result(tmp_path: Path) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    output = tmp_path / "merged.json"
    write(first, collection("run-one", "result-one"))
    write(second, collection("run-two", "result-two"))

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "surface_atlas",
            "merge-screens",
            str(first),
            str(second),
            "--output",
            str(output),
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["record_count"] == 2
    assert result["run_count"] == 2
    assert result["network_or_provider_calls"] is False
    assert output.is_file()
