"""Deterministic local evidence intake and census reconciliation.

Source plugins retrieve records; this module joins explicitly reviewed stable
identities and dispositions. It never infers surface display from expression.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any
from datetime import datetime, timezone
from urllib.parse import urlsplit

from .export import _rename_directory_exclusive
from .schemas import COLLECTION_SCHEMAS, SEARCH_LEDGER_SCHEMA

SNAPSHOT_SCHEMA = "codex-surface-evidence-snapshot/v0.1"
INTAKE_SCHEMA = "codex-surface-evidence-intake/v0.1"
IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,119}$")
COUNT_KEYS = {"raw_records", "duplicate_records", "normalized_discovered_entities", "surface_targets", "excluded_from_surface_universe", "unresolved_records"}
DISPOSITIONS = {"surface-target", "excluded-from-surface-universe", "unresolved"}


class EvidenceError(ValueError):
    """Evidence does not meet the portable intake contract."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceError(message)


def _no_constant(value: str) -> None:
    raise EvidenceError("JSON numbers must be finite")


def _finite_float(value: str) -> float:
    result = float(value)
    _require(math.isfinite(result), "JSON numbers must be finite")
    return result


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        _require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _read(path: Path) -> tuple[dict[str, Any], bytes]:
    _require(not path.is_symlink() and path.is_file(), f"{path.name}: expected a regular file")
    _require(path.stat().st_size <= 16 * 1024 * 1024, f"{path.name}: exceeds 16 MiB intake limit")
    try:
        with path.open("rb") as handle:
            data = handle.read(16 * 1024 * 1024 + 1)
        _require(len(data) <= 16 * 1024 * 1024, f"{path.name}: exceeds 16 MiB intake limit")
        value = json.loads(data.decode("utf-8"), parse_constant=_no_constant, parse_float=_finite_float, object_pairs_hook=_unique_object)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"{path.name}: cannot read a UTF-8 JSON object") from exc
    _require(isinstance(value, dict), f"{path.name}: expected a JSON object")
    return value, data


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value == value.strip() and len(value) <= 20000 and not any(ord(char) < 32 and char not in "\n\t" for char in value)


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def validate_snapshot(value: dict[str, Any]) -> None:
    _require(isinstance(value, dict) and set(value) == {"schema_version", "data_kind", "source", "records"},
             "snapshot requires only schema_version, data_kind, source, records")
    _require(value.get("schema_version") == SNAPSHOT_SCHEMA, "unsupported evidence snapshot schema")
    _require(isinstance(value.get("data_kind"), str) and value["data_kind"] in {"public-source", "synthetic"}, "snapshot data_kind must be public-source or synthetic")
    source = value.get("source")
    _require(isinstance(source, dict), "snapshot source is required")
    _require(not set(source) - {"source_id", "query_id", "title", "query", "source_class", "retrieved_at", "license", "status", "url", "limitation"},
             "unknown snapshot source field")
    for key in ("source_id", "query_id", "title", "query", "source_class", "retrieved_at", "license"):
        _require(_text(source.get(key)), f"snapshot source.{key} is required")
    for key in ("source_id", "query_id"):
        _require(IDENTIFIER.fullmatch(source[key]) is not None, f"source.{key} must be a portable identifier")
    for key in ("url", "limitation"):
        _require(key not in source or _text(source[key]), f"source.{key} must be nonempty text when supplied")
    try:
        retrieved = datetime.fromisoformat(source["retrieved_at"].replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvidenceError("source.retrieved_at must be an ISO date-time") from exc
    _require(retrieved.tzinfo is not None, "source.retrieved_at must include a timezone")
    _require(isinstance(source.get("status"), str) and source["status"] in {"complete", "partial", "blocked"}, "source status must be complete, partial, or blocked")
    _require(_text(source.get("limitation")) if source["status"] != "complete" else True,
             "partial or blocked source needs a limitation")
    if value["data_kind"] == "public-source" or "url" in source:
        url = source.get("url", "")
        try:
            parsed = urlsplit(url)
            valid_url = parsed.scheme in {"http", "https"} and bool(parsed.hostname) and parsed.username is None and not any(char.isspace() for char in url)
        except ValueError:
            valid_url = False
        _require(valid_url, "public source needs a valid HTTP(S) source URL without credentials")
    records = value.get("records")
    _require(isinstance(records, list), "snapshot records must be an array")
    seen: set[str] = set()
    for record in records:
        _require(isinstance(record, dict), "snapshot records must contain objects")
        _require(not set(record) - {"record_id", "entity_id", "preferred_name", "reason", "locator", "disposition", "identifiers", "target"},
                 "unknown evidence record field")
        for key in ("record_id", "entity_id", "preferred_name", "reason", "locator"):
            _require(_text(record.get(key)), f"evidence record.{key} is required")
        for key in ("record_id", "entity_id"):
            _require(IDENTIFIER.fullmatch(record[key]) is not None, f"record.{key} must be a portable identifier")
        _require(record["record_id"] not in seen, "duplicate source record_id")
        seen.add(record["record_id"])
        _require(isinstance(record.get("disposition"), str) and record["disposition"] in DISPOSITIONS, "reviewed evidence disposition is required")
        identifiers = record.get("identifiers")
        _require(isinstance(identifiers, dict) and bool(identifiers) and all(_text(k) and _text(v) for k, v in identifiers.items()),
                 "evidence identities require nonempty stable identifier strings")
        if record["disposition"] == "surface-target":
            target = record.get("target")
            _require(isinstance(target, dict) and isinstance(target.get("target_id"), str) and IDENTIFIER.fullmatch(target["target_id"]) is not None, "retained evidence needs a target record with target_id")
            _require(isinstance(target.get("structure_tier"), str) and target["structure_tier"] in {"retained-unmodeled", "structure-a", "structure-b", "structure-c"},
                     "retained target needs an explicit structure_tier")
            _require(_text(target.get("surface_evidence", {}).get("basis")) if isinstance(target.get("surface_evidence"), dict) else False,
                     "retention requires a reviewed surface-evidence basis; RNA alone is insufficient")
        else:
            _require("target" not in record, "only retained evidence may carry a target projection")


def compile_snapshots(paths: list[str | Path], atlas_id: str) -> dict[str, Any]:
    _require(bool(paths), "at least one source snapshot is required")
    _require(isinstance(atlas_id, str) and re.fullmatch(r"[a-z0-9][a-z0-9-]{2,63}", atlas_id) is not None,
             "atlas_id must be a portable identifier of 3-64 characters")
    loaded: list[tuple[dict[str, Any], bytes]] = []
    query_ids: set[str] = set()
    for path in paths:
        value, data = _read(Path(path))
        validate_snapshot(value)
        source = value["source"]
        _require(source["query_id"] not in query_ids, "duplicate query_id across evidence snapshots")
        query_ids.add(source["query_id"])
        loaded.append((value, data))
    # Input enumeration must not change output identities, ordering, or decisions.
    loaded.sort(key=lambda pair: pair[0]["source"]["query_id"])
    kinds = {value["data_kind"] for value, _ in loaded}
    _require(len(kinds) == 1, "synthetic and public evidence must be compiled separately")
    data_kind = next(iter(kinds))
    entities: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {}
    identity_owner: dict[tuple[str, str], str] = {}
    sources, snapshots = [], {}
    for value, data in loaded:
        source = value["source"]
        digest = hashlib.sha256(data).hexdigest()
        relative = f"evidence/snapshots/{digest}.json"
        snapshots[relative] = data
        sources.append({**copy.deepcopy(source), "records": len(value["records"]),
                        "artifact": {"path": relative, "sha256": digest, "bytes": len(data)}})
        for row in value["records"]:
            for namespace, identifier in row["identifiers"].items():
                key = (namespace, identifier)
                _require(key not in identity_owner or identity_owner[key] == row["entity_id"],
                         "the same stable identifier is assigned to different entity IDs")
                identity_owner[key] = row["entity_id"]
            ref = {"source_id": source["source_id"], "query_id": source["query_id"], "title": source["title"],
                   "url": source.get("url"), "retrieved_at": source["retrieved_at"], "record_id": row["record_id"],
                   "locator": row["locator"], "artifact": {"path": relative, "sha256": digest, "bytes": len(data)}}
            entities.setdefault(row["entity_id"], []).append((row, ref))
    discovered, targets, exclusions = [], [], []
    target_owners: dict[str, str] = {}
    for entity_id, rows in sorted(entities.items()):
        identities: dict[str, str] = {}
        for row, _ in rows:
            for namespace, identifier in row["identifiers"].items():
                _require(namespace not in identities or identities[namespace] == identifier,
                         f"conflicting stable identities for entity {entity_id}")
                identities[namespace] = identifier
        decisions = {row["disposition"] for row, _ in rows}
        disposition = next(iter(decisions)) if len(decisions) == 1 else "unresolved"
        claim = "synthetic illustration" if data_kind == "synthetic" else "reviewed source evidence; not efficacy or safety"
        record = {"entity_id": entity_id, "preferred_name": rows[0][0]["preferred_name"], "identifiers": identities,
                  "surface_disposition": disposition, "source_refs": [ref for _, ref in rows], "claim_ceiling": claim,
                  "reasons": [row["reason"] for row, _ in rows]}
        if len(decisions) > 1:
            record["resolution_required"] = "Source dispositions conflict; review before retaining or excluding this entity."
        if disposition == "surface-target":
            candidates = [row["target"] for row, _ in rows]
            _require(all(candidate == candidates[0] for candidate in candidates),
                     f"conflicting target projections for {entity_id}; reconcile explicitly before intake")
            target = copy.deepcopy(candidates[0])
            target_id = target["target_id"]
            _require(target_id not in target_owners, "different entities share a target_id")
            target_owners[target_id] = entity_id
            target.update({"identifiers": identities, "source_refs": record["source_refs"], "claim_ceiling": claim})
            target.setdefault("preferred_name", record["preferred_name"])
            record["target_id"] = target_id
            targets.append(target)
        elif disposition == "excluded-from-surface-universe":
            exclusion_id = "X-" + hashlib.sha256(entity_id.encode()).hexdigest()[:16]
            record["exclusion_id"] = exclusion_id
            exclusions.append({"exclusion_id": exclusion_id, "entity_id": entity_id,
                               "preferred_name": record["preferred_name"], "reason": "; ".join(record["reasons"]),
                               "source_refs": record["source_refs"], "claim_ceiling": claim})
        discovered.append(record)
    raw_count = sum(source["records"] for source in sources)
    counts = {"raw_records": raw_count, "duplicate_records": raw_count - len(discovered),
              "normalized_discovered_entities": len(discovered), "surface_targets": len(targets),
              "excluded_from_surface_universe": len(exclusions),
              "unresolved_records": sum(row["surface_disposition"] == "unresolved" for row in discovered)}
    complete = all(source["status"] == "complete" for source in sources)
    ledger = {"schema_version": SEARCH_LEDGER_SCHEMA, "atlas_id": atlas_id,
              "data_kind": data_kind, "evidence_intake": INTAKE_SCHEMA,
              "as_of": max(datetime.fromisoformat(source["retrieved_at"].replace("Z", "+00:00")) for source in sources).astimezone(timezone.utc).date().isoformat(),
              "coverage_state": "complete_within_recorded_scope" if complete else "partial",
              "planned_source_classes": sorted({source["source_class"] for source in sources}),
              "sources": sources, "counts": counts,
              "limitations": ["Completeness is limited to the supplied reviewed queries."] +
                             (["All tutorial observations are synthetic; no biological evidence is asserted."] if data_kind == "synthetic" else []) +
                             [source["limitation"] for source in sources if source.get("limitation")]}
    documents: dict[str, Any] = {"search-ledger.json": ledger}
    for filename, records in (("discovered-entities.json", discovered), ("targets.json", targets), ("excluded-targets.json", exclusions)):
        documents[filename] = {"schema_version": COLLECTION_SCHEMAS[filename], "atlas_id": atlas_id,
                               "data_kind": data_kind, "records": records}
    return {"documents": documents, "snapshots": snapshots, "counts": counts, "data_kind": data_kind}


def _managed_snapshot_paths(root: Path) -> set[str]:
    """Inspect only the flat hash-named managed namespace; never adopt other files."""
    directory = root / "evidence" / "snapshots"
    _require(not (root / "evidence").is_symlink() and not directory.is_symlink(), "unsafe managed snapshot directory")
    _require(not (root / "evidence").exists() or (root / "evidence").is_dir(), "unsafe managed snapshot parent directory shape")
    if not directory.exists():
        return set()
    _require(directory.is_dir(), "unsafe managed snapshot directory shape")
    paths = set()
    for path in directory.iterdir():
        _require(not path.is_symlink() and path.is_file() and re.fullmatch(r"[a-f0-9]{64}\.json", path.name) is not None,
                 "unsafe managed snapshot directory shape: expected only flat hash-named JSON snapshots")
        value, raw = _read(path)
        _require(hashlib.sha256(raw).hexdigest() == path.stem, "managed snapshot filename does not match its bytes")
        validate_snapshot(value)
        paths.add(path.relative_to(root).as_posix())
    return paths


def _reject_retained_snapshot_references(root: Path, removed: set[str], replaced: set[str], documents: dict[str, Any]) -> None:
    """Do not silently strand another record or document when replacing intake."""
    if not removed:
        return
    needles = [path.encode("utf-8") for path in removed]
    overlap = max(map(len, needles)) - 1
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        if not path.is_file() or relative in replaced or relative.startswith("evidence/snapshots/"):
            continue
        if path.suffix.lower() == ".json":
            try:
                decoded = json.dumps(json.loads(path.read_bytes()), ensure_ascii=False).encode("utf-8")
            except (ValueError, UnicodeError):
                decoded = b""  # Raw scanning below still covers non-JSON content.
            _require(not any(needle in decoded for needle in needles),
                     "a retained artifact references a removed managed snapshot; include that snapshot or explicitly update the reference before intake")
        with path.open("rb") as handle:
            tail = b""
            while chunk := handle.read(1024 * 1024):
                data = tail + chunk
                _require(not any(needle in data for needle in needles),
                         "a retained artifact references a removed managed snapshot; include that snapshot or explicitly update the reference before intake")
                tail = data[-overlap:]
    serialized = json.dumps(documents, ensure_ascii=False).encode("utf-8")
    _require(not any(needle in serialized for needle in needles),
             "new evidence references a removed managed snapshot; include that snapshot in the input set")


def ingest_evidence(inputs: list[str | Path], atlas_directory: str | Path, output_directory: str | Path) -> dict[str, Any]:
    """Create a new portable atlas snapshot; never modify the source workspace."""
    _require(not Path(atlas_directory).is_symlink(), "atlas workspace must not be a symlink")
    root, output = Path(atlas_directory).resolve(), Path(output_directory)
    _require(root.is_dir(), "atlas workspace does not exist")
    _require(not output.exists() and not output.is_symlink(), "output must be a new directory")
    _require(not output.resolve().is_relative_to(root), "output must be outside the source atlas")
    plan, _ = _read(root / "atlas-plan.json")
    _require(isinstance(plan.get("scope"), dict), "atlas plan needs an explicit scope object")
    compiled = compile_snapshots(inputs, plan.get("atlas_id"))
    _require(compiled["data_kind"] != "synthetic" or plan.get("data_kind") == "synthetic",
             "synthetic evidence requires an explicitly synthetic atlas plan")
    _require(plan.get("data_kind") != "synthetic" or compiled["data_kind"] == "synthetic",
             "public evidence requires a nonsynthetic atlas plan")
    _require(not (root / ".surface-atlas-local.json").exists(), "materialize external artifacts before portable evidence intake")
    for path in root.rglob("*"):
        _require(not path.is_symlink() and (path.is_file() or path.is_dir()), "atlas must contain only regular files and directories")
    inherited_snapshots = _managed_snapshot_paths(root)
    removed_snapshots = inherited_snapshots - set(compiled["snapshots"])
    _reject_retained_snapshot_references(root, removed_snapshots, set(compiled["documents"]), compiled["documents"])
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".evidence-", dir=output.parent))
    try:
        shutil.copytree(root, stage, dirs_exist_ok=True)
        inherited_directory = stage / "evidence" / "snapshots"
        if inherited_directory.exists():
            shutil.rmtree(inherited_directory)
        for relative, data in compiled["snapshots"].items():
            target = stage / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                _require(target.read_bytes() == data, "snapshot artifact collision")
            target.write_bytes(data)
        for filename, value in compiled["documents"].items():
            _write(stage / filename, value)
        plan["scope"]["coverage_claim"] = compiled["documents"]["search-ledger.json"]["coverage_state"]
        _write(stage / "atlas-plan.json", plan)
        from .validator import validate_workspace
        result = validate_workspace(stage)
        _require(result["valid"], "intake would create an invalid atlas: " + "; ".join(result["errors"]))
        _rename_directory_exclusive(stage, output)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return {"output": str(output), "counts": compiled["counts"], "data_kind": compiled["data_kind"],
            "network_or_provider_calls": False}


def _contains_projection(actual: Any, expected: Any) -> bool:
    """Allow later annotations while preserving every source-derived field."""
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(key in actual and _contains_projection(actual[key], value)
                                                for key, value in expected.items())
    if isinstance(expected, list):
        return isinstance(actual, list) and len(actual) == len(expected) and all(
            _contains_projection(left, right) for left, right in zip(actual, expected))
    return type(actual) is type(expected) and actual == expected


def has_managed_evidence(atlas_directory: str | Path, ledger: dict[str, Any] | None = None) -> bool:
    """Detect managed artifacts independently of editable ledger declarations.

    Call this from validation/report generation, so stripping artifact fields
    cannot downgrade a managed workspace to the legacy count-only path.
    """
    root = Path(atlas_directory)
    snapshots = root / "evidence" / "snapshots"
    if snapshots.exists() or snapshots.is_symlink():
        return True
    if ledger is None:
        ledger, _ = _read(root / "search-ledger.json")
    if "evidence_intake" in ledger:
        return True
    def references(value: Any) -> bool:
        if isinstance(value, dict):
            if isinstance(value.get("path"), str) and value["path"].startswith("evidence/snapshots/"):
                return True
            return any(references(item) for item in value.values())
        return isinstance(value, list) and any(references(item) for item in value)
    if references(ledger):
        return True
    for name in ("targets.json", "discovered-entities.json", "excluded-targets.json"):
        path = root / name
        if path.exists():
            value, _ = _read(path)
            if references(value):
                return True
    return False


def reconcile_evidence(atlas_directory: str | Path, output: str | Path | None = None) -> dict[str, Any]:
    """Check ledger against source snapshots and normalized census; optionally write a new ledger."""
    _require(not Path(atlas_directory).is_symlink(), "atlas workspace must not be a symlink")
    root = Path(atlas_directory).resolve()
    ledger, _ = _read(root / "search-ledger.json")
    discovered, _ = _read(root / "discovered-entities.json")
    targets, _ = _read(root / "targets.json")
    excluded, _ = _read(root / "excluded-targets.json")
    for value in (discovered, targets, excluded):
        _require(value.get("atlas_id") == ledger.get("atlas_id") and isinstance(value.get("records"), list)
                 and all(isinstance(row, dict) for row in value["records"]), "collection identity or records are invalid")
    _require(isinstance(ledger.get("counts"), dict) and isinstance(ledger.get("sources"), list), "ledger counts or sources are invalid")
    _require(COUNT_KEYS <= set(ledger["counts"]) and all(type(ledger["counts"][key]) is int and ledger["counts"][key] >= 0 for key in COUNT_KEYS),
             "ledger counts must be nonnegative integers")
    expected = dict(ledger.get("counts", {}))
    expected.update({"normalized_discovered_entities": len(discovered["records"]), "surface_targets": len(targets["records"]),
                     "excluded_from_surface_universe": len(excluded["records"]),
                     "unresolved_records": sum(row.get("surface_disposition") == "unresolved" for row in discovered["records"])})
    snapshot_sources = [source for source in ledger.get("sources", []) if isinstance(source, dict)
                        and isinstance(source.get("artifact"), dict)
                        and str(source["artifact"].get("path", "")).startswith("evidence/snapshots/")]
    if has_managed_evidence(root, ledger):
        _require(bool(snapshot_sources) and len(snapshot_sources) == len(ledger["sources"]),
                 "managed evidence requires snapshot artifacts on every source")
        managed_paths = _managed_snapshot_paths(root)
        referenced_paths = {source["artifact"].get("path") for source in snapshot_sources if isinstance(source["artifact"].get("path"), str)}
        _require(managed_paths == referenced_paths, "managed snapshot inventory contains unreferenced or missing source snapshots")
        paths = []
        for source in snapshot_sources:
            artifact = source["artifact"]
            path_text = artifact.get("path", "")
            _require(isinstance(path_text, str) and re.fullmatch(r"evidence/snapshots/[a-f0-9]{64}\.json", path_text) is not None,
                     "snapshot path must be within evidence/snapshots")
            path = root / path_text
            _require(path.resolve().is_relative_to(root) and not any(p.is_symlink() for p in [path, *path.parents] if p != root), "unsafe evidence snapshot path")
            value, raw = _read(path)
            _require(hashlib.sha256(raw).hexdigest() == artifact.get("sha256") == path.stem and type(artifact.get("bytes")) is int and len(raw) == artifact["bytes"], "evidence snapshot integrity mismatch")
            paths.append(path)
        rebuilt = compile_snapshots(paths, ledger["atlas_id"])
        for name, value in (("discovered-entities.json", discovered), ("targets.json", targets), ("excluded-targets.json", excluded)):
            _require(_contains_projection(value, rebuilt["documents"][name]), f"{name} differs from its evidence snapshot projection")
        rebuilt_ledger = rebuilt["documents"]["search-ledger.json"]
        for key in ("schema_version", "atlas_id", "data_kind", "as_of", "coverage_state", "planned_source_classes", "limitations", "evidence_intake"):
            _require(ledger.get(key) == rebuilt_ledger[key], f"ledger {key} differs from source snapshot projection")
        plan, _ = _read(root / "atlas-plan.json")
        _require(plan.get("atlas_id") == ledger["atlas_id"] and isinstance(plan.get("scope"), dict)
                 and plan["scope"].get("coverage_claim") == rebuilt_ledger["coverage_state"],
                 "atlas plan coverage or identity differs from source snapshots")
        _require((plan.get("data_kind") == "synthetic") == (rebuilt_ledger["data_kind"] == "synthetic"),
                 "atlas plan and snapshot data kinds differ")
        expected = rebuilt["counts"]
        _require(ledger.get("sources") == rebuilt["documents"]["search-ledger.json"]["sources"] and _contains_projection(ledger["sources"], rebuilt["documents"]["search-ledger.json"]["sources"]), "source rows differ from their snapshots")
    changes = {key: {"recorded": ledger.get("counts", {}).get(key), "expected": value}
               for key, value in expected.items() if ledger.get("counts", {}).get(key) != value}
    if output is not None:
        path = Path(output)
        _require(not path.exists() and not path.is_symlink(), "reconciled ledger output must not exist")
        payload = copy.deepcopy(ledger)
        payload["counts"] = expected
        data = json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, prefix=".evidence-ledger-", delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(data)
            os.link(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    return {"consistent": not changes, "changes": changes, "expected_counts": expected,
            "output": str(output) if output is not None else None, "network_or_provider_calls": False}
