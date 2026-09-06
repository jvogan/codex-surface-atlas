"""Offline, provenance-preserving binder run and laboratory result intake.

No scores are pooled, endpoints converted, controls inferred, or decisions made.
The JSON contracts deliberately retain unsuccessful and unperformed work.
"""
from __future__ import annotations

import copy
import hashlib
import html
import json
import math
import re
import shutil
import tempfile
from functools import wraps
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote

BINDER_SCHEMA = "codex-surface-binder-run-collection/v0.1"
ASSAY_SCHEMA = "codex-surface-assay-result-collection/v0.1"
LEGACY_SCHEMAS = {
    "binders.json": "codex-surface-binder-collection/v0.1",
    "binder-controls.json": "codex-surface-binder-control-collection/v0.1",
    "designed-binders.json": "codex-surface-designed-binder-collection/v0.1",
    "binder-results.json": "codex-surface-binder-result-collection/v0.1",
}
SHA = re.compile(r"^[a-f0-9]{64}$")
AA = re.compile(r"^[ACDEFGHIKLMNPQRSTVWYXBZUO]+$")


class IntakeError(ValueError):
    """An input cannot be safely attributed or transported."""


def require(condition: Any, message: str) -> None:
    if not condition:
        raise IntakeError(message)


def load_json(path: Path | str) -> dict:
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, f"duplicate JSON key: {key}")
            result[key] = value
        return result
    def constant(value):
        raise IntakeError(f"non-finite JSON number: {value}")
    def finite_float(value):
        number = float(value)
        require(math.isfinite(number), "non-finite JSON number")
        return number
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"),
                           object_pairs_hook=pairs, parse_constant=constant, parse_float=finite_float)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise IntakeError(f"cannot read {Path(path).name}: {exc}") from exc
    require(isinstance(value, dict), "collection must be an object")
    return value


def text(value: Any, label: str) -> str:
    require(isinstance(value, str) and value.strip() == value and bool(value), f"{label}: nonempty string required")
    return value


def obj(value: Any, label: str) -> dict:
    require(isinstance(value, dict), f"{label}: object required")
    return value


def array(value: Any, label: str, nonempty: bool = False) -> list:
    require(isinstance(value, list) and (bool(value) or not nonempty), f"{label}: {'nonempty ' if nonempty else ''}array required")
    return value


def unique(records: list, key: str, label: str) -> None:
    seen = set()
    for record in records:
        identifier = text(obj(record, label).get(key), f"{label}.{key}")
        require(identifier not in seen, f"{label}: duplicate {key}: {identifier}")
        seen.add(identifier)


def sequence(record: dict, label: str) -> None:
    seq = text(record.get("sequence"), f"{label}.sequence")
    require(AA.fullmatch(seq), f"{label}: sequence must be uppercase unspaced amino acids")
    require(record.get("sequence_sha256") == hashlib.sha256(seq.encode("ascii")).hexdigest(), f"{label}: sequence hash mismatch")
    if "sequence_length" in record:
        require(type(record["sequence_length"]) is int and record["sequence_length"] == len(seq), f"{label}: sequence length mismatch")


def artifact(root: Path, value: Any) -> Path:
    value = obj(value, "artifact")
    name = text(value.get("path"), "artifact.path")
    pure = PurePosixPath(name)
    require(not pure.is_absolute() and ".." not in pure.parts and "\\" not in name and pure.as_posix() == name and name != ".", "artifact path must be a canonical relative POSIX path")
    require(value.get("storage", "workspace") == "workspace", "research artifacts must be workspace-relative")
    require(isinstance(value.get("sha256"), str) and SHA.fullmatch(value["sha256"]), "artifact sha256 required")
    require(type(value.get("bytes")) is int and value["bytes"] >= 0, "artifact bytes must be a non-negative integer")
    path = root.joinpath(*pure.parts).resolve()
    require(path.is_relative_to(root.resolve()), "artifact escapes workspace (including symlink)")
    require(path.is_file(), f"artifact missing: {name}")
    data = path.read_bytes()
    require(len(data) == value["bytes"] and hashlib.sha256(data).hexdigest() == value["sha256"], f"artifact integrity mismatch: {name}")
    return path


def source(root: Path, value: Any) -> None:
    value = obj(value, "source")
    artifact(root, value.get("artifact"))
    text(value.get("locator"), "source.locator")


def sources_in(root: Path, value: Any) -> None:
    if isinstance(value, list):
        for item in value:
            sources_in(root, item)
    elif isinstance(value, dict):
        for key, item in value.items():
            if key == "source":
                source(root, item)
            elif key == "artifacts":
                for entry in array(item, "artifacts"):
                    artifact(root, entry)
            else:
                sources_in(root, item)


def collection(value: dict, schema: str, atlas_id: str) -> list:
    require(value.get("schema_version") == schema, f"expected schema {schema}")
    require(value.get("atlas_id") == atlas_id, "collection atlas_id mismatch")
    require(value.get("data_status") in {"synthetic", "research"}, "data_status must explicitly be synthetic or research")
    return array(value.get("records"), "records", True)


def construct(root: Path, value: Any, label: str) -> dict:
    value = obj(value, label)
    text(value.get("construct_id"), f"{label}.construct_id")
    sequence(value, label)
    text(value.get("description"), f"{label}.description")
    # Nonsequence modifications cannot be represented by a sequence digest.
    for modification in array(value.get("modifications"), f"{label}.modifications"):
        text(modification, f"{label}.modification")
    source(root, value.get("source"))
    return value


def _validation_boundary(function):
    @wraps(function)
    def checked(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except (TypeError, KeyError, AttributeError, RecursionError) as exc:
            raise IntakeError(f"malformed research record: {exc}") from exc
    return checked


@_validation_boundary
def validate_binder_runs(value: dict, root: Path | str, atlas_id: str, target_ids: set[str]) -> None:
    root = Path(root)
    runs = collection(value, BINDER_SCHEMA, atlas_id)
    unique(runs, "run_id", "runs")
    constructs = {}
    def remember_construct(record):
        identity = (record["sequence_sha256"], json.dumps(record.get("modifications", []), sort_keys=True))
        identifier = record["construct_id"]
        require(identifier not in constructs or constructs[identifier] == identity, "construct_id reused with different sequence or modifications")
        constructs[identifier] = identity
    for run in runs:
        label = f"run {run['run_id']}"
        text(run.get("campaign_id"), f"{label}.campaign_id")
        require(run.get("target_id") in target_ids, f"{label}: unknown target_id")
        construct(root, run.get("target_construct"), f"{label}.target_construct")
        remember_construct(run["target_construct"])
        for key in ("generator", "evaluation_protocol"):
            descriptor = obj(run.get(key), f"{label}.{key}")
            text(descriptor.get("name" if key == "generator" else "id"), f"{label}.{key}.identifier")
            text(descriptor.get("version"), f"{label}.{key}.version")
            source(root, descriptor.get("source"))
        generator = run["generator"]
        require("seed" in generator and (generator["seed"] is None or type(generator["seed"]) is int), f"{label}: generator seed must be integer or explicit null")
        if generator["seed"] is None:
            text(generator.get("seed_gap"), "generator.seed_gap")
        source(root, run.get("source"))
        require(run.get("controls_status") in {"passed", "failed", "not-run", "unresolved"}, f"{label}: invalid controls_status")
        stages = array(run.get("stages"), f"{label}.stages", True)
        unique(stages, "name", f"{label}.stages")
        for stage in stages:
            require(stage.get("status") in {"completed", "partial", "failed", "not-run"}, f"{label}: invalid stage status")
            text(stage.get("reason"), f"{label}.stage.reason")
        candidates = array(run.get("candidates"), f"{label}.candidates", True)
        unique(candidates, "candidate_id", f"{label}.candidates")
        ids = {candidate["candidate_id"] for candidate in candidates}
        controls = []
        for candidate in candidates:
            clabel = f"{label}/{candidate['candidate_id']}"
            sequence(candidate, clabel)
            text(candidate.get("construct_id"), f"{clabel}.construct_id")
            text(candidate.get("description"), f"{clabel}.description")
            for modification in array(candidate.get("modifications"), f"{clabel}.modifications"):
                text(modification, "modification")
            remember_construct(candidate)
            require(candidate.get("role") in {"candidate", "positive-control", "negative-control"}, f"{clabel}: invalid role")
            require(candidate.get("evidence_class") == "computational-design-hypothesis", f"{clabel}: binder evidence must remain computational")
            source(root, candidate.get("source"))
            for parent in array(candidate.get("lineage"), f"{clabel}.lineage"):
                parent = obj(parent, "lineage parent")
                text(parent.get("run_id"), "parent.run_id")
                text(parent.get("candidate_id"), "parent.candidate_id")
                require(isinstance(parent.get("sequence_sha256"), str) and SHA.fullmatch(parent["sequence_sha256"]), "parent sequence hash required")
                source(root, parent.get("source"))
                if parent["run_id"] == run["run_id"]:
                    require(parent["candidate_id"] in ids and parent["candidate_id"] != candidate["candidate_id"], "invalid local lineage parent")
                    original = next(c for c in candidates if c["candidate_id"] == parent["candidate_id"])
                    require(parent["sequence_sha256"] == original["sequence_sha256"], "lineage parent hash mismatch")
            observations = array(candidate.get("observations"), f"{clabel}.observations")
            unique(observations, "observation_id", f"{clabel}.observations")
            seeds = set()
            for observation in observations:
                require(type(observation.get("seed")) is int, f"{clabel}: integer observation seed required")
                require(observation["seed"] not in seeds, f"{clabel}: duplicate seed in evaluation protocol")
                seeds.add(observation["seed"])
                require(observation.get("status") in {"scored", "failed", "not-run"}, f"{clabel}: invalid observation status")
                text(observation.get("reason"), f"{clabel}.observation.reason")
                metrics = obj(observation.get("metrics"), f"{clabel}.metrics")
                require(observation["status"] == "scored" or not metrics, f"{clabel}: unscored observation cannot carry scores")
                for name, score in metrics.items():
                    text(name, "metric name")
                    require(score is None or (type(score) in (int, float) and math.isfinite(score)), f"{clabel}: metric must be finite number or null")
                source(root, observation.get("source"))
            decision = obj(candidate.get("promotion"), f"{clabel}.promotion")
            require(decision.get("decision") in {"promoted", "not-promoted", "pending"}, f"{clabel}: invalid promotion decision")
            text(decision.get("rationale"), f"{clabel}.promotion.rationale")
            source(root, decision.get("source"))
            if candidate["role"] != "candidate":
                controls.append(candidate)
                require(candidate.get("acceptance_status") in {"passed", "failed", "not-run", "unresolved"}, f"{clabel}: control acceptance_status required")
                text(candidate.get("acceptance_rule"), f"{clabel}.acceptance_rule")
                require(decision["decision"] != "promoted", f"{clabel}: controls cannot be promoted as candidates")
            if decision["decision"] == "promoted":
                require(run["controls_status"] == "passed", f"{clabel}: promotion requires passed controls")
                require(any(o["status"] == "scored" for o in observations), f"{clabel}: promotion requires scored evidence")
        statuses = {control["acceptance_status"] for control in controls}
        if run["controls_status"] == "passed":
            require(bool(controls) and statuses == {"passed"}, f"{label}: passed controls require actual passed control records")
        if "failed" in statuses:
            require(run["controls_status"] == "failed", f"{label}: failed control must remain visible in run status")
        if run["controls_status"] == "not-run":
            require(statuses <= {"not-run"}, f"{label}: not-run controls conflict with recorded acceptance")
    _validate_joined_runs(runs)
    sources_in(root, value)


def _validate_joined_runs(runs: list[dict]) -> None:
    """Validate identities across independently imported collections too."""
    constructs = {}
    for run in runs:
        for item in [run["target_construct"], *run["candidates"]]:
            identity = (item["sequence_sha256"], json.dumps(item["modifications"], sort_keys=True))
            identifier = item["construct_id"]
            require(identifier not in constructs or constructs[identifier] == identity, "construct_id reused with different sequence or modifications")
            constructs[identifier] = identity
    # Known lineage parents are hash-bound even when they belong to another run.
    index = {(run["run_id"], c["candidate_id"]): c for run in runs for c in run["candidates"]}
    for key, candidate in index.items():
        for parent in candidate["lineage"]:
            parent_key = (parent["run_id"], parent["candidate_id"])
            if parent_key in index:
                require(parent_key != key and parent["sequence_sha256"] == index[parent_key]["sequence_sha256"], "cross-run lineage identity mismatch")
    done = set()
    def ancestors(key, stack):
        require(key not in stack, "lineage cycle detected")
        if key in done:
            return
        for parent in index[key]["lineage"]:
            parent_key = (parent["run_id"], parent["candidate_id"])
            if parent_key in index:
                ancestors(parent_key, stack | {key})
        done.add(key)
    for key in index:
        ancestors(key, set())


ENDPOINT_UNITS = {
    "KD": {"M", "mM", "uM", "µM", "nM", "pM", "fM"},
    "IC50": {"M", "mM", "uM", "µM", "nM", "pM", "fM"},
    "EC50": {"M", "mM", "uM", "µM", "nM", "pM", "fM"},
    "kon": {"M^-1 s^-1"}, "koff": {"s^-1"},
    "response": {"RU", "nm", "%", "1", "RFU", "RLU", "OD"},
}


def reading(root: Path, value: Any, endpoint: str) -> None:
    value = obj(value, "reading")
    status = value.get("status")
    require(status in {"measured", "failed", "not-measured", "inconclusive"}, "invalid reading status")
    unit = value.get("unit")
    require(unit is None or unit in ENDPOINT_UNITS[endpoint], "unit incompatible with endpoint")
    if status == "measured":
        require(type(value.get("value")) in (int, float) and math.isfinite(value["value"]), "measured reading requires finite numeric value")
        require(value.get("relation") in {"=", "<", "<=", ">", ">="}, "measured reading requires relation")
        require(unit is not None, "measured reading requires unit")
        if endpoint != "response":
            require(value["value"] >= 0, "concentration/rate cannot be negative")
    else:
        require("value" in value and value["value"] is None and "relation" in value and value["relation"] is None, "missing/failed reading requires explicit null value and relation")
        text(value.get("reason"), "reading.reason")
    source(root, value.get("source"))


@_validation_boundary
def validate_assays(value: dict, root: Path | str, atlas_id: str, target_ids: set[str], binder_runs: dict) -> None:
    root = Path(root)
    records = collection(value, ASSAY_SCHEMA, atlas_id)
    unique(records, "assay_result_id", "assays")
    index = {(r["run_id"], c["candidate_id"]): (r, c) for r in binder_runs.get("records", []) for c in r.get("candidates", [])}
    record_ids = {r["assay_result_id"] for r in records}
    for record in records:
        text(record.get("experiment_id"), "experiment_id")
        require(record.get("evidence_class") == "laboratory-assay-observation", "assays require laboratory evidence class")
        require(record.get("target_id") in target_ids, "assay target_id does not resolve")
        key = (record.get("candidate_run_id"), record.get("candidate_id"))
        require(key in index, "assay candidate must resolve by exact run_id and candidate_id")
        run, candidate = index[key]
        require(record["target_id"] == run["target_id"], "assay target differs from candidate run")
        require(record.get("campaign_id") == run["campaign_id"], "assay campaign mismatch")
        if binder_runs.get("data_status") == "synthetic":
            require(value["data_status"] == "synthetic", "synthetic candidate cannot become research assay evidence")
        for field, original in (("candidate_construct", candidate), ("target_construct", run["target_construct"])):
            supplied = construct(root, record.get(field), field)
            require(supplied["construct_id"] == original["construct_id"] and supplied["sequence_sha256"] == original["sequence_sha256"], f"{field}: exact construct ID and sequence hash must match binder run; register a distinct run/construct before importing modified constructs")
            require(supplied["modifications"] == original.get("modifications", []), f"{field}: nonsequence modification mismatch")
        method = obj(record.get("method"), "method")
        for field in ("name", "version", "conditions"):
            text(method.get(field), f"method.{field}")
        require(method.get("family") in {"SPR", "BLI", "ITC", "MST", "ELISA", "radioligand", "cell-assay", "other-laboratory-assay"}, "method must name a physical laboratory assay family")
        source(root, method.get("source"))
        endpoint = record.get("endpoint")
        require(endpoint in ENDPOINT_UNITS, "unsupported laboratory endpoint (predictions are not assay endpoints)")
        reading(root, record.get("reading"), endpoint)
        for plural, gap in (("replicates", "replicate_gap"), ("controls", "control_gap")):
            require(plural in record, f"{plural} must be explicit")
            if record[plural] is None:
                text(record.get(gap), gap)
            else:
                values = array(record[plural], plural, True)
                unique(values, "replicate_id" if plural == "replicates" else "control_id", plural)
                for item in values:
                    if plural == "replicates":
                        for identity in ("biological_sample_id", "technical_replicate_id"):
                            require(identity in item, f"replicate {identity} must be explicit (null if unknown)")
                            if item[identity] is not None:
                                text(item[identity], identity)
                        reading(root, item.get("reading"), endpoint)
                    else:
                        require(item.get("role") in {"positive", "negative", "blank", "reference"}, "invalid assay control role")
                        text(item.get("description"), "control.description")
                        text(item.get("acceptance_rule"), "control.acceptance_rule")
                        require(item.get("acceptance_status") in {"passed", "failed", "unresolved", "not-run"}, "invalid control acceptance status")
                        source(root, item.get("source"))
                        link = item.get("result_record_id")
                        require("result_record_id" in item and (link is None or link in record_ids), "control result link must resolve or be explicit null")
                        if link is not None:
                            linked = next(r for r in records if r["assay_result_id"] == link)
                            require(linked["experiment_id"] == record["experiment_id"], "control link crosses experiments")
                            require(link != record["assay_result_id"], "control result cannot link to itself")
        require("aggregation" in record, "aggregation must be explicit (null if unreported)")
        if record["aggregation"] is not None:
            aggregation = obj(record["aggregation"], "aggregation")
            text(aggregation.get("description"), "aggregation.description")
            for count in ("biological_sample_count", "technical_reading_count"):
                require(count in aggregation and (aggregation[count] is None or (type(aggregation[count]) is int and aggregation[count] >= 0)), f"aggregation.{count} must be non-negative integer or null")
            source(root, aggregation.get("source"))
        source(root, record.get("identity_source"))
    sources_in(root, value)


def _target_ids(root: Path, targets: Any = None) -> set[str]:
    targets = load_json(root / "targets.json") if targets is None else targets
    if isinstance(targets, dict):
        targets = targets.get("records", [])
    if isinstance(targets, set):
        return targets
    return {r["target_id"] for r in targets if isinstance(r, dict) and isinstance(r.get("target_id"), str)}


def validate_optional_research(root: Path | str, atlas_id: str, targets: Any = None) -> list[str]:
    """Return errors; absence is valid. Legacy records receive conservative checks.

    Legacy records are not upgraded to strict runs and cannot back new assays.
    """
    root = Path(root)
    errors = []
    runs = None
    try:
        target_ids = _target_ids(root, targets)
    except (IntakeError, TypeError) as exc:
        return [str(exc)]
    legacy_paths = [root / name for name in [*LEGACY_SCHEMAS, "designs.json"]]
    for directory_name in ("binders", "designs"):
        directory = root / directory_name
        if directory.exists() or directory.is_symlink():
            if not directory.is_dir() or not directory.resolve().is_relative_to(root.resolve()):
                errors.append(f"{directory_name}: expected directory within workspace")
                continue
            legacy_paths.extend(sorted(directory.rglob("*.json")))
    legacy_ids = set()
    for path in legacy_paths:
        if not path.exists() and not path.is_symlink():
            continue
        filename = path.relative_to(root).as_posix()
        try:
            require(path.is_file() and path.resolve().is_relative_to(root.resolve()), "legacy input must be a file within workspace")
            value = load_json(path)
            expected = LEGACY_SCHEMAS.get(path.name)
            schemas = {expected} if expected else set(LEGACY_SCHEMAS.values()) - {LEGACY_SCHEMAS["binder-controls.json"]}
            require(value.get("schema_version") in schemas and value.get("atlas_id") == atlas_id, "legacy schema or atlas identity mismatch; register a recognized collection")
            records = array(value.get("records"), "legacy records")
            controls = array(value.get("controls", []), "legacy controls")
            for record in records + controls:
                obj(record, "legacy binder")
                identifier = record.get("binder_id", record.get("candidate_id"))
                text(identifier, "legacy binder_id or candidate_id")
                require(identifier not in legacy_ids, f"duplicate legacy binder identity: {identifier}")
                legacy_ids.add(identifier)
                require(record.get("target_id") in target_ids, "legacy binder target does not resolve")
                sequence(record, "legacy binder")
                if "evidence_class" in record:
                    require(record["evidence_class"] in {"computational-design-hypothesis", "computational-control-hypothesis"}, "legacy binder evidence class must remain computational")
                for observation in array(record.get("cofold_observations", []), "legacy observations"):
                    obj(observation, "legacy observation")
                    for key in ("candidate_id", "target_id", "sequence_sha256"):
                        require(observation.get(key) == record.get(key), f"legacy observation {key} mismatch")
            sources_in(root, value)
        except (IntakeError, OSError, TypeError, KeyError) as exc:
            errors.append(f"{filename}: {exc}")
    for filename, check in (("binder-runs.json", validate_binder_runs), ("assay-results.json", validate_assays)):
        path = root / filename
        if not path.exists() and not path.is_symlink():
            continue
        try:
            require(path.is_file() and path.resolve().is_relative_to(root.resolve()), "research input must be a file within workspace")
            value = load_json(path)
            if filename == "binder-runs.json":
                check(value, root, atlas_id, target_ids)
                runs = value
            else:
                require(runs is not None, "assay intake requires valid strict binder-runs.json")
                check(value, root, atlas_id, target_ids, runs)
        except (IntakeError, OSError, TypeError, KeyError) as exc:
            errors.append(f"{filename}: {exc}")
    return errors


def _atlas(root: Path) -> tuple[str, set[str]]:
    plan = load_json(root / "atlas-plan.json")
    return text(plan.get("atlas_id"), "atlas_id"), _target_ids(root)


def _transport(value: Any, source_root: Path, destination: Path) -> Any:
    if isinstance(value, list):
        return [_transport(item, source_root, destination) for item in value]
    if not isinstance(value, dict):
        return value
    if {"path", "sha256", "bytes"} <= value.keys():
        original = artifact(source_root, value)
        relative = f"research-artifacts/{value['sha256']}/{original.name}"
        output = destination / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        if not output.exists():
            shutil.copyfile(original, output)
        return {**value, "path": relative, "storage": "workspace"}
    return {key: _transport(item, source_root, destination) for key, item in value.items()}


def _publish(output: Path, build) -> dict:
    from .export import _rename_directory_exclusive
    require(not output.exists() and not output.is_symlink(), "output must be a new directory; existing output is never overwritten")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".research-intake-", dir=output.parent))
    try:
        result = build(temporary)
        require(not output.exists(), "output appeared during import")
        _rename_directory_exclusive(temporary, output)
        return result
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def import_binder_runs(inputs: list[Path | str], atlas_directory: Path | str, output: Path | str | None = None) -> dict:
    """Validate independent strict runs, return normalized collection or new bundle.

    With output=None this is a dry run: artifact paths retain their input roots
    and the returned collection must not be written as a portable bundle.
    """
    root = Path(atlas_directory)
    atlas_id, target_ids = _atlas(root)
    require(bool(inputs), "at least one input collection required")
    loaded = [(Path(path), load_json(path)) for path in inputs]
    for path, value in loaded:
        validate_binder_runs(value, path.parent, atlas_id, target_ids)
    statuses = {value["data_status"] for _, value in loaded}
    require(len(statuses) == 1, "cannot mix synthetic and research collections")
    result = {"schema_version": BINDER_SCHEMA, "atlas_id": atlas_id, "data_status": statuses.pop(), "records": [copy.deepcopy(r) for _, value in loaded for r in value["records"]]}
    unique(result["records"], "run_id", "combined runs")
    _validate_joined_runs(result["records"])
    # Candidate identity is scoped to a run; incompatible protocols stay separate.
    if output is None:
        return result
    def build(destination):
        portable = {**result, "records": [r for path, value in loaded for r in _transport(value["records"], path.parent, destination)]}
        validate_binder_runs(portable, destination, atlas_id, target_ids)
        (destination / "binder-runs.json").write_text(json.dumps(portable, indent=2, allow_nan=False) + "\n")
        return portable
    return _publish(Path(output), build)


def import_assays(input_path: Path | str, atlas_directory: Path | str, output: Path | str | None = None) -> dict:
    """Import exact construct matches, preserving original endpoint and readings."""
    root, path = Path(atlas_directory), Path(input_path)
    atlas_id, target_ids = _atlas(root)
    runs = load_json(root / "binder-runs.json")
    validate_binder_runs(runs, root, atlas_id, target_ids)
    value = load_json(path)
    validate_assays(value, path.parent, atlas_id, target_ids, runs)
    if output is None:
        return copy.deepcopy(value)
    def build(destination):
        portable = _transport(value, path.parent, destination)
        validate_assays(portable, destination, atlas_id, target_ids, runs)
        (destination / "assay-results.json").write_text(json.dumps(portable, indent=2, allow_nan=False) + "\n")
        return portable
    return _publish(Path(output), build)


def _details(value: Any) -> str:
    return "<details><summary>Identity, conditions and source records</summary><pre>" + html.escape(json.dumps(value, indent=2, ensure_ascii=False)) + "</pre></details>"


def _esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _safe_link(href: str | None, label: Any, *, file_path: bool = False) -> str:
    if not isinstance(href, str) or not href or href.startswith(("/", "\\")) or ":" in href or "\\" in href or ".." in PurePosixPath(href.split("#")[0]).parts:
        return _esc(label)
    return f'<a href="{_esc(quote(href, safe="/" if file_path else "/#"))}">{_esc(label)}</a>'


def _source_links(value: Any, artifact_map: dict[str, str] | None) -> str:
    references = {}
    def visit(item):
        if isinstance(item, list):
            for child in item:
                visit(child)
        elif isinstance(item, dict):
            if "path" in item and "sha256" in item:
                references[str(item["path"])] = item
            for child in item.values():
                visit(child)
    visit(value)
    if not references:
        return ""
    links = [_safe_link((artifact_map or {}).get(path), path, file_path=True) for path in sorted(references)]
    return '<p class="source-files">Source files: ' + " · ".join(links) + "</p>"


def _table(headers: list[str], rows: list[list[str]]) -> str:
    return '<div class="table-wrap"><table><thead><tr>' + "".join("<th>" + _esc(h) + "</th>" for h in headers) + "</tr></thead><tbody>" + "".join("<tr>" + "".join("<td>" + cell + "</td>" for cell in row) + "</tr>" for row in rows) + "</tbody></table></div>"


def render_campaigns(value: dict | None, artifact_map: dict[str, str] | None = None, target_hrefs: dict[str, str] | None = None) -> str:
    if not value:
        return "<p>No strict binder runs recorded.</p>"
    body = "<p>Computational hypotheses; independent runs and controls are retained separately. No cross-run score pooling.</p>"
    if value.get("data_status") == "synthetic":
        body = "<p><strong>SYNTHETIC TEST DATA — no experimental or campaign result.</strong></p>" + body
    for run in value.get("records", []):
        candidates = run["candidates"]
        observations = [o for c in candidates for o in c["observations"]]
        promoted = sum(c["role"] == "candidate" and c["promotion"]["decision"] == "promoted" for c in candidates)
        generator, protocol = run["generator"], run["evaluation_protocol"]
        seed = generator["seed"] if generator["seed"] is not None else "unknown: " + generator["seed_gap"]
        body += '<section class="panel"><h2>' + _esc(run["run_id"]) + "</h2><p>Campaign " + _esc(run["campaign_id"]) + " · Target " + _safe_link((target_hrefs or {}).get(run["target_id"]), run["target_id"]) + " · Construct " + _esc(run["target_construct"]["construct_id"]) + "</p>"
        body += "<p>Generator: " + _esc(f"{generator['name']} {generator['version']}; seed {seed}") + ". Evaluation protocol: " + _esc(f"{protocol['id']} {protocol['version']}") + ".</p>"
        body += "<p><strong>Controls: " + _esc(run["controls_status"]) + f". Promoted candidates: {promoted}.</strong> Failed observations: {sum(o['status'] == 'failed' for o in observations)}; unrun observations: {sum(o['status'] == 'not-run' for o in observations)}; unrun stages: {sum(s['status'] == 'not-run' for s in run['stages'])}.</p>"
        body += _table(["Stage", "Status", "Reason"], [[_esc(s["name"]), _esc(s["status"]), _esc(s["reason"])] for s in run["stages"]])
        rows = []
        for candidate in candidates:
            obs = "; ".join(f"seed {o['seed']}: {o['status']} ({o['reason']}); " + ", ".join(f"{key}={val}" for key, val in o["metrics"].items()) for o in candidate["observations"]) or "No observations recorded"
            control = (candidate.get("acceptance_status", "") + ": " + candidate.get("acceptance_rule", "")) if candidate["role"] != "candidate" else "Not a control"
            rows.append([_esc(candidate["candidate_id"]), _esc(candidate["role"]), _esc(candidate["construct_id"]) + "<br><code>" + _esc(candidate["sequence_sha256"][:16]) + "…</code>", _esc(obs), _esc(control), _esc(candidate["promotion"]["decision"] + ": " + candidate["promotion"]["rationale"])])
        body += _table(["Candidate", "Role", "Construct / sequence SHA-256", "Separate observations", "Control acceptance", "Promotion decision"], rows)
        body += _source_links(run, artifact_map) + _details(run) + "</section>"
    return body


def _reading_display(value: dict) -> str:
    return (f"{value['relation']} {value['value']} {value['unit']}" if value["status"] == "measured" else f"{value['status']}: {value['reason']}")


def render_assays(value: dict | None, artifact_map: dict[str, str] | None = None, target_hrefs: dict[str, str] | None = None) -> str:
    if not value:
        return "<p>No laboratory assay return recorded.</p>"
    body = "<p>Source-reported endpoints under recorded conditions. IC50 and EC50 are not KD; measurements do not change candidate promotion.</p>"
    if value.get("data_status") == "synthetic":
        body = "<p><strong>SYNTHETIC TEST DATA — no laboratory measurements were performed.</strong></p>" + body
    for record in value.get("records", []):
        display = _reading_display(record["reading"])
        controls = record.get("controls")
        status = ", ".join(c["acceptance_status"] for c in controls) if controls else "unresolved: " + record.get("control_gap", "unreported")
        body += '<section class="panel"><h2>' + _esc(record["assay_result_id"]) + "</h2><p><strong>" + _esc(record["endpoint"] + " " + display) + "</strong></p><p>Controls: " + _esc(status) + "</p>"
        body += "<p>Experiment " + _esc(record["experiment_id"]) + " · Candidate " + _esc(record["candidate_run_id"] + "/" + record["candidate_id"]) + " · Target " + _safe_link((target_hrefs or {}).get(record["target_id"]), record["target_id"]) + "</p>"
        body += _table(["Exact construct", "Construct ID", "Full sequence SHA-256", "Description / modifications"], [[_esc(label), _esc(record[field]["construct_id"]), "<code>" + _esc(record[field]["sequence_sha256"]) + "</code>", _esc(record[field]["description"] + "; modifications: " + (", ".join(record[field]["modifications"]) or "none recorded"))] for label, field in (("Candidate", "candidate_construct"), ("Target", "target_construct"))])
        method = record["method"]
        body += "<p>Method: " + _esc(f"{method['family']} — {method['name']} {method['version']}") + ". Conditions: " + _esc(method["conditions"]) + "</p>"
        if record["replicates"] is None:
            body += "<p>Replicate details unavailable: " + _esc(record["replicate_gap"]) + "</p>"
        else:
            body += _table(["Replicate", "Biological sample", "Technical replicate", "Reading"], [[_esc(r["replicate_id"]), _esc(r["biological_sample_id"] or "unknown"), _esc(r["technical_replicate_id"] or "unknown"), _esc(_reading_display(r["reading"]))] for r in record["replicates"]])
        if controls:
            body += _table(["Control", "Role", "Acceptance", "Rule / description"], [[_esc(c["control_id"]), _esc(c["role"]), _esc(c["acceptance_status"]), _esc(c["acceptance_rule"] + "; " + c["description"])] for c in controls])
        aggregation = record["aggregation"]
        body += "<p>Aggregation: " + (_esc(aggregation["description"]) + "; biological samples: " + _esc(aggregation["biological_sample_count"]) + "; technical readings: " + _esc(aggregation["technical_reading_count"]) if aggregation else "not reported; no aggregate calculated by intake") + ".</p>"
        body += _source_links(record, artifact_map) + _details(record) + "</section>"
    return body
