"""Safely merge screening collections without combining their scores."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


SCHEMA = "codex-surface-screening-result-collection/v0.1"
CLAIM_CEILING = "computational-screening-hypothesis"
SAFE_ATLAS_ID = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")


class ScreeningMergeError(ValueError):
    """Raised when screening collections cannot be merged safely."""


class _DuplicateKey(ValueError):
    pass


@dataclass(frozen=True)
class _LoadedInput:
    ordinal: int
    value: dict[str, Any]
    sha256: str
    byte_count: int


@dataclass(frozen=True)
class ScreeningMergeResult:
    output: str
    sha256: str
    bytes: int
    run_count: int
    record_count: int
    network_or_provider_calls: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "output": self.output,
            "sha256": self.sha256,
            "bytes": self.bytes,
            "run_count": self.run_count,
            "record_count": self.record_count,
            "network_or_provider_calls": self.network_or_provider_calls,
        }


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ScreeningMergeError(message)


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise _DuplicateKey(key)
        value[key] = item
    return value


def _reject_nonfinite_constant(value: str) -> None:
    raise ScreeningMergeError(f"non-finite number {value}")


def _contains_nonfinite(value: Any) -> bool:
    if isinstance(value, float):
        return not math.isfinite(value)
    if isinstance(value, list):
        return any(_contains_nonfinite(item) for item in value)
    if isinstance(value, dict):
        return any(_contains_nonfinite(item) for item in value.values())
    return False


def _read_input(path: Path, ordinal: int) -> _LoadedInput:
    label = f"input {ordinal}"
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise ScreeningMergeError(f"{label} is missing or unreadable") from exc
    _require(not stat.S_ISLNK(metadata.st_mode), f"{label} must not be a symlink")
    _require(stat.S_ISREG(metadata.st_mode), f"{label} must be a regular file")

    flags = (
        os.O_RDONLY
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ScreeningMergeError(f"{label} is missing or unreadable") from exc
    try:
        with os.fdopen(descriptor, "rb") as handle:
            _require(stat.S_ISREG(os.fstat(handle.fileno()).st_mode), f"{label} must be a regular file")
            data = handle.read()
    except OSError as exc:
        raise ScreeningMergeError(f"{label} could not be read") from exc

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ScreeningMergeError(f"{label} is not valid UTF-8") from exc
    try:
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite_constant,
        )
    except _DuplicateKey as exc:
        raise ScreeningMergeError(f"{label} contains a duplicate JSON key") from exc
    except json.JSONDecodeError as exc:
        raise ScreeningMergeError(
            f"{label} contains invalid JSON at line {exc.lineno}, column {exc.colno}"
        ) from exc
    _require(not _contains_nonfinite(value), f"{label} contains a non-finite number")
    _require(isinstance(value, dict), f"{label} must contain a JSON object")
    return _LoadedInput(
        ordinal=ordinal,
        value=value,
        sha256=hashlib.sha256(data).hexdigest(),
        byte_count=len(data),
    )


def _source_runs(collection: dict[str, Any], ordinal: int) -> list[dict[str, Any]]:
    has_one = "source_run" in collection
    has_many = "source_runs" in collection
    _require(not (has_one and has_many), f"input {ordinal} has conflicting source-run fields")
    if has_one:
        run = collection["source_run"]
        _require(isinstance(run, dict), f"input {ordinal} source_run must be an object")
        return [run]
    _require(has_many, f"input {ordinal} requires source_run or source_runs")
    runs = collection["source_runs"]
    _require(
        isinstance(runs, list) and bool(runs),
        f"input {ordinal} source_runs must be a non-empty array",
    )
    _require(
        all(isinstance(run, dict) for run in runs),
        f"input {ordinal} source_runs must contain only objects",
    )
    return runs


def _confirmation_contexts(
    collection: dict[str, Any], runs: list[dict[str, Any]], runs_by_id: dict[str, dict[str, Any]], ordinal: int
) -> list[dict[str, Any]]:
    has_one = "confirmation_context" in collection
    has_many = "confirmation_contexts" in collection
    _require(not (has_one and has_many), f"input {ordinal} has conflicting confirmation-context fields")
    if has_many:
        contexts = collection["confirmation_contexts"]
        _require(
            isinstance(contexts, list),
            f"input {ordinal} confirmation_contexts must be an array",
        )
        _require(
            all(isinstance(context, dict) for context in contexts),
            f"input {ordinal} confirmation_contexts must contain only objects",
        )
        normalized = contexts
    elif has_one:
        context = collection["confirmation_context"]
        if context is None:
            return []
        _require(
            isinstance(context, dict),
            f"input {ordinal} confirmation_context must be an object",
        )
        _require(
            len(runs) == 1,
            f"input {ordinal} confirmation_context requires exactly one source run",
        )
        scoped = dict(context)
        scoped.setdefault("run_id", runs[0]["run_id"])
        if "screen_id" not in scoped and isinstance(runs[0].get("screen_id"), str):
            scoped["screen_id"] = runs[0]["screen_id"]
        normalized = [scoped]
    else:
        return []

    for context in normalized:
        run_id = context.get("run_id")
        _require(
            isinstance(run_id, str) and run_id and run_id == run_id.strip(),
            f"input {ordinal} confirmation context requires a non-empty run_id",
        )
        _require(
            run_id in runs_by_id,
            f"input {ordinal} confirmation context points outside its source runs",
        )
        source_screen_id = runs_by_id[run_id].get("screen_id")
        if source_screen_id is not None:
            _require(
                context.get("screen_id", source_screen_id) == source_screen_id,
                f"input {ordinal} confirmation screen_id does not match its source run",
            )
    return normalized


def _merge_loaded(inputs: list[_LoadedInput]) -> dict[str, Any]:
    atlas_id: str | None = None
    merged_runs: list[dict[str, Any]] = []
    merged_contexts: list[dict[str, Any]] = []
    merged_records: list[dict[str, Any]] = []
    input_summaries: list[dict[str, Any]] = []
    input_normalized_at: list[str | None] = []
    execution_states: list[bool | None] = []
    all_run_ids: set[str] = set()
    all_record_ids: set[str] = set()

    for loaded in inputs:
        ordinal = loaded.ordinal
        collection = loaded.value
        _require(collection.get("schema_version") == SCHEMA, f"input {ordinal} has the wrong schema")
        candidate_atlas_id = collection.get("atlas_id")
        _require(
            isinstance(candidate_atlas_id, str) and SAFE_ATLAS_ID.fullmatch(candidate_atlas_id) is not None,
            f"input {ordinal} has an invalid atlas_id",
        )
        if atlas_id is None:
            atlas_id = candidate_atlas_id
        else:
            _require(candidate_atlas_id == atlas_id, "input collections have different atlas_id values")
        _require(
            collection.get("claim_ceiling") == CLAIM_CEILING,
            f"input {ordinal} has an unsupported claim_ceiling",
        )
        summary = collection.get("summary")
        _require(isinstance(summary, dict), f"input {ordinal} summary must be an object")
        execution_state = summary.get("execution_complete")
        _require(
            execution_state is None or isinstance(execution_state, bool),
            f"input {ordinal} summary.execution_complete must be a boolean or null",
        )
        normalized_at = collection.get("normalized_at")
        _require(
            normalized_at is None or isinstance(normalized_at, str),
            f"input {ordinal} normalized_at must be a string or null",
        )
        input_summaries.append(summary)
        input_normalized_at.append(normalized_at)
        execution_states.append(execution_state)

        runs = _source_runs(collection, ordinal)
        input_runs_by_id: dict[str, dict[str, Any]] = {}
        for run in runs:
            run_id = run.get("run_id")
            _require(
                isinstance(run_id, str) and run_id and run_id == run_id.strip(),
                f"input {ordinal} source run requires a non-empty run_id",
            )
            _require(run_id not in all_run_ids, "duplicate run_id across input collections")
            all_run_ids.add(run_id)
            input_runs_by_id[run_id] = run
            merged_runs.append(run)

        merged_contexts.extend(
            _confirmation_contexts(collection, runs, input_runs_by_id, ordinal)
        )
        records = collection.get("records")
        _require(isinstance(records, list), f"input {ordinal} records must be an array")
        for index, record in enumerate(records):
            _require(
                isinstance(record, dict),
                f"input {ordinal} records[{index}] must be an object",
            )
            record_id = record.get("screening_result_id")
            _require(
                isinstance(record_id, str) and record_id and record_id == record_id.strip(),
                f"input {ordinal} records[{index}] requires screening_result_id",
            )
            _require(
                record_id not in all_record_ids,
                "duplicate screening_result_id across input collections",
            )
            record_run_id = record.get("run_id")
            _require(
                isinstance(record_run_id, str)
                and record_run_id
                and record_run_id == record_run_id.strip(),
                f"input {ordinal} records[{index}] requires a non-empty run_id",
            )
            _require(
                record_run_id in input_runs_by_id,
                f"input {ordinal} records[{index}] points outside its source runs",
            )
            all_record_ids.add(record_id)
            merged_records.append(record)

    merged_summary: dict[str, Any] = {
        "record_count": len(merged_records),
        "run_count": len(merged_runs),
    }
    if any(state is False for state in execution_states):
        merged_summary["execution_complete"] = False
    elif execution_states and all(state is True for state in execution_states):
        merged_summary["execution_complete"] = True

    return {
        "schema_version": SCHEMA,
        "atlas_id": atlas_id,
        "claim_ceiling": CLAIM_CEILING,
        "source_runs": merged_runs,
        "confirmation_contexts": merged_contexts,
        "summary": merged_summary,
        "input_summaries": input_summaries,
        "input_normalized_at": input_normalized_at,
        "input_collections": [
            {
                "input_ordinal": loaded.ordinal,
                "sha256": loaded.sha256,
                "bytes": loaded.byte_count,
            }
            for loaded in inputs
        ],
        "input_metadata": [
            {
                "input_ordinal": loaded.ordinal,
                "envelope": {
                    key: value for key, value in loaded.value.items() if key != "records"
                },
            }
            for loaded in inputs
        ],
        "records": merged_records,
    }


def _canonical_path(path: Path, label: str) -> str:
    try:
        return os.path.normcase(str(path.resolve(strict=False)))
    except (OSError, RuntimeError) as exc:
        raise ScreeningMergeError(f"{label} has an invalid path") from exc


def merge_screening_collections(inputs: Iterable[str | os.PathLike[str]]) -> dict[str, Any]:
    """Validate and merge screening collections in the supplied order."""

    paths = [Path(path) for path in inputs]
    _require(len(paths) >= 2, "at least two screening collections are required")
    canonical = [
        _canonical_path(path, f"input {ordinal}")
        for ordinal, path in enumerate(paths, start=1)
    ]
    _require(len(canonical) == len(set(canonical)), "input paths must be distinct")
    loaded = [_read_input(path, ordinal) for ordinal, path in enumerate(paths, start=1)]
    return _merge_loaded(loaded)


def _serialize(value: dict[str, Any]) -> bytes:
    try:
        text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError) as exc:  # pragma: no cover - inputs are checked above
        raise ScreeningMergeError("merged output is not valid JSON") from exc
    return (text + "\n").encode("utf-8")


def _write_new_file(output: Path, data: bytes) -> None:
    if os.path.lexists(output):
        raise ScreeningMergeError("output already exists")
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".surface-atlas-merge-", dir=output.parent
        )
    except OSError as exc:
        raise ScreeningMergeError("could not prepare the output directory") from exc
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, output, follow_symlinks=False)
        except FileExistsError as exc:
            raise ScreeningMergeError("output already exists") from exc
        except OSError as exc:
            raise ScreeningMergeError("could not publish output atomically") from exc
    finally:
        temporary.unlink(missing_ok=True)


def merge_screening_files(
    inputs: Iterable[str | os.PathLike[str]], output: str | os.PathLike[str]
) -> ScreeningMergeResult:
    """Merge screening inputs and atomically create one new JSON file."""

    paths = [Path(path) for path in inputs]
    output_path = Path(output)
    output_key = _canonical_path(output_path, "output")
    input_keys = {
        _canonical_path(path, f"input {ordinal}")
        for ordinal, path in enumerate(paths, start=1)
    }
    _require(output_key not in input_keys, "output must not alias an input")
    merged = merge_screening_collections(paths)
    data = _serialize(merged)
    _write_new_file(output_path, data)
    return ScreeningMergeResult(
        output=str(output_path),
        sha256=hashlib.sha256(data).hexdigest(),
        bytes=len(data),
        run_count=len(merged["source_runs"]),
        record_count=len(merged["records"]),
    )


__all__ = [
    "CLAIM_CEILING",
    "SCHEMA",
    "ScreeningMergeError",
    "ScreeningMergeResult",
    "merge_screening_collections",
    "merge_screening_files",
]
