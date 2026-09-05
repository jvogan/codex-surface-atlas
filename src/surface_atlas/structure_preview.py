"""Validate and render bounded, report-local structure preview descriptors.

The descriptor is deliberately small.  Coordinates are ordinary verified
record artifacts, while this module only translates their recorded styling to
the local browser viewer.  No network or provider access is used.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import PurePosixPath
from typing import Any


STRUCTURE_SNAPSHOT_SCHEMA = "codex-surface-structure-snapshot/v0.1"
HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")
OBJECT_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
CHAIN_NAME = r"[A-Za-z0-9]{1,8}"
COORDINATE_SUFFIXES = {".pdb": "pdb", ".cif": "cif", ".mmcif": "cif", ".sdf": "sdf"}
SEQUENCE_SUFFIXES = {".fasta", ".fa", ".faa"}
MAX_SOURCES = 4
MAX_LAYERS = 20
MAX_COORDINATE_BYTES = 8 * 1024 * 1024


def _safe_relative(value: Any) -> PurePosixPath | None:
    if not isinstance(value, str) or not value.strip() or "\\" in value:
        return None
    try:
        path = PurePosixPath(value.strip())
    except (TypeError, ValueError):
        return None
    if path.is_absolute() or ".." in path.parts or "." in path.parts:
        return None
    return path


def _artifact_errors(value: Any, context: str, *, sequence: bool = False) -> list[str]:
    if not isinstance(value, dict):
        return [f"{context}: artifact must be an object"]
    errors: list[str] = []
    path = _safe_relative(value.get("path"))
    if path is None:
        errors.append(f"{context}: artifact path must be a safe relative path")
    expected_hash = value.get("sha256")
    if not isinstance(expected_hash, str) or not HASH_PATTERN.fullmatch(expected_hash):
        errors.append(f"{context}: artifact sha256 must contain 64 lowercase hex characters")
    expected_bytes = value.get("bytes")
    if isinstance(expected_bytes, bool) or not isinstance(expected_bytes, int) or expected_bytes < 0:
        errors.append(f"{context}: artifact bytes must be a non-negative integer")
    if sequence:
        if path is not None and path.suffix.casefold() not in SEQUENCE_SUFFIXES:
            errors.append(f"{context}: sequence artifact must use .fasta, .fa, or .faa")
    elif path is not None:
        suffix = path.suffix.casefold()
        declared = value.get("format")
        if suffix not in COORDINATE_SUFFIXES:
            errors.append(f"{context}: coordinate artifact must use .pdb, .cif, .mmcif, or .sdf")
        elif declared != suffix.removeprefix("."):
            errors.append(f"{context}: coordinate format must match its file suffix")
    return errors


def translate_simple_selection(value: Any) -> dict[str, Any] | None:
    """Translate the deliberately small selector subset used by snapshots."""
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    if value == "not hydro":
        return {"elem": "H", "invert": True}
    if "(" in value or ")" in value:
        return None
    terms = re.split(r"\s+and\s+", value)
    if not terms or any(not term for term in terms):
        return None
    selection: dict[str, Any] = {}
    for term in terms:
        if term == "polymer.protein":
            if "hetflag" in selection:
                return None
            selection["hetflag"] = False
            continue
        chain = re.fullmatch(rf"chain ({CHAIN_NAME}(?:\+{CHAIN_NAME})*)", term)
        if chain:
            if "chain" in selection:
                return None
            names = chain.group(1).split("+")
            selection["chain"] = names[0] if len(names) == 1 else names
            continue
        residues = re.fullmatch(r"resi (.+)", term)
        if residues:
            if "resi" in selection:
                return None
            numbers = _residue_numbers(residues.group(1))
            if numbers is None:
                return None
            selection["resi"] = numbers[0] if len(numbers) == 1 else numbers
            continue
        residue_name = re.fullmatch(r"resn ([A-Za-z0-9]{1,8})", term)
        if residue_name:
            if "resn" in selection:
                return None
            selection["resn"] = residue_name.group(1)
            continue
        return None
    return selection or None


def _residue_numbers(value: str) -> list[int] | None:
    if not re.fullmatch(r"[0-9]+(?:-[0-9]+)?(?:\+[0-9]+(?:-[0-9]+)?)*", value):
        return None
    result: list[int] = []
    for item in value.split("+"):
        if "-" in item:
            start, end = (int(part) for part in item.split("-", 1))
            if end < start or end - start > 10_000:
                return None
            result.extend(range(start, end + 1))
        else:
            result.append(int(item))
        if len(result) > 10_000:
            return None
    return list(dict.fromkeys(result))


def snapshot_values(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Return optional inline snapshots while preserving legacy records."""
    value = record.get("structure_snapshot")
    if isinstance(value, dict):
        return [value]
    values = record.get("structure_snapshots")
    if isinstance(values, list):
        return [item for item in values if isinstance(item, dict)]
    return []


def snapshot_errors(snapshot: Any, *, context: str = "structure_snapshot") -> list[str]:
    """Return contract errors without reading or copying any files."""
    if not isinstance(snapshot, dict):
        return [f"{context}: snapshot must be an object"]
    errors: list[str] = []
    if snapshot.get("schema_version") != STRUCTURE_SNAPSHOT_SCHEMA:
        errors.append(f"{context}: schema_version must be {STRUCTURE_SNAPSHOT_SCHEMA}")
    sources = snapshot.get("coordinate_sources")
    if not isinstance(sources, list) or not 1 <= len(sources) <= MAX_SOURCES:
        errors.append(f"{context}: coordinate_sources must contain 1-{MAX_SOURCES} entries")
        sources = []
    object_names: set[str] = set()
    for index, source in enumerate(sources):
        source_context = f"{context}.coordinate_sources[{index}]"
        errors.extend(_artifact_errors(source, source_context))
        if not isinstance(source, dict):
            continue
        object_name = source.get("object_name")
        if not isinstance(object_name, str) or not OBJECT_NAME.fullmatch(object_name):
            errors.append(f"{source_context}.object_name must be a safe object name")
        elif object_name in object_names:
            errors.append(f"{source_context}.object_name is duplicated: {object_name}")
        else:
            object_names.add(object_name)
        if type(source.get("state")) is not int or source.get("state") != 1:
            errors.append(f"{source_context}.state must be 1")
        if isinstance(source.get("bytes"), int) and source["bytes"] > MAX_COORDINATE_BYTES:
            errors.append(f"{source_context}.bytes exceeds the 8 MiB preview limit")

    layers = snapshot.get("layers")
    if not isinstance(layers, list) or not 1 <= len(layers) <= MAX_LAYERS:
        errors.append(f"{context}: layers must contain 1-{MAX_LAYERS} entries")
        layers = []
    for index, layer in enumerate(layers):
        layer_context = f"{context}.layers[{index}]"
        if not isinstance(layer, dict):
            errors.append(f"{layer_context}: layer must be an object")
            continue
        object_name = layer.get("object_name")
        if not isinstance(object_name, str) or object_name not in object_names:
            errors.append(f"{layer_context}.object_name must refer to a coordinate source")
        selection = translate_simple_selection(layer.get("selection"))
        if selection is None:
            errors.append(f"{layer_context}.selection is not a supported bounded selector")
        color = layer.get("color")
        if not isinstance(color, str) or not HEX_COLOR.fullmatch(color):
            errors.append(f"{layer_context}.color must be a six-digit hex color")
        representation = layer.get("representation")
        if not isinstance(representation, str) or representation not in {"cartoon", "stick", "sticks"}:
            errors.append(f"{layer_context}.representation must be cartoon or stick")
        color_mode = layer.get("color_mode")
        if not isinstance(color_mode, str) or color_mode not in {"solid", "carbon-and-elements"}:
            errors.append(f"{layer_context}.color_mode is unsupported")
        opacity = layer.get("opacity")
        if opacity is None:
            transparency = layer.get("transparency")
            if isinstance(transparency, bool) or not isinstance(transparency, (int, float)) or not 0 <= transparency <= 1:
                errors.append(f"{layer_context}: opacity or transparency must be between 0 and 1")
        elif isinstance(opacity, bool) or not isinstance(opacity, (int, float)) or not 0 <= opacity <= 1:
            errors.append(f"{layer_context}.opacity must be between 0 and 1")
        label = layer.get("label", layer.get("description", layer.get("name")))
        if not isinstance(label, str) or not label.strip() or len(label.strip()) > 300:
            errors.append(f"{layer_context}: label or description is required")

    sequence = snapshot.get("sequence_artifact")
    if sequence is not None:
        errors.extend(_artifact_errors(sequence, f"{context}.sequence_artifact", sequence=True))
        if isinstance(sequence, dict):
            for key in ("sequence_id", "chain"):
                if key in sequence and (not isinstance(sequence[key], str) or not sequence[key].strip()):
                    errors.append(f"{context}.sequence_artifact.{key} must be a non-empty string")
    return errors


def normalized_scene(snapshot: dict[str, Any], artifact_map: dict[str, str]) -> dict[str, Any] | None:
    """Return the browser scene only when every source is copied and verified."""
    if snapshot_errors(snapshot):
        return None
    sources: list[dict[str, Any]] = []
    for source in snapshot["coordinate_sources"]:
        path = source["path"]
        href = artifact_map.get(path)
        if not isinstance(href, str) or not href.startswith("data/artifacts/"):
            return None
        suffix = PurePosixPath(path).suffix.casefold().removeprefix(".")
        sources.append(
            {
                "href": href,
                "format": "cif" if suffix == "mmcif" else suffix,
                "sha256": source["sha256"],
                "object_name": source["object_name"],
                "state": 1,
            }
        )
    layers: list[dict[str, Any]] = []
    for layer in snapshot["layers"]:
        opacity = layer.get("opacity")
        if opacity is None:
            opacity = 1.0 - float(layer["transparency"])
        representation = "stick" if layer["representation"] == "sticks" else layer["representation"]
        value = {
            "object_name": layer["object_name"],
            "selection": translate_simple_selection(layer["selection"]),
            "color": layer["color"],
            "representation": representation,
            "opacity": float(opacity),
            "label": str(layer.get("label", layer.get("description", layer.get("name")))).strip(),
        }
        if representation == "stick" and layer["color_mode"] == "carbon-and-elements":
            value["elements"] = True
        layers.append(value)
    return {"sources": sources, "layers": layers}


def _attribute(name: str, value: Any) -> str:
    return f'{name}="{html.escape(str(value), quote=True)}"'


def preview_controls(
    record: dict[str, Any],
    artifact_map: dict[str, str],
    *,
    title: str,
    evidence: str,
    record_id: str,
) -> str:
    """Render zero or more safe preview controls for a record."""
    controls: list[str] = []
    snapshots = snapshot_values(record)
    show_title = len(snapshots) > 1
    for snapshot in snapshots:
        scene = normalized_scene(snapshot, artifact_map)
        if scene is None:
            continue
        display_title = str(snapshot.get("title") or title)
        attributes = {
            "data-structure-preview": scene["sources"][0]["href"],
            "data-structure-format": scene["sources"][0]["format"],
            "data-structure-scene": json.dumps(scene, sort_keys=True, separators=(",", ":")),
            "data-structure-title": display_title,
            "data-structure-evidence": snapshot.get("evidence_class") or evidence,
            "data-structure-id": snapshot.get("preview_id") or record_id,
            "aria-label": f"View {display_title} in 3D",
        }
        sequence = snapshot.get("sequence_artifact")
        if isinstance(sequence, dict):
            href = artifact_map.get(sequence.get("path"))
            if isinstance(href, str) and href.startswith("data/artifacts/"):
                attributes["data-structure-sequence"] = json.dumps(
                    {
                        "path": href,
                        "sha256": sequence["sha256"],
                        "bytes": sequence["bytes"],
                        "sequence_id": sequence.get("sequence_id"),
                        "chain": sequence.get("chain"),
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
        encoded = " ".join(_attribute(name, value) for name, value in attributes.items())
        title_label = f'<span class="structure-preview-name">{html.escape(display_title)}</span>' if show_title else ""
        controls.append(
            '<span class="structure-preview-actions">'
            f"{title_label}"
            f'<button type="button" class="structure-preview-trigger" aria-haspopup="dialog" {encoded}>'
            "View in 3D</button>"
            f'<a href="{html.escape(scene["sources"][0]["href"], quote=True)}" download>Download coordinates</a>'
            "</span>"
        )
    return "".join(controls)


def snapshot_record_errors(record: dict[str, Any], *, context: str) -> list[str]:
    errors: list[str] = []
    value = record.get("structure_snapshot")
    if isinstance(value, dict):
        errors.extend(snapshot_errors(value, context=f"{context}.structure_snapshot"))
    elif value is not None:
        errors.append(f"{context}.structure_snapshot must be an object")
    values = record.get("structure_snapshots")
    if isinstance(values, list):
        for index, snapshot in enumerate(values):
            if not isinstance(snapshot, dict):
                errors.append(f"{context}.structure_snapshots[{index}] must be an object")
                continue
            errors.extend(snapshot_errors(snapshot, context=f"{context}.structure_snapshots[{index}]"))
    elif values is not None:
        errors.append(f"{context}.structure_snapshots must be an array")
    return errors
