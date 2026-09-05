"""Register supplied molecule and sequence libraries without network access."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import shutil
import stat
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from .export import _rename_directory_exclusive


COLLECTION_SCHEMA = "codex-surface-molecular-library/v0.1"
MANIFEST_SCHEMA = "surface-atlas-supplied-library-registration/v1"
RECEIPT_SCHEMA = "surface-atlas-supplied-library-registration-receipt/v1"
FORMATS = {"csv", "fasta", "sdf", "smiles"}
SMALL_MOLECULE_CLASSES = {"small-molecule", "natural-product", "metabolite", "other"}
FASTA_CLASSES = {"peptide", "modified-peptide", "protein-binder", "antibody-format-binder"}
SEQUENCE_PATTERN = re.compile(r"^[ABCDEFGHIKLMNPQRSTUVWXYZ*]+$")
SAFE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
CANONICAL_EXTENSIONS = {"csv": ".csv", "fasta": ".fasta", "sdf": ".sdf", "smiles": ".smi"}


class LibraryRegistrationError(RuntimeError):
    """Raised when a supplied library cannot be registered safely."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _pretty_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _reject_constant(value: str) -> None:
    raise ValueError(f"invalid JSON constant {value}")


def _read_regular(path: Path, label: str) -> bytes:
    if path.is_symlink():
        raise LibraryRegistrationError(f"{label} must not be a symlink")
    descriptor = -1
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        descriptor = os.open(path, flags)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise LibraryRegistrationError(f"{label} must be a regular file")
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = -1
            return stream.read()
    except LibraryRegistrationError:
        raise
    except OSError as exc:
        raise LibraryRegistrationError(f"could not read {label}") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _decode_text(data: bytes, label: str) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise LibraryRegistrationError(f"{label} must be UTF-8") from exc


def _load_object(data: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(_decode_text(data, label), parse_constant=_reject_constant)
    except json.JSONDecodeError as exc:
        raise LibraryRegistrationError(
            f"{label} is invalid JSON at line {exc.lineno}, column {exc.colno}"
        ) from exc
    except ValueError as exc:
        raise LibraryRegistrationError(f"{label} is invalid JSON") from exc
    if not isinstance(value, dict):
        raise LibraryRegistrationError(f"{label} must be a JSON object")
    return value


def _resolve_input(manifest_path: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise LibraryRegistrationError(f"{label} requires a non-empty path")
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = manifest_path.parent / candidate
    return candidate.absolute()


def _path_component(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip(".-")[:72] or "library"
    return f"{slug}-{_sha256(value.encode('utf-8'))[:10]}"


def _safe_relative(value: Any, label: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value:
        raise LibraryRegistrationError(f"{label} path must be a safe relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or value != path.as_posix() or any(part in {"", ".", ".."} for part in path.parts):
        raise LibraryRegistrationError(f"{label} path must be a safe relative path")
    if value in {"molecular-library.json", "registration.json"}:
        raise LibraryRegistrationError(f"{label} path conflicts with bundle metadata")
    return path


def _write_file(stage: Path, relative: PurePosixPath | str, data: bytes) -> Path:
    path = PurePosixPath(relative)
    destination = stage.joinpath(*path.parts)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if not destination.is_file() or destination.read_bytes() != data:
            raise LibraryRegistrationError(f"bundle artifact collision: {path.as_posix()}")
        return destination
    destination.write_bytes(data)
    return destination


def _artifact(relative: PurePosixPath | str, data: bytes) -> dict[str, Any]:
    return {
        "path": PurePosixPath(relative).as_posix(),
        "storage": "external-artifact-root",
        "bytes": len(data),
        "sha256": _sha256(data),
    }


def _stable_id(prefix: str, supplied: str | None, content: str, index: int) -> str:
    if supplied:
        candidate = supplied.strip()
        if not SAFE_ID_PATTERN.fullmatch(candidate):
            raise LibraryRegistrationError("supplied record ID is invalid")
        return candidate
    slug = re.sub(r"[^A-Za-z0-9]+", "-", content).strip("-")[:36] or f"record-{index}"
    return f"{prefix}-{slug}-{_sha256(content.encode('utf-8'))[:10]}"


def _common_record(
    spec: dict[str, Any], molecule_id: str, name: str, input_format: str,
    source_artifact: dict[str, Any], source_record_index: int,
) -> dict[str, Any]:
    return {
        "molecule_id": molecule_id,
        "input_library_id": spec["input_library_id"],
        "name": name,
        "aliases": [],
        "panel": spec.get("panel", "user-supplied"),
        "molecular_class": spec["molecular_class"],
        "input_format": input_format,
        "source_class": spec.get("source_class", "user-supplied"),
        "confidentiality": spec.get("confidentiality", "unspecified"),
        "license": spec.get("license", "unspecified"),
        "known_target_ids": [],
        "known_interaction_refs": [],
        "identity_state": "resolved",
        "evidence_class": "user-supplied-identity",
        "source_artifact": source_artifact,
        "source_record_index": source_record_index,
        "validation_state": "source-format-validated",
    }


def _sdf_property(block: str, key: str) -> str | None:
    pattern = re.compile(rf"^>\s*<\s*{re.escape(key)}\s*>\s*$", re.MULTILINE | re.IGNORECASE)
    match = pattern.search(block)
    if match is None:
        return None
    rows: list[str] = []
    for line in block[match.end():].lstrip("\r\n").splitlines():
        if not line.strip():
            break
        rows.append(line.rstrip())
    value = "\n".join(rows).strip()
    return value or None


def _parse_sdf(
    text: str, source_artifact: dict[str, Any], spec: dict[str, Any],
    stage: Path, input_root: PurePosixPath,
) -> list[dict[str, Any]]:
    if re.search(r"^\$\$\$\$\s*$", text, re.MULTILINE) is None:
        raise LibraryRegistrationError("SDF contains no record delimiter")
    blocks = [part.rstrip("\r\n") for part in re.split(r"\$\$\$\$\s*", text) if part.strip()]
    if not blocks:
        raise LibraryRegistrationError("SDF contains no records")
    records: list[dict[str, Any]] = []
    for index, block in enumerate(blocks, 1):
        if re.search(r"^M  END\s*$", block, re.MULTILINE) is None:
            raise LibraryRegistrationError(f"SDF record {index} has no MOL block terminator")
        lines = block.splitlines()
        supplied_id = _sdf_property(block, str(spec.get("id_property", "ID")))
        title = lines[0].strip() if lines else ""
        name = _sdf_property(block, str(spec.get("name_property", "NAME"))) or title or supplied_id or f"SDF record {index}"
        molecule_id = _stable_id("SDF", supplied_id, f"{name}\n{block}", index)
        record_data = (block + "\n$$$$\n").encode("utf-8")
        record_relative = input_root / "records" / f"record-{index:06d}-{_sha256(molecule_id.encode())[:12]}.sdf"
        _write_file(stage, record_relative, record_data)
        record = _common_record(spec, molecule_id, name, "sdf", source_artifact, index)
        record.update({
            "source_record_artifact": _artifact(record_relative, record_data),
            "source_record_sha256": _sha256(record_data),
            "source_smiles": _sdf_property(block, str(spec.get("smiles_property", "SMILES"))),
            "formal_charge": _sdf_property(block, "FORMAL_CHARGE"),
            "stereochemistry": {"state": "preserved-in-source-record", "interpretation": "not-normalized-by-registrar"},
            "mixture_state": spec.get("mixture_state", "not-normalized-by-registrar"),
            "preparation_state": "supplied-sdf-unprepared",
            "screening_eligibility": "identity-supplied-needs-preparation",
        })
        records.append(record)
    return records


def _smiles_rows(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line_number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        fields = stripped.split(maxsplit=2)
        name = ""
        if len(fields) > 2:
            name = fields[2]
            if len(name) >= 2 and name[0] == name[-1] and name[0] in {'"', "'"}:
                name = name[1:-1]
        rows.append({
            "smiles": fields[0],
            "id": fields[1] if len(fields) > 1 else "",
            "name": name,
            "source_line": str(line_number),
        })
    if not rows:
        raise LibraryRegistrationError("SMILES file contains no records")
    return rows


def _csv_rows(text: str, spec: dict[str, Any]) -> list[dict[str, str]]:
    delimiter = spec.get("delimiter", ",")
    if not isinstance(delimiter, str) or len(delimiter) != 1:
        raise LibraryRegistrationError("CSV delimiter must be one character")
    try:
        reader = csv.DictReader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True)
        if not reader.fieldnames:
            raise LibraryRegistrationError("CSV input requires a header")
        if len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise LibraryRegistrationError("CSV input has duplicate headers")
        smiles_column = str(spec.get("smiles_column", "smiles"))
        if smiles_column not in reader.fieldnames:
            raise LibraryRegistrationError("CSV input lacks the configured SMILES column")
        id_column = str(spec.get("id_column", "id"))
        name_column = str(spec.get("name_column", "name"))
        rows: list[dict[str, str]] = []
        for line_number, source_row in enumerate(reader, 2):
            if None in source_row:
                raise LibraryRegistrationError(f"CSV line {line_number} has extra fields")
            smiles = (source_row.get(smiles_column) or "").strip()
            if not smiles:
                raise LibraryRegistrationError(f"CSV line {line_number} has an empty SMILES value")
            row = {key: value for key, value in source_row.items() if isinstance(key, str) and isinstance(value, str)}
            row.update({"smiles": smiles, "id": (source_row.get(id_column) or "").strip(),
                        "name": (source_row.get(name_column) or "").strip(), "source_line": str(line_number)})
            rows.append(row)
    except csv.Error as exc:
        raise LibraryRegistrationError("CSV input is invalid") from exc
    if not rows:
        raise LibraryRegistrationError("CSV contains no records")
    return rows


def _parse_smiles(text: str, source_artifact: dict[str, Any], spec: dict[str, Any], input_format: str) -> list[dict[str, Any]]:
    rows = _csv_rows(text, spec) if input_format == "csv" else _smiles_rows(text)
    records: list[dict[str, Any]] = []
    for index, row in enumerate(rows, 1):
        smiles = row["smiles"]
        name = row.get("name") or row.get("id") or f"SMILES record {index}"
        molecule_id = _stable_id("SMI", row.get("id"), f"{name}\n{smiles}", index)
        record = _common_record(spec, molecule_id, name, input_format, source_artifact, index)
        record.update({
            "source_smiles": smiles,
            "source_line": int(row["source_line"]),
            "formal_charge": row.get("formal_charge") or spec.get("formal_charge"),
            "stereochemistry": {"state": "preserved-in-source-string", "interpretation": "not-normalized-by-registrar"},
            "mixture_state": "multi-component-string" if "." in smiles else "single-component-string",
            "preparation_state": row.get("preparation_state") or "supplied-smiles-unprepared",
            "screening_eligibility": "identity-supplied-needs-preparation",
        })
        if row.get("parent_id"):
            record["parent_molecule_id"] = row["parent_id"]
        records.append(record)
    return records


def _parse_fasta_text(text: str) -> list[tuple[str, str, str, int]]:
    records: list[tuple[str, str, str, int]] = []
    header: str | None = None
    chunks: list[str] = []
    start_line = 0

    def commit() -> None:
        if header is None:
            return
        sequence = "".join(chunks).replace(" ", "").upper()
        if not sequence or not SEQUENCE_PATTERN.fullmatch(sequence):
            raise LibraryRegistrationError("FASTA contains an invalid sequence")
        identifier, _, description = header.partition(" ")
        if not identifier:
            raise LibraryRegistrationError("FASTA header requires an identifier")
        records.append((identifier, description.strip(), sequence, start_line))

    for line_number, raw_line in enumerate(text.splitlines(), 1):
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(">"):
            commit()
            header, chunks, start_line = line[1:].strip(), [], line_number
        elif header is None:
            raise LibraryRegistrationError(f"FASTA sequence precedes a header at line {line_number}")
        else:
            chunks.append(line)
    commit()
    if not records:
        raise LibraryRegistrationError("FASTA contains no records")
    return records


def _load_sidecar(
    manifest_path: Path, spec: dict[str, Any], stage: Path, input_root: PurePosixPath,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any] | None]:
    if spec.get("modification_sidecar") is None:
        return {}, None
    path = _resolve_input(manifest_path, spec["modification_sidecar"], "modification sidecar")
    data = _read_regular(path, "modification sidecar")
    value = _load_object(data, "modification sidecar")
    source_records = value.get("records", value)
    result: dict[str, dict[str, Any]] = {}
    if isinstance(source_records, dict):
        for key, row in source_records.items():
            if not isinstance(row, dict):
                raise LibraryRegistrationError("modification sidecar records must be objects")
            result[str(key)] = dict(row)
    elif isinstance(source_records, list):
        for row in source_records:
            if not isinstance(row, dict) or not isinstance(row.get("record_id"), str):
                raise LibraryRegistrationError("modification sidecar list records require record_id")
            if row["record_id"] in result:
                raise LibraryRegistrationError("modification sidecar has duplicate record_id")
            result[row["record_id"]] = {key: value for key, value in row.items() if key != "record_id"}
    else:
        raise LibraryRegistrationError("modification sidecar records must be an object or array")
    relative = input_root / "modifications.json"
    _write_file(stage, relative, data)
    return result, _artifact(relative, data)


def _parse_fasta(
    text: str, source_artifact: dict[str, Any], spec: dict[str, Any], manifest_path: Path,
    stage: Path, input_root: PurePosixPath,
) -> list[dict[str, Any]]:
    sidecar, sidecar_artifact = _load_sidecar(manifest_path, spec, stage, input_root)
    parsed = _parse_fasta_text(text)
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, (identifier, description, sequence, line_number) in enumerate(parsed, 1):
        if identifier in seen:
            raise LibraryRegistrationError("FASTA contains a duplicate identifier")
        seen.add(identifier)
        molecule_id = _stable_id("SEQ", identifier, sequence, index)
        record = _common_record(spec, molecule_id, description or identifier, "fasta", source_artifact, index)
        modifications = dict(sidecar.get(identifier, {}))
        record.update({
            "fasta_id": identifier,
            "description": description,
            "sequence": sequence,
            "sequence_sha256": _sha256(sequence.encode("ascii")),
            "sequence_length": len(sequence),
            "source_line": line_number,
            "construct_boundaries": modifications.pop("construct_boundaries", spec.get("construct_boundaries")),
            "oligomeric_state": modifications.pop("oligomeric_state", spec.get("oligomeric_state", "unspecified")),
            "modifications": modifications,
            "preparation_state": "supplied-parent-sequence",
            "screening_eligibility": (
                "parent-sequence-registered-modification-model-pending"
                if modifications or spec["molecular_class"] == "modified-peptide"
                else "sequence-registered-needs-site-evaluation"
            ),
        })
        if sidecar_artifact:
            record["modification_sidecar_artifact"] = sidecar_artifact
        records.append(record)
    if set(sidecar) - seen:
        raise LibraryRegistrationError("modification sidecar contains unknown FASTA identifiers")
    return records


def _validate_manifest(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    if manifest.get("schema_version") != MANIFEST_SCHEMA:
        raise LibraryRegistrationError(f"manifest schema_version must be {MANIFEST_SCHEMA}")
    for field in ("atlas_id", "library_id"):
        if not isinstance(manifest.get(field), str) or not SAFE_ID_PATTERN.fullmatch(manifest[field]):
            raise LibraryRegistrationError(f"manifest has invalid {field}")
    inputs = manifest.get("inputs")
    if not isinstance(inputs, list) or not inputs:
        raise LibraryRegistrationError("manifest inputs must be a non-empty array")
    validated: list[dict[str, Any]] = []
    input_ids: set[str] = set()
    for index, source in enumerate(inputs, 1):
        if not isinstance(source, dict):
            raise LibraryRegistrationError(f"input {index} must be an object")
        spec = dict(source)
        input_format = spec.get("format")
        if not isinstance(input_format, str) or input_format.casefold() not in FORMATS:
            raise LibraryRegistrationError(f"input {index} has unsupported format")
        input_format = input_format.casefold()
        classes = FASTA_CLASSES if input_format == "fasta" else SMALL_MOLECULE_CLASSES
        if spec.get("molecular_class") not in classes:
            raise LibraryRegistrationError(f"input {index} has invalid molecular_class")
        input_id = spec.get("input_library_id", f"{manifest['library_id']}-{index}")
        if not isinstance(input_id, str) or not SAFE_ID_PATTERN.fullmatch(input_id):
            raise LibraryRegistrationError(f"input {index} has invalid input_library_id")
        if input_id in input_ids:
            raise LibraryRegistrationError("manifest has duplicate input_library_id")
        input_ids.add(input_id)
        spec.update({"format": input_format, "input_library_id": input_id})
        validated.append(spec)
    return validated


def _artifact_dicts(value: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    known_fields = {"source_artifact", "source_record_artifact", "modification_sidecar_artifact"}

    def visit(item: Any, field: str | None = None) -> None:
        if field == "registration_receipt":
            return
        if field in known_fields:
            if not isinstance(item, dict):
                raise LibraryRegistrationError(f"base library {field} must be an artifact object")
            result.append(item)
            return
        if field == "artifacts":
            if not isinstance(item, list):
                raise LibraryRegistrationError("base library artifacts must be an array")
            for child in item:
                if not isinstance(child, dict):
                    raise LibraryRegistrationError("base library artifacts entries must be objects")
                result.append(child)
            return
        if isinstance(item, list):
            for child in item:
                visit(child)
        elif isinstance(item, dict):
            path = item.get("path")
            if isinstance(path, str) and any(key in item for key in ("sha256", "bytes")):
                result.append(item)
                return
            for key, child in item.items():
                visit(child, key)

    visit(value)
    return result


def _copy_base_artifacts(base: dict[str, Any], base_path: Path, stage: Path) -> None:
    base_root = base_path.parent.resolve()
    seen: dict[str, tuple[str, int]] = {}
    for index, artifact in enumerate(_artifact_dicts(base), 1):
        label = f"base artifact {index}"
        if artifact.get("storage") != "external-artifact-root":
            raise LibraryRegistrationError(f"{label} has unsupported storage")
        relative = _safe_relative(artifact.get("path"), label)
        digest, byte_count = artifact.get("sha256"), artifact.get("bytes")
        if not isinstance(digest, str) or not HASH_PATTERN.fullmatch(digest):
            raise LibraryRegistrationError(f"{label} has invalid sha256")
        if isinstance(byte_count, bool) or not isinstance(byte_count, int) or byte_count < 0:
            raise LibraryRegistrationError(f"{label} has invalid byte count")
        signature = (digest, byte_count)
        previous = seen.get(relative.as_posix())
        if previous is not None:
            if previous != signature:
                raise LibraryRegistrationError(f"{label} conflicts with another reference to the same path")
            continue
        seen[relative.as_posix()] = signature
        source = base_root.joinpath(*relative.parts)
        current = base_root
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise LibraryRegistrationError(f"{label} contains a symlink")
        try:
            resolved = source.resolve(strict=True)
            resolved.relative_to(base_root)
        except (OSError, ValueError) as exc:
            raise LibraryRegistrationError(f"{label} leaves the base bundle") from exc
        data = _read_regular(source, label)
        if len(data) != byte_count or _sha256(data) != digest:
            raise LibraryRegistrationError(f"{label} failed integrity verification")
        _write_file(stage, relative, data)


def _load_base(base_path: Path, manifest: dict[str, Any], stage: Path) -> tuple[dict[str, Any], bytes]:
    data = _read_regular(base_path, "base library")
    base = _load_object(data, "base library")
    if base.get("schema_version") != COLLECTION_SCHEMA:
        raise LibraryRegistrationError(f"base library schema_version must be {COLLECTION_SCHEMA}")
    if base.get("atlas_id") != manifest["atlas_id"]:
        raise LibraryRegistrationError("base library atlas_id differs from manifest")
    if not isinstance(base.get("library_id"), str) or not SAFE_ID_PATTERN.fullmatch(base["library_id"]):
        raise LibraryRegistrationError("base library has invalid library_id")
    records = base.get("records")
    if not isinstance(records, list) or any(not isinstance(row, dict) for row in records):
        raise LibraryRegistrationError("base library records must be an array of objects")
    _copy_base_artifacts(base, base_path, stage)
    relative = PurePosixPath("libraries/base") / _sha256(data) / "molecular-library.json"
    _write_file(stage, relative, data)
    return base, data


def register_library(
    manifest: Path, output_directory: Path, *, base_library: Path | None = None,
) -> dict[str, Any]:
    """Register supplied inputs into a new portable artifact bundle."""

    manifest_path = Path(manifest).absolute()
    destination = Path(output_directory)
    if destination.exists() or destination.is_symlink():
        raise LibraryRegistrationError("output directory must not already exist")
    if not destination.parent.is_dir():
        raise LibraryRegistrationError("output parent must be an existing directory")
    manifest_data = _read_regular(manifest_path, "registration manifest")
    manifest_value = _load_object(manifest_data, "registration manifest")
    specs = _validate_manifest(manifest_value)
    try:
        stage = Path(tempfile.mkdtemp(prefix=f".{destination.name}.tmp-", dir=destination.parent))
    except OSError as exc:
        raise LibraryRegistrationError("could not create registration staging directory") from exc

    try:
        base: dict[str, Any] | None = None
        base_data: bytes | None = None
        existing_records: list[dict[str, Any]] = []
        if base_library is not None:
            base, base_data = _load_base(Path(base_library).absolute(), manifest_value, stage)
            existing_records = [dict(row) for row in base["records"]]

        registered: list[dict[str, Any]] = []
        input_receipts: list[dict[str, Any]] = []
        for spec in specs:
            source_path = _resolve_input(manifest_path, spec.get("path"), "library input")
            source_data = _read_regular(source_path, "library input")
            source_text = _decode_text(source_data, "library input")
            source_digest = _sha256(source_data)
            input_root = PurePosixPath("libraries") / _path_component(spec["input_library_id"]) / source_digest
            source_relative = input_root / f"source{CANONICAL_EXTENSIONS[spec['format']]}"
            _write_file(stage, source_relative, source_data)
            source_artifact = _artifact(source_relative, source_data)
            if spec["format"] == "sdf":
                records = _parse_sdf(source_text, source_artifact, spec, stage, input_root)
            elif spec["format"] in {"csv", "smiles"}:
                records = _parse_smiles(source_text, source_artifact, spec, spec["format"])
            else:
                records = _parse_fasta(source_text, source_artifact, spec, manifest_path, stage, input_root)
            registered.extend(records)
            input_receipts.append({
                "input_library_id": spec["input_library_id"],
                "format": spec["format"],
                "molecular_class": spec["molecular_class"],
                "source_artifact": source_artifact,
                "record_count": len(records),
            })

        combined = existing_records + registered
        ids: set[str] = set()
        for row in combined:
            molecule_id = row.get("molecule_id")
            if not isinstance(molecule_id, str) or not molecule_id or molecule_id != molecule_id.strip():
                raise LibraryRegistrationError("every library record requires molecule_id")
            if molecule_id in ids:
                raise LibraryRegistrationError(f"duplicate molecule_id after registration: {molecule_id}")
            ids.add(molecule_id)

        if base is None:
            output: dict[str, Any] = {
                "schema_version": COLLECTION_SCHEMA,
                "atlas_id": manifest_value["atlas_id"],
                "library_id": manifest_value["library_id"],
                "purpose": manifest_value.get("purpose", "Register a user-supplied screening library."),
                "claim_state": "identity-and-sequence-registration-only",
                "screening_contract": manifest_value.get("screening_contract", {
                    "small_molecule_route": "defined extracellular pocket required",
                    "protein_or_peptide_route": "defined extracellular interface required",
                    "evidence_class": "computational-screening-hypothesis",
                }),
            }
        else:
            output = {key: value for key, value in base.items() if key not in {
                "records", "record_count", "panel_counts", "registration_receipt", "updated_at"
            }}
        included = output.get("included_library_ids", [])
        if not isinstance(included, list) or any(not isinstance(value, str) for value in included):
            raise LibraryRegistrationError("base library included_library_ids must be an array of strings")
        included = list(included)
        for library_id in [output["library_id"], manifest_value["library_id"], *(spec["input_library_id"] for spec in specs)]:
            if library_id not in included:
                included.append(library_id)
        registered_at = _utc_now()
        output.update({
            "updated_at": registered_at,
            "included_library_ids": included,
            "registration_receipt": {"path": "registration.json", "storage": "external-artifact-root"},
            "record_count": len(combined),
            "panel_counts": dict(sorted(
                (panel, sum(row.get("panel", "unassigned") == panel for row in combined))
                for panel in {row.get("panel", "unassigned") for row in combined}
            )),
            "records": combined,
        })
        output_data = _pretty_json(output)
        _write_file(stage, "molecular-library.json", output_data)
        receipt: dict[str, Any] = {
            "schema_version": RECEIPT_SCHEMA,
            "atlas_id": manifest_value["atlas_id"],
            "library_id": manifest_value["library_id"],
            "registered_at": registered_at,
            "provider_calls": 0,
            "network_calls": 0,
            "target_assignments_created": 0,
            "manifest_sha256": _sha256(manifest_data),
            "base_library_artifact": (
                _artifact(PurePosixPath("libraries/base") / _sha256(base_data) / "molecular-library.json", base_data)
                if base_data is not None else None
            ),
            "inputs": input_receipts,
            "registered_record_count": len(registered),
            "output_record_count": len(combined),
            "output_artifact": _artifact("molecular-library.json", output_data),
        }
        _write_file(stage, "registration.json", _pretty_json(receipt))
        try:
            _rename_directory_exclusive(stage, destination)
        except OSError as exc:
            raise LibraryRegistrationError("could not publish registration; output may have appeared") from exc
    except LibraryRegistrationError:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    except Exception as exc:
        shutil.rmtree(stage, ignore_errors=True)
        raise LibraryRegistrationError("library registration failed") from exc
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise

    return {
        "ok": True,
        "output_directory": str(destination),
        "molecular_library": "molecular-library.json",
        "registration": "registration.json",
        "registered_records": len(registered),
        "total_records": len(combined),
        "provider_calls": 0,
        "network_calls": 0,
    }


__all__ = ["LibraryRegistrationError", "register_library"]
