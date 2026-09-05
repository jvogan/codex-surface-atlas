"""Create a clean, provider-free Surface Atlas workspace."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from .schemas import COLLECTION_SCHEMAS


ATLAS_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PROFILES: dict[str, tuple[int, int, int, int]] = {
    "showcase": (6, 12, 20, 1),
    "standard": (10, 20, 20, 3),
    "broad": (15, 35, 50, 5),
}


class WorkspaceError(ValueError):
    """Raised when a workspace cannot be created safely."""


@dataclass(frozen=True)
class InitializationResult:
    """Machine-readable result returned by :func:`initialize_atlas`."""

    atlas_id: str
    workspace: str
    profile: str
    research_target_cap: None = None
    external_compute_authorized: bool = False
    network_or_provider_calls: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


_WORKSPACE_DIRECTORIES = (
    "evidence",
    "structures",
    "interventions",
    "libraries",
    "screens",
    "opportunities",
    "handoffs",
    "reports",
    "media",
    "receipts",
)


def _template_directory() -> Path:
    return Path(__file__).resolve().parent / "assets" / "templates"


def _render_template(filename: str, replacements: dict[str, str]) -> dict[str, object]:
    path = _template_directory() / filename
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover - package corruption is unusual
        raise WorkspaceError(f"package resource is unavailable: {filename}") from exc
    # Substitute fixed and numeric values first.  Inserting the JSON-escaped
    # user disease last prevents placeholder-looking text in the disease name
    # from being interpreted as another template variable.
    for key, value in replacements.items():
        if key != "DISEASE":
            text = text.replace(f"__{key}__", value)
    text = text.replace("__DISEASE__", replacements["DISEASE"])
    try:
        result = json.loads(text)
    except json.JSONDecodeError as exc:  # pragma: no cover - caught by packaging tests
        raise WorkspaceError(f"package template is invalid: {filename}") from exc
    if not isinstance(result, dict):
        raise WorkspaceError(f"package template must contain an object: {filename}")
    return result


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _validate_inputs(
    atlas_id: str,
    output_directory: Path,
    disease: str,
    profile: str,
    evidence_cutoff: str | None,
) -> str:
    if not isinstance(atlas_id, str) or not ATLAS_ID_PATTERN.fullmatch(atlas_id):
        raise WorkspaceError("atlas_id must contain 3-64 lowercase letters, digits, or hyphens")
    if not isinstance(disease, str) or not disease.strip():
        raise WorkspaceError("disease must be a non-empty string")
    if profile not in PROFILES:
        raise WorkspaceError(f"profile must be one of: {', '.join(sorted(PROFILES))}")
    if evidence_cutoff is None:
        return datetime.now(timezone.utc).date().isoformat()
    if not isinstance(evidence_cutoff, str) or not DATE_PATTERN.fullmatch(evidence_cutoff):
        raise WorkspaceError("evidence_cutoff must use YYYY-MM-DD")
    try:
        date.fromisoformat(evidence_cutoff)
    except ValueError as exc:
        raise WorkspaceError("evidence_cutoff must be a valid calendar date") from exc
    return evidence_cutoff


def initialize_atlas(
    atlas_id: str,
    output_directory: str | Path,
    *,
    disease: str,
    profile: str = "standard",
    evidence_cutoff: str | None = None,
) -> InitializationResult:
    """Create a new atlas workspace without network or provider calls.

    The output path must not exist, including when it is an empty directory.
    This keeps accidental overwrites of an existing research workspace from
    happening through the package CLI.
    """

    output = Path(output_directory)
    cutoff = _validate_inputs(atlas_id, output, disease, profile, evidence_cutoff)
    if output.exists():
        raise WorkspaceError(f"refusing to overwrite existing path: {output}")

    created_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    tier_a, tier_b, tier_c, design_max = PROFILES[profile]
    # The plan template has two kinds of placeholders: quoted text and
    # numeric limits.  JSON escaping for disease is handled before insertion.
    disease_text = json.dumps(disease.strip(), ensure_ascii=False)[1:-1]
    replacements = {
        "ATLAS_ID": atlas_id,
        "CREATED_AT": created_at,
        "DISEASE": disease_text,
        "EVIDENCE_CUTOFF": cutoff,
        "PROFILE": profile,
        "TIER_A": str(tier_a),
        "TIER_B": str(tier_b),
        "TIER_C": str(tier_c),
        "DESIGN_MAX": str(design_max),
    }
    plan = _render_template("atlas-plan.template.json", replacements)
    ledger = _render_template("search-ledger.template.json", replacements)
    collection_template = (_template_directory() / "collection.template.json").read_text(encoding="utf-8")

    collection_payloads: dict[str, dict[str, object]] = {}
    for filename, schema_version in COLLECTION_SCHEMAS.items():
        text = collection_template.replace("__SCHEMA_VERSION__", schema_version).replace("__ATLAS_ID__", atlas_id)
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:  # pragma: no cover - package corruption is unusual
            raise WorkspaceError(f"package template is invalid: {filename}") from exc
        if not isinstance(payload, dict):
            raise WorkspaceError(f"package template must contain an object: {filename}")
        collection_payloads[filename] = payload

    # Prepare all writes only after validation and template loading succeeded.
    output.mkdir(parents=True)
    for directory in _WORKSPACE_DIRECTORIES:
        (output / directory).mkdir()
    _write_json(output / "atlas-plan.json", plan)
    _write_json(output / "search-ledger.json", ledger)
    for filename, payload in collection_payloads.items():
        _write_json(output / filename, payload)

    return InitializationResult(atlas_id, str(output.resolve()), profile)


# Compatibility spelling used by the workbench script and useful to callers
# migrating to the package.
init_atlas = initialize_atlas
