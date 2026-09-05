#!/usr/bin/env python3
"""Validate a Codex Surface Atlas workspace without network access."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Any

from .screening_context import screening_run_contexts
from .schemas import REQUIRED_WORKSPACE_SCHEMAS
from .structure_preview import snapshot_record_errors


REQUIRED_FILES = REQUIRED_WORKSPACE_SCHEMAS
STAGE_STATES = {"pending", "in-progress", "blocked", "complete", "failed", "skipped"}
COVERAGE_STATES = {
    "planned",
    "in-progress",
    "complete_within_recorded_scope",
    "partial",
    "blocked",
}
CAPABILITY_STATES = {
    "catalogued",
    "visible",
    "bound",
    "preflight-passed",
    "scientifically-qualified",
    "executed",
    "artifact-validated",
}
SOURCE_STATES = {"planned", "running", "complete", "partial", "blocked", "not_applicable"}
SURFACE_DISPOSITIONS = {
    "pending",
    "surface-target",
    "excluded-from-surface-universe",
    "unresolved",
}
HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
SAFE_ATLAS_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")
REGISTERED_ARTIFACT_FIELDS = {
    "source_artifact",
    "source_record_artifact",
    "modification_sidecar_artifact",
}
REGISTRATION_RECEIPT_SCHEMA = "surface-atlas-supplied-library-registration-receipt/v1"
REGISTERED_LIBRARY_SCHEMA = "codex-surface-molecular-library/v0.1"
COLLECTION_ID_FIELDS = {
    "discovered-entities.json": "entity_id",
    "targets.json": "target_id",
    "excluded-targets.json": "exclusion_id",
    "interventions.json": "intervention_id",
    "molecular-library.json": "molecule_id",
    "screening-results.json": "screening_result_id",
    "structures.json": "structure_id",
    "opportunities.json": "opportunity_id",
    "capabilities.json": "capability_id",
}


def load_json(path: Path, errors: list[str]) -> Any:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        errors.append(f"missing required file: {path.name}")
        return None
    except UnicodeDecodeError:
        errors.append(f"invalid UTF-8 in {path.name}")
        return None
    except json.JSONDecodeError as exc:
        errors.append(f"invalid JSON in {path.name}: line {exc.lineno}, column {exc.colno}")
        return None
    if not isinstance(value, dict):
        errors.append(f"{path.name}: top level must be an object")
        return None
    return value


def record_id(record: dict[str, Any], filename: str) -> str | None:
    field = COLLECTION_ID_FIELDS[filename]
    value = record.get(field)
    if isinstance(value, str) and value and value == value.strip():
        return value
    return None


def validate_artifact(
    root: Path,
    external_root: Path | None,
    artifact: dict[str, Any],
    context: str,
    errors: list[str],
) -> None:
    path_text = artifact.get("path")
    if not isinstance(path_text, str) or not path_text:
        errors.append(f"{context}: artifact path is required")
        return
    pure = PurePosixPath(path_text)
    if pure.is_absolute() or ".." in pure.parts:
        errors.append(f"{context}: artifact path must be a safe relative path")
        return
    expected_hash = artifact.get("sha256")
    expected_bytes = artifact.get("bytes")
    if not isinstance(expected_hash, str) or not HASH_PATTERN.fullmatch(expected_hash):
        errors.append(f"{context}: artifact sha256 must contain 64 lowercase hex characters")
    if not isinstance(expected_bytes, int) or expected_bytes < 0:
        errors.append(f"{context}: artifact bytes must be a non-negative integer")
    if artifact.get("storage") == "external-artifact-root":
        if external_root is None:
            errors.append(f"{context}: external artifact requires a configured artifact root")
            return
        base = external_root
    else:
        base = root
    resolved = base.joinpath(*pure.parts).resolve()
    try:
        resolved.relative_to(base)
    except ValueError:
        errors.append(f"{context}: artifact path escapes its configured root")
        return
    if not resolved.is_file():
        errors.append(f"{context}: artifact file does not exist: {path_text}")
        return
    data = resolved.read_bytes()
    if isinstance(expected_bytes, int) and len(data) != expected_bytes:
        errors.append(f"{context}: artifact byte count does not match: {path_text}")
    if isinstance(expected_hash, str) and HASH_PATTERN.fullmatch(expected_hash):
        if hashlib.sha256(data).hexdigest() != expected_hash:
            errors.append(f"{context}: artifact hash does not match: {path_text}")


def validate_record_artifacts(
    root: Path,
    external_root: Path | None,
    record: dict[str, Any],
    context: str,
    errors: list[str],
) -> None:
    """Validate only the artifact fields in the public record contract.

    Registered library records use named artifact fields alongside the older
    ``artifacts`` array.  Walking JSON containers lets those fields remain
    nested in lineage/provenance objects, while requiring an explicit field
    name avoids treating arbitrary evidence payloads with ``path`` keys as
    files.
    """

    def visit(value: Any, value_context: str) -> None:
        if isinstance(value, list):
            for index, item in enumerate(value):
                visit(item, f"{value_context}[{index}]")
            return
        if not isinstance(value, dict):
            return
        for key, child in value.items():
            field_context = f"{value_context}.{key}"
            if key == "artifacts":
                if not isinstance(child, list):
                    errors.append(f"{field_context}: artifact collection must be an array")
                    continue
                for index, artifact in enumerate(child):
                    item_context = f"{field_context}[{index}]"
                    if isinstance(artifact, dict):
                        validate_artifact(root, external_root, artifact, item_context, errors)
                    else:
                        errors.append(f"{item_context}: artifact must be an object")
                continue
            if key in REGISTERED_ARTIFACT_FIELDS:
                if isinstance(child, dict):
                    validate_artifact(root, external_root, child, field_context, errors)
                else:
                    errors.append(f"{field_context}: artifact must be an object")
                continue
            visit(child, field_context)

    visit(record, context)


def validate_record_snapshots(
    root: Path,
    external_root: Path | None,
    record: dict[str, Any],
    context: str,
    errors: list[str],
) -> None:
    """Validate optional structure styling and the files it references."""
    errors.extend(snapshot_record_errors(record, context=context))
    snapshots: list[dict[str, Any]] = []
    value = record.get("structure_snapshot")
    if isinstance(value, dict):
        snapshots.append(value)
    values = record.get("structure_snapshots")
    if isinstance(values, list):
        snapshots.extend(item for item in values if isinstance(item, dict))
    for index, snapshot in enumerate(snapshots):
        snapshot_context = f"{context}.structure_snapshot[{index}]"
        coordinate_sources = snapshot.get("coordinate_sources")
        if not isinstance(coordinate_sources, list):
            coordinate_sources = []
        for source_index, source in enumerate(coordinate_sources):
            if isinstance(source, dict):
                validate_artifact(
                    root,
                    external_root,
                    source,
                    f"{snapshot_context}.coordinate_sources[{source_index}]",
                    errors,
                )
        sequence = snapshot.get("sequence_artifact")
        if isinstance(sequence, dict):
            validate_artifact(root, external_root, sequence, f"{snapshot_context}.sequence_artifact", errors)


def validate_registration_receipt(
    root: Path,
    external_root: Path | None,
    collection: dict[str, Any],
    errors: list[str],
) -> None:
    """Validate the supplied-library receipt referenced by a collection.

    The collection's receipt reference has no own hash.  Its receipt instead
    binds the original ``molecular-library.json`` bytes through
    ``output_artifact``; check both that binding and the artifact-root path.
    """

    reference = collection.get("registration_receipt")
    if reference is None:
        return
    context = "molecular-library.json:registration_receipt"
    if not isinstance(reference, dict):
        errors.append(f"{context}: must be an object")
        return
    path_text = reference.get("path")
    if not isinstance(path_text, str) or not path_text:
        errors.append(f"{context}: artifact path is required")
        return
    pure = PurePosixPath(path_text)
    if pure.is_absolute() or ".." in pure.parts:
        errors.append(f"{context}: artifact path must be a safe relative path")
        return
    if reference.get("storage") != "external-artifact-root":
        errors.append(f"{context}: storage must be external-artifact-root")
        return
    if external_root is None:
        errors.append(f"{context}: external artifact requires a configured artifact root")
        return
    receipt_path = external_root.joinpath(*pure.parts).resolve()
    try:
        receipt_path.relative_to(external_root.resolve())
    except ValueError:
        errors.append(f"{context}: artifact path escapes its configured root")
        return
    if not receipt_path.is_file():
        errors.append(f"{context}: receipt file does not exist: {path_text}")
        return
    try:
        receipt_value = json.loads(receipt_path.read_text(encoding="utf-8"))
    except UnicodeDecodeError:
        errors.append(f"{context}: receipt file is not valid UTF-8")
        return
    except json.JSONDecodeError as exc:
        errors.append(f"{context}: receipt file is invalid JSON at line {exc.lineno}, column {exc.colno}")
        return
    if not isinstance(receipt_value, dict):
        errors.append(f"{context}: receipt file must contain an object")
        return
    if receipt_value.get("schema_version") != REGISTRATION_RECEIPT_SCHEMA:
        errors.append(f"{context}: receipt schema_version is not supported")
        return
    output_artifact = receipt_value.get("output_artifact")
    if not isinstance(output_artifact, dict):
        errors.append(f"{context}: receipt output_artifact must be an object")
        return
    validate_artifact(
        root,
        external_root,
        output_artifact,
        f"{context}:output_artifact",
        errors,
    )

    output_path_text = output_artifact.get("path")
    if not isinstance(output_path_text, str) or not output_path_text:
        return
    output_pure = PurePosixPath(output_path_text)
    if output_pure.is_absolute() or ".." in output_pure.parts:
        return
    output_path = external_root.joinpath(*output_pure.parts).resolve()
    try:
        output_path.relative_to(external_root.resolve())
    except ValueError:
        return
    if not output_path.is_file():
        return
    try:
        original_data = output_path.read_bytes()
    except OSError:
        errors.append(f"{context}: receipt output artifact cannot be read")
        return
    expected_bytes = output_artifact.get("bytes")
    expected_hash = output_artifact.get("sha256")
    if isinstance(expected_bytes, int) and expected_bytes >= 0 and len(original_data) != expected_bytes:
        errors.append(f"{context}: receipt output byte count does not match output_artifact")
    if isinstance(expected_hash, str) and HASH_PATTERN.fullmatch(expected_hash):
        if hashlib.sha256(original_data).hexdigest() != expected_hash:
            errors.append(f"{context}: receipt output hash does not match output_artifact")
    try:
        original_value = json.loads(original_data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        errors.append(f"{context}: receipt output artifact is not valid JSON")
        return
    if not isinstance(original_value, dict):
        errors.append(f"{context}: receipt output artifact must contain an object")
        return
    if original_value.get("schema_version") != REGISTERED_LIBRARY_SCHEMA:
        errors.append(f"{context}: receipt output artifact has an unsupported schema_version")
    atlas_id = collection.get("atlas_id")
    if isinstance(atlas_id, str) and original_value.get("atlas_id") != atlas_id:
        errors.append(f"{context}: receipt output atlas_id does not match the atlas")
    receipt_atlas_id = receipt_value.get("atlas_id")
    if not isinstance(receipt_atlas_id, str) or not receipt_atlas_id:
        errors.append(f"{context}: receipt atlas_id is required")
    elif original_value.get("atlas_id") != receipt_atlas_id:
        errors.append(f"{context}: receipt atlas_id does not match output_artifact")
    receipt_library_id = receipt_value.get("library_id")
    if not isinstance(receipt_library_id, str) or not receipt_library_id:
        errors.append(f"{context}: receipt library_id is required")
    else:
        included_library_ids = original_value.get("included_library_ids")
        if isinstance(included_library_ids, list):
            if receipt_library_id not in included_library_ids:
                errors.append(f"{context}: receipt library_id is not included in output_artifact")
        elif original_value.get("library_id") != receipt_library_id:
            errors.append(f"{context}: receipt library_id does not match output_artifact")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("atlas_directory", type=Path)
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(argv)


def configured_external_root(root: Path, errors: list[str]) -> Path | None:
    path = root / ".surface-atlas-local.json"
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError:
        errors.append("invalid UTF-8 in .surface-atlas-local.json")
        return None
    except json.JSONDecodeError as exc:
        errors.append(
            f"invalid JSON in .surface-atlas-local.json: line {exc.lineno}, column {exc.colno}"
        )
        return None
    if not isinstance(value, dict) or not isinstance(value.get("artifact_root"), str):
        errors.append(".surface-atlas-local.json: artifact_root must be a string")
        return None
    candidate = Path(value["artifact_root"]).resolve()
    if not candidate.is_dir():
        errors.append(".surface-atlas-local.json: artifact_root is not a directory")
        return None
    return candidate


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.atlas_directory.resolve()
    errors: list[str] = []
    warnings: list[str] = []
    loaded: dict[str, Any] = {}
    external_root = configured_external_root(root, errors)

    for filename, schema_version in REQUIRED_FILES.items():
        value = load_json(root / filename, errors)
        loaded[filename] = value
        if isinstance(value, dict) and value.get("schema_version") != schema_version:
            errors.append(f"{filename}: expected schema_version {schema_version}")

    plan = loaded.get("atlas-plan.json")
    if not isinstance(plan, dict):
        return finish(args.json_output, root, errors, warnings)
    atlas_id = plan.get("atlas_id")
    if not isinstance(atlas_id, str) or not SAFE_ATLAS_ID_PATTERN.fullmatch(atlas_id):
        errors.append("atlas-plan.json: atlas_id must contain 3-64 lowercase letters, digits, or hyphens")

    if "disease" in plan and not isinstance(plan["disease"], dict):
        errors.append("atlas-plan.json: disease must be an object")

    scope = plan.get("scope")
    if not isinstance(scope, dict):
        errors.append("atlas-plan.json: scope must be an object")
    else:
        if scope.get("research_target_cap") is not None:
            errors.append("atlas-plan.json: research_target_cap must be null; resource tiers start after discovery")
        if scope.get("completeness_language") != "searched-in-scope target census":
            errors.append("atlas-plan.json: completeness_language must be 'searched-in-scope target census'")
        if scope.get("coverage_claim") not in COVERAGE_STATES:
            errors.append("atlas-plan.json: coverage_claim has an invalid state")

    resource_profile = plan.get("resource_profile")
    if not isinstance(resource_profile, dict):
        errors.append("atlas-plan.json: resource_profile must be an object")
    else:
        tiers = resource_profile.get("structure_tiers")
        if not isinstance(tiers, list) or not tiers:
            errors.append("atlas-plan.json: structure_tiers must be a non-empty array")
        else:
            tier_ids: set[str] = set()
            for index, tier in enumerate(tiers):
                if not isinstance(tier, dict):
                    errors.append(f"atlas-plan.json: structure_tiers[{index}] must be an object")
                    continue
                tier_id = tier.get("tier_id")
                if not isinstance(tier_id, str) or not tier_id.startswith("structure-"):
                    errors.append(f"atlas-plan.json: structure_tiers[{index}].tier_id must start with 'structure-'")
                elif tier_id in tier_ids:
                    errors.append(f"atlas-plan.json: duplicate tier_id {tier_id}")
                else:
                    tier_ids.add(tier_id)
                if not isinstance(tier.get("max_targets"), int) or tier["max_targets"] < 1:
                    errors.append(f"atlas-plan.json: structure_tiers[{index}].max_targets must be a positive integer")

    stages = plan.get("stages")
    stage_ids: set[str] = set()
    if not isinstance(stages, list) or not stages:
        errors.append("atlas-plan.json: stages must be a non-empty array")
    else:
        for index, stage in enumerate(stages):
            if not isinstance(stage, dict):
                errors.append(f"atlas-plan.json: stages[{index}] must be an object")
                continue
            stage_id = stage.get("stage_id")
            if not isinstance(stage_id, str) or not stage_id:
                errors.append(f"atlas-plan.json: stages[{index}].stage_id is required")
            elif stage_id in stage_ids:
                errors.append(f"atlas-plan.json: duplicate stage_id {stage_id}")
            else:
                stage_ids.add(stage_id)
            if stage.get("state") not in STAGE_STATES:
                errors.append(f"atlas-plan.json: stages[{index}] has invalid state")
        for stage in stages:
            if isinstance(stage, dict):
                for dependency in stage.get("depends_on", []):
                    if dependency not in stage_ids:
                        errors.append(f"atlas-plan.json: stage {stage.get('stage_id')} depends on unknown stage {dependency}")

    record_ids_by_file: dict[str, set[str]] = {}
    for filename, value in loaded.items():
        if not isinstance(value, dict) or filename in {"atlas-plan.json", "search-ledger.json"}:
            continue
        if value.get("atlas_id") != atlas_id:
            errors.append(f"{filename}: atlas_id does not match atlas-plan.json")
        records = value.get("records")
        if not isinstance(records, list):
            errors.append(f"{filename}: records must be an array")
            continue
        ids: set[str] = set()
        for index, record in enumerate(records):
            if not isinstance(record, dict):
                errors.append(f"{filename}: records[{index}] must be an object")
                continue
            item_id = record_id(record, filename)
            if not item_id:
                errors.append(
                    f"{filename}: records[{index}].{COLLECTION_ID_FIELDS[filename]} "
                    "must be a non-empty string without surrounding whitespace"
                )
            elif item_id in ids:
                errors.append(f"{filename}: duplicate record ID {item_id}")
            else:
                ids.add(item_id)
            if filename == "capabilities.json" and record.get("state") not in CAPABILITY_STATES:
                errors.append(f"{filename}: record {item_id or index} has invalid capability state")
            validate_record_artifacts(
                root,
                external_root,
                record,
                f"{filename}:{item_id or index}",
                errors,
            )
            validate_record_snapshots(
                root,
                external_root,
                record,
                f"{filename}:{item_id or index}",
                errors,
            )
        record_ids_by_file[filename] = ids
        if filename == "molecular-library.json" and isinstance(value, dict):
            validate_registration_receipt(root, external_root, value, errors)
        if filename == "screening-results.json" and all(
            isinstance(record, dict) for record in records
        ):
            try:
                screening_run_contexts(value, records)
            except ValueError as exc:
                errors.append(str(exc))

    target_records = loaded.get("targets.json", {}).get("records", []) if isinstance(loaded.get("targets.json"), dict) else []
    if isinstance(resource_profile, dict) and isinstance(resource_profile.get("structure_tiers"), list):
        tier_limits = {
            tier.get("tier_id"): tier.get("max_targets")
            for tier in resource_profile["structure_tiers"]
            if isinstance(tier, dict) and isinstance(tier.get("tier_id"), str)
        }
        tier_counts = {tier_id: 0 for tier_id in tier_limits}
        if isinstance(target_records, list):
            for index, target in enumerate(target_records):
                if not isinstance(target, dict):
                    continue
                assignment = target.get("structure_tier")
                if assignment == "retained-unmodeled":
                    continue
                if assignment not in tier_limits:
                    errors.append(
                        f"targets.json: record {target.get('target_id', index)} has invalid or missing structure_tier"
                    )
                    continue
                tier_counts[assignment] += 1
        for tier_id, count in tier_counts.items():
            limit = tier_limits[tier_id]
            if isinstance(limit, int) and count > limit:
                errors.append(f"targets.json: {tier_id} contains {count} targets; maximum is {limit}")

    discovered_records = (
        loaded.get("discovered-entities.json", {}).get("records", [])
        if isinstance(loaded.get("discovered-entities.json"), dict)
        else []
    )
    pending_discovered = 0
    if isinstance(discovered_records, list):
        for index, entity in enumerate(discovered_records):
            if not isinstance(entity, dict):
                continue
            entity_id = entity.get("entity_id", index)
            disposition = entity.get("surface_disposition")
            if disposition not in SURFACE_DISPOSITIONS:
                errors.append(f"discovered-entities.json: record {entity_id} has invalid surface_disposition")
                continue
            if disposition == "pending":
                pending_discovered += 1
            elif disposition == "surface-target":
                if entity.get("target_id") not in record_ids_by_file.get("targets.json", set()):
                    errors.append(f"discovered-entities.json: record {entity_id} points to an unknown target_id")
            elif disposition == "excluded-from-surface-universe":
                if entity.get("exclusion_id") not in record_ids_by_file.get("excluded-targets.json", set()):
                    errors.append(f"discovered-entities.json: record {entity_id} points to an unknown exclusion_id")

    ledger = loaded.get("search-ledger.json")
    discovered = loaded.get("discovered-entities.json")
    targets = loaded.get("targets.json")
    exclusions = loaded.get("excluded-targets.json")
    if isinstance(ledger, dict):
        if ledger.get("atlas_id") != atlas_id:
            errors.append("search-ledger.json: atlas_id does not match atlas-plan.json")
        counts = ledger.get("counts")
        if not isinstance(counts, dict):
            errors.append("search-ledger.json: counts must be an object")
        else:
            discovered_count = (
                len(discovered.get("records", []))
                if isinstance(discovered, dict) and isinstance(discovered.get("records"), list)
                else None
            )
            target_count = (
                len(targets.get("records", []))
                if isinstance(targets, dict) and isinstance(targets.get("records"), list)
                else None
            )
            exclusion_count = (
                len(exclusions.get("records", []))
                if isinstance(exclusions, dict) and isinstance(exclusions.get("records"), list)
                else None
            )
            if discovered_count is not None and counts.get("normalized_discovered_entities") != discovered_count:
                errors.append(
                    "search-ledger.json: normalized_discovered_entities does not equal "
                    "discovered-entities.json record count"
                )
            if target_count is not None and counts.get("surface_targets") != target_count:
                errors.append("search-ledger.json: surface_targets does not equal targets.json record count")
            if exclusion_count is not None and counts.get("excluded_from_surface_universe") != exclusion_count:
                errors.append(
                    "search-ledger.json: excluded_from_surface_universe does not equal "
                    "excluded-targets.json record count"
                )
            unresolved_count = (
                sum(
                    record.get("surface_disposition") == "unresolved"
                    for record in discovered.get("records", [])
                    if isinstance(record, dict)
                )
                if isinstance(discovered, dict) and isinstance(discovered.get("records"), list)
                else None
            )
            if unresolved_count is not None and counts.get("unresolved_records") != unresolved_count:
                errors.append(
                    "search-ledger.json: unresolved_records does not equal "
                    "discovered-entities.json unresolved record count"
                )
            for count_name in (
                "raw_records",
                "duplicate_records",
                "normalized_discovered_entities",
                "surface_targets",
                "excluded_from_surface_universe",
                "unresolved_records",
            ):
                if not isinstance(counts.get(count_name), int) or counts[count_name] < 0:
                    errors.append(f"search-ledger.json: counts.{count_name} must be a non-negative integer")
        coverage_state = ledger.get("coverage_state")
        if coverage_state not in COVERAGE_STATES:
            errors.append("search-ledger.json: coverage_state has an invalid state")
        sources = ledger.get("sources")
        if not isinstance(sources, list):
            errors.append("search-ledger.json: sources must be an array")
            sources = []
        source_ids: set[str] = set()
        for index, source in enumerate(sources):
            if not isinstance(source, dict):
                errors.append(f"search-ledger.json: sources[{index}] must be an object")
                continue
            query_id = source.get("query_id")
            if not isinstance(query_id, str) or not query_id or query_id != query_id.strip():
                errors.append(f"search-ledger.json: sources[{index}].query_id is required")
            elif query_id in source_ids:
                errors.append(f"search-ledger.json: duplicate query_id {query_id}")
            else:
                source_ids.add(query_id)
            status = source.get("status")
            if status not in SOURCE_STATES:
                errors.append(f"search-ledger.json: source {query_id or index} has invalid status")
            if status in {"partial", "blocked"} and not source.get("limitation"):
                errors.append(f"search-ledger.json: source {query_id or index} requires a limitation")
        if coverage_state == "complete_within_recorded_scope" and not ledger.get("sources"):
            errors.append("search-ledger.json: completed coverage requires at least one source record")
        if coverage_state == "complete_within_recorded_scope" and isinstance(scope, dict) and scope.get("coverage_claim") != coverage_state:
            errors.append("atlas-plan.json: coverage_claim must match completed search coverage")
        if coverage_state == "complete_within_recorded_scope":
            unfinished = [
                source.get("query_id", str(index))
                for index, source in enumerate(sources)
                if isinstance(source, dict) and source.get("status") in {"planned", "running"}
            ]
            if unfinished:
                errors.append(
                    "search-ledger.json: completed coverage has unfinished queries: " + ", ".join(unfinished)
                )
            if pending_discovered:
                errors.append(
                    f"discovered-entities.json: completed coverage has {pending_discovered} pending dispositions"
                )
        if ledger.get("coverage_state") == "planned":
            warnings.append("search coverage is planned; no evidence retrieval is claimed")

    return finish(args.json_output, root, errors, warnings)


def finish(json_output: bool, root: Path, errors: list[str], warnings: list[str]) -> int:
    result = {
        "schema_version": "codex-surface-atlas-validation/v0.1",
        "workspace": str(root),
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "network_or_provider_calls": False,
    }
    if json_output:
        print(json.dumps(result, indent=2))
    else:
        print("valid" if not errors else "invalid")
        for message in errors:
            print(f"ERROR: {message}")
        for message in warnings:
            print(f"WARNING: {message}")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())


def validate_workspace(atlas_directory: str | Path) -> dict[str, Any]:
    """Return the JSON validation result for a workspace.

    The command-line validator remains the single implementation of the
    contract.  Capturing its JSON output here keeps the importable API and the
    CLI behavior in lockstep without adding another validator with subtly
    different rules.
    """

    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        exit_code = main([str(atlas_directory), "--json"])
    try:
        result = json.loads(output.getvalue())
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive guard
        raise RuntimeError("validator did not produce JSON") from exc
    result["exit_code"] = exit_code
    return result
