#!/usr/bin/env python3
"""Build a provider-free, offline Codex Surface Atlas HTML report.

The input is an atlas workspace created by ``init_atlas.py`` or populated by
the research workflow.  The report contains static HTML, local data exports,
and local artifact copies.  It never calls a provider or fetches a URL.
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import html
import json
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from .screening_context import screening_role
from .structure_preview import preview_controls


COLLECTION_FILES = (
    "discovered-entities.json",
    "targets.json",
    "excluded-targets.json",
    "interventions.json",
    "molecular-library.json",
    "screening-results.json",
    "structures.json",
    "opportunities.json",
    "capabilities.json",
)
OPTIONAL_BINDER_FILES = (
    "binders.json",
    "binder-controls.json",
    "designed-binders.json",
    "binder-results.json",
    "designs.json",
)
OPTIONAL_SOURCE_FILES = (
    "source-registry.json",
    "run-manifest.json",
)
NAV_ITEMS = (
    ("overview", "Overview", "index.html"),
    ("explore", "Target atlas", "explore.html"),
    ("targets", "Target census", "targets.html"),
    ("action-comparison", "Compare actions", "action-comparison.html"),
    ("sequence-sites", "Sequence & sites", "sequence-sites.html"),
    ("treatments", "Interventions", "treatments.html"),
    ("molecular-library", "Molecules & screens", "molecular-library.html"),
    ("screening", "Screening readout", "screening.html"),
    ("structures", "Structures", "structures.html"),
    ("binders", "Designed binders", "binders.html"),
    ("campaigns", "Campaign runs", "campaigns.html"),
    ("assays", "Assay returns", "assays.html"),
    ("design-sources", "Methods & sources", "design-sources.html"),
    ("study", "Study & coverage", "study.html"),
)
ID_KEYS = (
    "entity_id",
    "target_id",
    "exclusion_id",
    "intervention_id",
    "structure_id",
    "opportunity_id",
    "capability_id",
    "binder_id",
    "candidate_id",
    "design_id",
    "molecule_id",
    "screening_result_id",
    "screening_id",
    "screen_id",
    "result_id",
    "pose_id",
    "id",
)
NAME_KEYS = (
    "preferred_name",
    "target_name",
    "gene_symbol",
    "symbol",
    "protein_name",
    "molecule_name",
    "compound_name",
    "intervention_name",
    "drug_name",
    "ligand_name",
    "candidate_name",
    "name",
    "label",
    "title",
)
REF_KEYS = (
    "target_id",
    "target_ids",
    "target_ref",
    "target_refs",
    "targets",
    "target",
    "gene_symbol",
    "symbol",
    "known_target_ids",
    "known_targets",
)
URL_RE = re.compile(r"^https?://", re.IGNORECASE)
SAFE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")
REGISTRATION_RECEIPT_SCHEMA = "surface-atlas-supplied-library-registration-receipt/v1"
REGISTERED_LIBRARY_SCHEMA = "codex-surface-molecular-library/v0.1"
COLLECTION_ID_KEYS = {
    "discovered-entities.json": ("entity_id",),
    "targets.json": ("target_id",),
    "excluded-targets.json": ("exclusion_id",),
    "interventions.json": ("intervention_id",),
    "molecular-library.json": ("molecule_id",),
    "screening-results.json": ("screening_result_id", "screening_id", "screen_id", "result_id"),
    "structures.json": ("structure_id",),
    "opportunities.json": ("opportunity_id",),
    "capabilities.json": ("capability_id",),
}


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def pretty_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def nonempty(value: Any) -> bool:
    return value is not None and value != "" and value != [] and value != {}


def pick(record: dict[str, Any], *keys: str, default: Any = "") -> Any:
    for key in keys:
        value = record.get(key)
        if nonempty(value):
            return value
    return default


def scalar_text(value: Any, *, empty: str = "Not recorded") -> str:
    if not nonempty(value):
        return empty
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        values = [scalar_text(item, empty="") for item in value]
        return ", ".join(item for item in values if item)
    if isinstance(value, dict):
        for key in ("label", "name", "title", "id", "value", "symbol"):
            if nonempty(value.get(key)):
                return scalar_text(value[key], empty=empty)
        return compact_json(value)
    return str(value)


def count_text(value: Any, *, empty: str = "Not recorded") -> str:
    """Format exact recorded counts without coercing missing values to zero."""
    if isinstance(value, bool):
        return scalar_text(value, empty=empty)
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float) and value.is_integer():
        return f"{int(value):,}"
    return scalar_text(value, empty=empty)


def normalized(value: Any) -> str:
    return scalar_text(value, empty="").strip().casefold()


def record_id(record: dict[str, Any], index: int, prefix: str) -> str:
    for key in ID_KEYS:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return f"{prefix}-{index + 1:04d}"


def typed_record_id(record: dict[str, Any], index: int, prefix: str, *preferred_keys: str) -> str:
    for key in preferred_keys:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return record_id(record, index, prefix)


def record_name(record: dict[str, Any], fallback: str) -> str:
    value = pick(record, *NAME_KEYS, default="")
    if isinstance(value, dict):
        value = pick(value, "label", "name", "title", "symbol", "id", default="")
    text = scalar_text(value, empty="").strip()
    return text or fallback


def slugify(value: str) -> str:
    value = value.casefold()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value[:80] or "record"


def safe_relative(path_text: str) -> PurePosixPath | None:
    try:
        pure = PurePosixPath(path_text)
    except (TypeError, ValueError):
        return None
    if pure.is_absolute() or ".." in pure.parts or not pure.parts:
        return None
    return pure


def read_json(path: Path, *, required: bool = False) -> dict[str, Any]:
    if not path.is_file():
        if required:
            raise FileNotFoundError(f"required atlas file is missing: {path.name}")
        return {"records": []}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError as exc:
        raise ValueError(f"invalid UTF-8 in {path.name}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path.name}: line {exc.lineno}, column {exc.colno}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"atlas file must contain an object: {path.name}")
    return value


def get_records(
    payload: dict[str, Any], *, source_name: str = "atlas file", records_required: bool = False
) -> list[dict[str, Any]]:
    if records_required and "records" not in payload:
        raise ValueError(f"{source_name}: records is required")
    records = payload.get("records", [])
    if not isinstance(records, list):
        raise ValueError(f"{source_name}: records must be an array")
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError(f"{source_name}: records[{index}] must be an object")
    return records


def validate_collection_ids(filename: str, records: list[dict[str, Any]]) -> None:
    keys = COLLECTION_ID_KEYS[filename]
    seen: set[str] = set()
    for index, record in enumerate(records):
        item_id = next(
            (
                value
                for key in keys
                if isinstance((value := record.get(key)), str)
                and value
                and value == value.strip()
            ),
            None,
        )
        if item_id is None:
            raise ValueError(
                f"{filename}: records[{index}] requires a non-empty {keys[0]}"
            )
        if item_id in seen:
            raise ValueError(f"{filename}: duplicate record ID {item_id}")
        seen.add(item_id)


def source_display(source: Any) -> tuple[str, str]:
    if isinstance(source, str):
        return source, source
    if isinstance(source, dict):
        label = scalar_text(pick(source, "title", "label", "name", "source_id", "accession", "id"), empty="source")
        url = scalar_text(pick(source, "url", "href", "link", default=""), empty="")
        return label, url
    return scalar_text(source), ""


def source_links(record: dict[str, Any]) -> list[tuple[str, str]]:
    values: list[Any] = []
    for key in ("source_refs", "sources", "citations", "evidence_refs", "references", "source"):
        value = record.get(key)
        if isinstance(value, list):
            values.extend(value)
        elif nonempty(value):
            values.append(value)
    seen: set[str] = set()
    result: list[tuple[str, str]] = []
    for value in values:
        label, url = source_display(value)
        marker = f"{label}\x00{url}"
        if label and marker not in seen:
            seen.add(marker)
            result.append((label, url))
    return result


def render_source_list(records: Iterable[dict[str, Any]], *, limit: int | None = None) -> str:
    entries: list[tuple[str, str]] = []
    seen: set[str] = set()
    for record in records:
        for label, url in source_links(record):
            key = f"{label}\x00{url}"
            if key not in seen:
                seen.add(key)
                entries.append((label, url))
                if limit is not None and len(entries) >= limit:
                    break
        if limit is not None and len(entries) >= limit:
            break
    if not entries:
        return '<p class="small">No source references are recorded.</p>'
    items: list[str] = []
    for label, url in entries:
        if URL_RE.match(url):
            items.append(f'<li><a href="{esc(url)}">{esc(label)}</a></li>')
        else:
            items.append(f"<li><code>{esc(label)}</code></li>")
    return '<ul class="source-list">' + "".join(items) + "</ul>"


def claim_value(record: dict[str, Any], default: str = "Not classified") -> str:
    value = pick(record, "claim_ceiling", "evidence_class", "evidence_state", "claim", default=default)
    text = scalar_text(value, empty=default)
    lower = text.casefold()
    if any(token in lower for token in ("observed", "experimental", "approved", "clinical", "known", "measured", "source-backed")):
        return text
    if any(token in lower for token in ("inferred", "supported", "predicted")):
        return text
    if any(token in lower for token in ("proposed", "hypothesis", "design")):
        return text
    return text


def claim_class(value: str) -> str:
    lower = value.casefold()
    if any(token in lower for token in ("observed", "experimental", "approved", "clinical", "known", "measured", "source-backed")):
        return "claim-observed"
    if any(token in lower for token in ("inferred", "supported", "predicted")):
        return "claim-inferred"
    if any(token in lower for token in ("proposed", "hypothesis", "design")):
        return "claim-proposed"
    if any(token in lower for token in ("risk", "conflict", "unsafe")):
        return "claim-risk"
    return "claim-unknown"


def claim_pill(record: dict[str, Any], default: str = "Not classified") -> str:
    value = claim_value(record, default)
    return f'<span class="claim {claim_class(value)}">{esc(value)}</span>'


def state_class(value: str) -> str:
    lower = value.casefold()
    if "block" in lower:
        normalized_state = "blocked"
    elif "fail" in lower:
        normalized_state = "failed"
    elif "complete" in lower or lower in {"done", "release ready"}:
        normalized_state = "complete"
    elif "progress" in lower or "running" in lower:
        normalized_state = "in-progress"
    elif "plan" in lower or "pending" in lower or "unrun" in lower:
        normalized_state = "pending"
    elif "executed" in lower:
        normalized_state = "executed"
    elif "validated" in lower:
        normalized_state = "artifact-validated"
    elif "visible" in lower:
        normalized_state = "visible"
    elif "bound" in lower:
        normalized_state = "bound"
    elif "catalog" in lower:
        normalized_state = "catalogued"
    elif "skip" in lower:
        normalized_state = "skipped"
    elif "not applicable" in lower:
        normalized_state = "not-applicable"
    else:
        normalized_state = re.sub(r"[^a-z0-9]+", "-", lower).strip("-")
    return "state-" + normalized_state


def state_pill(value: Any, default: str = "not recorded") -> str:
    text = scalar_text(value, empty=default)
    class_name = "tag" if re.match(r"^\d", text) else f"state {state_class(text)}"
    return f'<span class="{class_name}">{esc(text)}</span>'


def field_html(label: str, value: Any, *, mono: bool = False) -> str:
    text = scalar_text(value)
    class_name = ' class="mono"' if mono and text != "Not recorded" else ""
    return f"<dt>{esc(label)}</dt><dd{class_name}>{esc(text)}</dd>"


def field_list_html(fields: Iterable[tuple[Any, ...]]) -> str:
    rendered_parts: list[str] = []
    for item in fields:
        if len(item) == 2:
            label, value = item
            mono = False
        else:
            label, value, mono = item[:3]
        rendered_parts.append(field_html(label, value, mono=bool(mono)))
    rendered = "".join(rendered_parts)
    return f'<dl class="field-list">{rendered}</dl>'


def empty_state(title: str, detail: str, link: str | None = None) -> str:
    extra = f' <a href="{esc(link)}">Open the data export.</a>' if link else ""
    return f'<div class="empty-state"><strong>{esc(title)}</strong><span>{esc(detail)}</span>{extra}</div>'


def section(title: str, body: str, *, kicker: str = "") -> str:
    kicker_html = f'<p class="eyebrow">{esc(kicker)}</p>' if kicker else ""
    return f'<section class="section"><div class="section-heading"><div>{kicker_html}<h2>{esc(title)}</h2></div></div>{body}</section>'


def link_html(href: str, label: str, *, download: bool = False) -> str:
    download_attr = " download" if download else ""
    return f'<a href="{esc(href)}"{download_attr}>{esc(label)}</a>'


def collect_refs(record: dict[str, Any]) -> set[str]:
    refs: set[str] = set()

    def visit(value: Any) -> None:
        if isinstance(value, str) and value.strip():
            refs.add(value.strip())
        elif isinstance(value, list):
            for item in value:
                visit(item)
        elif isinstance(value, dict):
            for key in ("id", "target_id", "target_ref", "gene_symbol", "symbol", "name", "label"):
                if nonempty(value.get(key)):
                    visit(value[key])

    for key in REF_KEYS:
        if key in record:
            visit(record[key])
    return refs


def related(record: dict[str, Any], target_id: str, target_name: str) -> bool:
    refs = {normalized(value) for value in collect_refs(record)}
    return normalized(target_id) in refs or normalized(target_name) in refs


def target_profile(record: dict[str, Any], index: int) -> dict[str, Any]:
    from .report_presentation import cell_population_summary
    target_id = typed_record_id(record, index, "target", "target_id", "entity_id")
    name = record_name(record, target_id)
    context = record.get("disease_context") if isinstance(record.get("disease_context"), dict) else {}
    surface = record.get("surface_evidence") if isinstance(record.get("surface_evidence"), dict) else {}
    reviewed = surface.get("reviewed_uniprot") if isinstance(surface.get("reviewed_uniprot"), dict) else {}
    topology_annotations = [label for key, label in (("gpi_anchored", "GPI anchored"), ("integral_membrane", "integral membrane"), ("extracellular_topology", "extracellular topology annotated"), ("plasma_membrane", "plasma membrane")) if reviewed.get(key) is True]
    risk = record.get("risk") if isinstance(record.get("risk"), dict) else {}
    risk_summary = ""
    if risk:
        risk_summary = scalar_text(risk.get("assessment_state"), empty="Partial assessment").replace("-", " ") + "; recorded warning signals, not a normal-tissue safety assessment."
    return {
        "id": target_id,
        "name": name,
        "slug": slugify(f"{name}-{target_id}"),
        "record": record,
        "entity_class": pick(record, "entity_class", "entity_type", "class", "molecule_type"),
        "cell_owner": cell_population_summary(pick(record, "cell_owner", "cell_type", "compartment", "owner")),
        "surface": pick(record, "surface_evidence", "surface_accessibility", "surface_state", "accessibility"),
        "priority": target_priority(record),
        "tier": pick(record, "structure_tier", "structure_wave", "resource_tier", default="Evidence only"),
        "topology": pick(record, "topology", "membrane_topology", "orientation", default=", ".join(topology_annotations)),
        "normal_risk": pick(record, "normal_tissue_risk", "normal_accessibility_risk", "safety_risk", "normal_risk", default=risk_summary),
        "risk_label": "Normal-tissue risk" if any(nonempty(record.get(key)) for key in ("normal_tissue_risk", "normal_accessibility_risk", "normal_risk")) else "Recorded warning assessment",
        "disease_evidence": pick(record, "disease_evidence", "disease_state", "prevalence", default=pick(context, "disease_name", "name", default=record.get("disease_context"))),
        "disease_evidence_label": "Disease evidence" if any(nonempty(record.get(key)) for key in ("disease_evidence", "disease_state", "prevalence")) else "Disease context",
        "isoforms": pick(record, "isoforms", "isoform", "sequence_ids"),
        "extracellular_region": pick(record, "extracellular_region", "extracellular_regions", "ectodomain", "domain"),
    }


def surface_evidence_summary(value: Any) -> str:
    """Project structured surface evidence to a concise table-safe label."""
    if not isinstance(value, dict):
        return scalar_text(value)
    decision = scalar_text(value.get("decision"), empty="").strip().replace("-", " ").title()
    signals: list[str] = []
    if value.get("tcsa_global_membership") is True:
        signals.append("TCSA surfaceome")
    reviewed = value.get("reviewed_uniprot")
    if isinstance(reviewed, dict):
        if reviewed.get("extracellular_topology") is True:
            signals.append("UniProt extracellular topology")
        elif reviewed.get("gpi_anchored") is True:
            signals.append("UniProt GPI anchor")
        elif reviewed.get("integral_membrane") is True and reviewed.get("plasma_membrane") is True:
            signals.append("UniProt integral membrane")
        elif reviewed.get("direct_cell_surface_text") is True:
            signals.append("UniProt cell-surface annotation")
    if not signals:
        reason_code = scalar_text(value.get("reason_code"), empty="").strip()
        if reason_code:
            signals.append(reason_code.replace("-", " "))
    parts = [part for part in (decision, " + ".join(signals)) if part]
    return " · ".join(parts) or "Structured evidence recorded"


def target_priority(record: dict[str, Any]) -> dict[str, Any]:
    """Return exact display and sort values for a target priority field."""
    for key in ("priority_score", "priority", "rank", "score"):
        value = record.get(key)
        if nonempty(value):
            return {"display": scalar_text(value), "sort": value, "source": key}
    evidence_score = record.get("evidence_score")
    if isinstance(evidence_score, dict) and nonempty(evidence_score.get("score")):
        score = evidence_score["score"]
        maximum = evidence_score.get("maximum")
        display = scalar_text(score)
        if nonempty(maximum):
            display += f" / {scalar_text(maximum)}"
        return {"display": display, "sort": score, "source": "evidence_score"}
    return {"display": "Not recorded", "sort": "", "source": ""}


def unique_slugs(profiles: list[dict[str, Any]]) -> None:
    seen: dict[str, int] = {}
    for profile in profiles:
        base = profile["slug"]
        count = seen.get(base, 0)
        seen[base] = count + 1
        if count:
            profile["slug"] = f"{base}-{count + 1}"


def table_cell(content: str, sort_value: Any = "") -> tuple[str, str]:
    return content, scalar_text(sort_value, empty="")


def render_table(
    table_id: str,
    headers: list[str],
    rows: list[list[tuple[str, Any]]],
    *,
    caption: str,
    filter_label: str | None = None,
    sort_labels: list[tuple[int, str]] | None = None,
    page_size: int = 50,
) -> str:
    if not rows:
        return empty_state("No records are present", caption)
    toolbar = ""
    if filter_label or sort_labels:
        controls: list[str] = []
        if filter_label:
            controls.append(
                f'<div class="toolbar-field"><label for="filter-{esc(table_id)}">{esc(filter_label)}</label>'
                f'<input id="filter-{esc(table_id)}" name="filter-{esc(table_id)}" type="search" '
                f'autocomplete="off" spellcheck="false" aria-controls="{esc(table_id)}" '
                f'data-table-filter="{esc(table_id)}" placeholder="Name, ID, or keyword…"></div>'
            )
        if sort_labels:
            options = ['<option value="">Original order</option>']
            options.extend(f'<option value="{index}">{esc(label)}</option>' for index, label in sort_labels)
            controls.append(
                f'<div class="toolbar-sort"><label for="sort-{esc(table_id)}">Sort</label>'
                f'<select id="sort-{esc(table_id)}" name="sort-{esc(table_id)}" '
                f'aria-controls="{esc(table_id)}" data-table-sort="{esc(table_id)}">{"".join(options)}</select></div>'
            )
        toolbar = f'<div class="table-toolbar">{"".join(controls)}</div>'
    head = "".join(f"<th scope=\"col\">{esc(header)}</th>" for header in headers)
    body_rows: list[str] = []
    for row in rows:
        cells = []
        for content, sort_value in row:
            cells.append(f'<td data-sort-value="{esc(sort_value)}">{content}</td>')
        body_rows.append("<tr>" + "".join(cells) + "</tr>")
    pagination = (
        f'<div class="pagination"><span class="table-status" role="status" aria-live="polite" '
        f'data-table-status="{esc(table_id)}"></span>'
        f'<div class="pagination-controls"><button type="button" aria-controls="{esc(table_id)}" '
        f'data-table-previous="{esc(table_id)}">Previous</button>'
        f'<button type="button" aria-controls="{esc(table_id)}" '
        f'data-table-next="{esc(table_id)}">Next</button></div></div>'
    )
    return (
        toolbar
        + f'<div class="table-wrap"><table id="{esc(table_id)}" data-table data-page-size="{page_size}">'
        + f'<caption>{esc(caption)}</caption><thead><tr>{head}</tr></thead><tbody>{"".join(body_rows)}</tbody></table></div>'
        + pagination
    )


def render_downloads(files: Iterable[tuple[str, str, bool]]) -> str:
    links = [link_html(href, label, download=download) for label, href, download in files]
    if not links:
        return ""
    return '<div class="download-row"><span class="small">Downloads:</span>' + " · ".join(links) + "</div>"


def discover_receipts(root: Path) -> list[dict[str, Any]]:
    """Read local and configured artifact-root receipts without exporting paths."""
    search_roots = [root]
    config_path = root / ".surface-atlas-local.json"
    if config_path.is_file():
        try:
            config = read_json(config_path)
        except ValueError:
            config = {}
        artifact_root = config.get("artifact_root")
        if isinstance(artifact_root, str):
            candidate = Path(artifact_root)
            if candidate.is_dir():
                search_roots.append(candidate)
    paths: set[Path] = set()
    for search_root in search_roots:
        paths.update(path for path in search_root.rglob("*.json") if "receipt" in path.name.casefold())
    receipts: list[dict[str, Any]] = []
    for path in sorted(paths):
        try:
            payload = read_json(path)
        except (OSError, ValueError):
            continue
        if nonempty(payload.get("schema_version")):
            receipts.append(payload)
    return receipts


def receipt_for(receipts: list[dict[str, Any]], schema_prefix: str) -> dict[str, Any] | None:
    matches = [
        receipt
        for receipt in receipts
        if scalar_text(receipt.get("schema_version"), empty="").startswith(schema_prefix)
    ]
    if not matches:
        return None
    # Prefer compilation receipts over individual request receipts when both exist.
    return max(matches, key=lambda item: len(compact_json(item)))


def receipt_time(receipt: dict[str, Any] | None) -> str:
    if not receipt:
        return ""
    return scalar_text(
        pick(receipt, "generated_at", "resolved_at", "retrieved_at", "created_at", default=""),
        empty="",
    )


def exact_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def derive_report_state(
    root: Path,
    plan: dict[str, Any],
    ledger: dict[str, Any],
    collections: dict[str, list[dict[str, Any]]],
    binders: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Overlay stale planning state with observations from exact workspace artifacts."""
    effective_plan = copy.deepcopy(plan)
    effective_ledger = copy.deepcopy(ledger)
    receipts = discover_receipts(root)

    literature = receipt_for(receipts, "codex-surface-literature-compiler-receipt/")
    open_targets = receipt_for(receipts, "codex-surface-opentargets-compilation-result/")
    tcsa = receipt_for(receipts, "codex-surface-tcsa-receipt/")
    trials = receipt_for(receipts, "codex-surface-clinicaltrials-compilation-result/")
    reconciliation = receipt_for(receipts, "codex-surface-target-reconciliation-receipt/")
    molecule_resolution = receipt_for(receipts, "codex-surface-molecular-library-resolution-receipt/")

    discovered_count = len(collections.get("discovered-entities.json", []))
    target_count = len(collections.get("targets.json", []))
    excluded_count = len(collections.get("excluded-targets.json", []))
    intervention_count = len(collections.get("interventions.json", []))
    molecule_count = len(collections.get("molecular-library.json", []))
    screening_count = len(collections.get("screening-results.json", []))
    structure_records = collections.get("structures.json", [])
    structure_count = len(structure_records)
    opportunity_count = len(collections.get("opportunities.json", []))

    reconciled = False
    unresolved_count: int | None = None
    if reconciliation:
        unresolved_count = exact_int(reconciliation.get("unresolved_count"))
        reconciled = (
            reconciliation.get("disposition_accounting_complete") is True
            and exact_int(reconciliation.get("discovered_entity_count")) == discovered_count
            and exact_int(reconciliation.get("surface_target_count")) == target_count
            and exact_int(reconciliation.get("excluded_count")) == excluded_count
            and unresolved_count is not None
            and target_count + excluded_count + unresolved_count == discovered_count
        )
    if unresolved_count is None:
        unresolved_count = sum(
            1
            for record in collections.get("discovered-entities.json", [])
            if record.get("surface_disposition") == "unresolved"
        )

    evidence_counts: list[dict[str, Any]] = []
    executed_sources: list[dict[str, Any]] = []

    def add_source(source_id: str, source_class: str, timestamp: str, records: Any, detail: str) -> None:
        executed_sources.append(
            {
                "query_id": source_id,
                "source_class": source_class,
                "status": "complete",
                "retrieved_at": timestamp,
                "records": records,
                "detail": detail,
            }
        )

    def add_count(label: str, value: Any) -> None:
        if exact_int(value) is not None:
            evidence_counts.append({"label": label, "value": value})

    if literature:
        counts = literature.get("counts", {}) if isinstance(literature.get("counts"), dict) else {}
        unique = exact_int(counts.get("unique_record_count"))
        memberships = exact_int(counts.get("emitted_membership_count"))
        if unique is not None:
            detail = f"{count_text(unique)} unique PubMed records"
            if memberships is not None:
                detail += f" across {count_text(memberships)} query memberships"
            add_source("PubMed literature corpus", "literature", receipt_time(literature), unique, detail)
            add_count("Unique literature records", unique)
            add_count("Duplicate query memberships", counts.get("duplicate_query_membership_count"))
            add_count("Missing or merged PMIDs", counts.get("missing_or_merged_pmid_count"))

    if open_targets:
        discovered = exact_int(open_targets.get("total_discovered_entity_count"))
        associated = exact_int(open_targets.get("compiled_associated_target_count"))
        if discovered is not None:
            detail = f"{count_text(discovered)} discovered entities"
            if associated is not None:
                detail += f"; {count_text(associated)} disease-associated targets"
            add_source("Open Targets", "disease association", receipt_time(open_targets), discovered, detail)
        matched = exact_int(open_targets.get("uniprot_matched_entity_count"))
        if matched is not None:
            add_source("UniProt reviewed human proteins", "sequence and topology", receipt_time(open_targets), matched, f"{count_text(matched)} discovered entities matched to reviewed UniProt records")
            add_count("Reviewed UniProt matches", matched)

    if tcsa:
        counts = tcsa.get("counts", {}) if isinstance(tcsa.get("counts"), dict) else {}
        global_count = exact_int(counts.get("global_gesp_records"))
        coad_count = exact_int(counts.get("cancer_specific_gesp_records"))
        single_cell_count = exact_int(counts.get("single_cell_gene_records"))
        if global_count is not None:
            detail_parts = [f"{count_text(global_count)} global surface-protein records"]
            if coad_count is not None:
                detail_parts.append(f"{count_text(coad_count)} COAD-specific candidates")
            if single_cell_count is not None:
                detail_parts.append(f"{count_text(single_cell_count)} single-cell gene rows")
            add_source("Cancer Surfaceome Atlas", "surfaceome and single-cell context", receipt_time(tcsa), global_count, "; ".join(detail_parts))
        add_count("Global surface-protein records", global_count)
        add_count("COAD-specific surface candidates", coad_count)
        add_count("Single-cell gene rows", single_cell_count)

    if trials:
        study_count = exact_int(trials.get("unique_nct_id_count"))
        entry_count = exact_int(trials.get("registry_intervention_entry_count"))
        if study_count is not None:
            detail = f"{count_text(study_count)} unique registry studies"
            if entry_count is not None:
                detail += f"; {count_text(entry_count)} intervention entries"
            add_source("ClinicalTrials.gov", "interventions and trials", receipt_time(trials), study_count, detail)
        add_count("Registry studies", study_count)
        add_count("Registry intervention entries", entry_count)
        add_count("Target assignments", trials.get("target_assignment_count"))

    if molecule_resolution:
        resolved = exact_int(molecule_resolution.get("resolved_count"))
        unresolved_molecules = exact_int(molecule_resolution.get("unresolved_count"))
        record_count = exact_int(molecule_resolution.get("record_count"))
        if record_count is not None:
            detail = f"{count_text(resolved)} identities resolved" if resolved is not None else f"{count_text(record_count)} library records"
            if unresolved_molecules is not None:
                detail += f"; {count_text(unresolved_molecules)} unresolved"
            add_source("PubChem identity resolution", "molecular library", receipt_time(molecule_resolution), record_count, detail)
        add_count("Resolved molecule identities", resolved)
        add_count("Unresolved molecule identities", unresolved_molecules)

    rcsb_accessions = {
        scalar_text(pick(record, "accession", "pdb_id", default=""), empty="").upper()
        for record in structure_records
        if nonempty(pick(record, "accession", "pdb_id", default=""))
    }
    if rcsb_accessions:
        timestamps = [scalar_text(pick(record, "retrieval_date", "retrieved_at", default=""), empty="") for record in structure_records]
        add_source("RCSB Protein Data Bank", "structures and complexes", max(timestamps, default=""), len(rcsb_accessions), f"{count_text(len(rcsb_accessions))} distinct experimental entries")
        add_count("Distinct experimental PDB entries", len(rcsb_accessions))

    if reconciled:
        add_source("Surface-target reconciliation", "census reconciliation", receipt_time(reconciliation), discovered_count, f"{count_text(discovered_count)} entities fully accounted across retained, excluded, and unresolved states")

    counts = effective_ledger.get("counts")
    if not isinstance(counts, dict):
        counts = {}
        effective_ledger["counts"] = counts
    counts.update(
        {
            "normalized_discovered_entities": discovered_count,
            "surface_targets": target_count,
            "excluded_from_surface_universe": excluded_count,
            "unresolved_records": unresolved_count,
        }
    )

    if reconciled:
        effective_ledger["coverage_state"] = "complete_within_recorded_scope"
    elif executed_sources:
        effective_ledger["coverage_state"] = "in-progress"
    effective_ledger["_report_state"] = {
        "executed_sources": executed_sources,
        "evidence_counts": evidence_counts,
        "receipt_schema_versions": sorted(
            {
                scalar_text(receipt.get("schema_version"), empty="")
                for receipt in receipts
                if nonempty(receipt.get("schema_version"))
            }
        ),
        "census_accounting_validated": reconciled,
    }

    stages = effective_plan.get("stages", [])
    if isinstance(stages, list) and plan.get("data_kind") != "synthetic":
        stage_by_id = {stage.get("stage_id"): stage for stage in stages if isinstance(stage, dict)}

        def set_stage(stage_id: str, state: str, *, clear_external_blocker: bool = False) -> None:
            stage = stage_by_id.get(stage_id)
            if not isinstance(stage, dict):
                return
            order = {"blocked": 0, "pending": 1, "in-progress": 2, "complete": 3}
            current = scalar_text(stage.get("state"), empty="pending")
            if order.get(state, 0) >= order.get(current, 0):
                stage["state"] = state
            if clear_external_blocker and isinstance(stage.get("blocked_by"), list):
                stage["blocked_by"] = [item for item in stage["blocked_by"] if item != "external-work-not-authorized"]

        query_plan = read_json(root / "query-plan.json") if (root / "query-plan.json").is_file() else {}
        if query_plan:
            set_stage("G1", "complete")
        if any((literature, open_targets, tcsa, trials)):
            set_stage("G2", "complete")
        if discovered_count:
            set_stage("G3", "complete")
        if reconciled:
            set_stage("G4", "complete")
            set_stage("G6", "complete")
        if intervention_count or molecule_count:
            set_stage("G5", "complete")
        targets = collections.get("targets.json", [])
        if targets and all(nonempty(pick(record, "structure_tier", "structure_wave", "resource_tier", default="")) for record in targets):
            set_stage("G7", "complete")
        if structure_count:
            set_stage("G8", "in-progress")
        if opportunity_count or screening_count:
            set_stage("G9", "in-progress")
        external = effective_plan.get("external_work", {}) if isinstance(effective_plan.get("external_work"), dict) else {}
        if binders:
            set_stage("G10", "complete", clear_external_blocker=True)
        elif external.get("compute_authorized") is True:
            set_stage("G10", "in-progress", clear_external_blocker=True)
        set_stage("G11", "complete")

    if plan.get("data_kind") == "synthetic":
        execution = "Synthetic example · no research or model execution"
    elif binders or screening_count:
        execution = "Atlas with screening or design records"
    elif structure_count and reconciled:
        execution = "Evidence and structure atlas executed"
    elif reconciled:
        execution = "Evidence atlas executed"
    elif executed_sources:
        execution = "Research retrieval executed"
    else:
        execution = execution_label(plan)
    effective_plan["_report_state"] = {
        "execution_label": execution,
        "source_mode": scalar_text(plan.get("mode"), empty="not recorded"),
        "observed_collection_counts": {
            "discovered_entities": discovered_count,
            "targets": target_count,
            "excluded_targets": excluded_count,
            "interventions": intervention_count,
            "molecules": molecule_count,
            "structures": structure_count,
            "screening_results": screening_count,
            "designed_binders": len(binders),
        },
    }
    return effective_plan, effective_ledger


def execution_label(plan: dict[str, Any]) -> str:
    report_state = plan.get("_report_state")
    if isinstance(report_state, dict) and nonempty(report_state.get("execution_label")):
        return scalar_text(report_state["execution_label"])
    mode = scalar_text(plan.get("mode"), empty="unclassified")
    mapping = {
        "plan-only": "Plan only",
        "public-evidence": "Public evidence atlas",
        "frozen-demo-replay": "Frozen demo replay",
        "live-extension": "Live extension",
    }
    return mapping.get(mode, mode)


def coverage_label(ledger: dict[str, Any]) -> str:
    value = scalar_text(ledger.get("coverage_state"), empty="not recorded")
    mapping = {
        "planned": "Search coverage planned",
        "in-progress": "Search coverage in progress",
        "complete_within_recorded_scope": "Searched in-scope target census",
        "partial": "Search coverage partial",
        "blocked": "Search coverage blocked",
    }
    return mapping.get(value, value)


def page_html(
    *,
    title: str,
    current: str,
    atlas_id: str,
    plan: dict[str, Any],
    body: str,
    generated_at: str,
) -> str:
    nav: list[str] = []
    from .report_workflows import insert_page_diagram
    body = insert_page_diagram(body, current, title)
    for key, label, href in NAV_ITEMS:
        current_attr = ' aria-current="page"' if current == key else ""
        nav.append(f'<a href="{href}"{current_attr}>{esc(label)}</a>')
    execution = execution_label(plan)
    example_notice = (
        '<aside class="example-notice" role="note"><strong>Synthetic example.</strong> '
        'All targets and records are invented. No database retrieval or model run.</aside>'
        if plan.get("data_kind") == "synthetic" else ""
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#FFFFFF">
  <meta name="description" content="Codex Surface Atlas report for {esc(atlas_id)}">
  <title>{esc(title)} · Codex Surface Atlas</title>
  <link rel="stylesheet" href="assets/report.css">
  <link rel="stylesheet" href="assets/presentation.css">
  <link rel="stylesheet" href="assets/workflows.css">
  <link rel="stylesheet" href="assets/diagrams.css">
  <link rel="stylesheet" href="assets/structure-preview.css">
  <link rel="stylesheet" href="assets/sequence-sites.css">
  <link rel="stylesheet" href="assets/action-comparison.css">
  <script defer src="assets/report.js"></script>
  <script defer src="assets/presentation.js"></script>
  <script defer src="assets/structure-preview.js"></script>
  <script defer src="assets/sequence-sites.js"></script>
  <script defer src="assets/action-comparison.js"></script>
</head>
<body>
  <a class="skip-link" href="#main">Skip to content</a>
  <header class="atlas-header">
    <div class="header-inner">
      <div class="brand"><a href="index.html">Codex Surface Atlas</a><span class="brand-id">{esc(atlas_id)}</span></div>
      <nav class="main-nav" aria-label="Atlas sections">{"".join(nav)}</nav>
    </div>
  </header>
  <main id="main" class="page-shell">
    {example_notice}
    {body}
  </main>
  <footer class="footer">
    <div>Generated {esc(generated_at)} · {esc(execution)} · {esc(coverage_label(plan.get("_ledger", {})))}</div>
    <div>This report is self-contained. Source links may open outside the report; the report's core data and local files are included here.</div>
  </footer>
</body>
</html>
"""


def page_heading(eyebrow: str, title: str, lede: str = "", *, pills: str = "") -> str:
    lede_html = f'<p class="lede">{esc(lede)}</p>' if lede else ""
    pills_html = f'<div class="status-line">{pills}</div>' if pills else ""
    return f'<div class="page-heading"><p class="eyebrow">{esc(eyebrow)}</p><h1>{esc(title)}</h1>{lede_html}{pills_html}</div>'


def render_metrics(metrics: list[tuple[str, Any]]) -> str:
    return '<dl class="metrics">' + "".join(
        f'<div class="metric"><dt>{esc(label)}</dt><dd>{esc(count_text(value, empty="0"))}</dd></div>'
        for label, value in metrics
    ) + "</dl>"


def render_stages(plan: dict[str, Any]) -> str:
    stages = plan.get("stages", [])
    if not isinstance(stages, list) or not stages:
        return empty_state("No stage records are present", "The plan has no staged goals to display.")
    items: list[str] = []
    for stage in stages:
        if not isinstance(stage, dict):
            continue
        stage_id = scalar_text(stage.get("stage_id"), empty="stage")
        name = scalar_text(stage.get("name"), empty="Unnamed stage").replace("-", " ")
        blocker = stage.get("blocked_by")
        blocker_html = f'<div class="stage-blocker">Blocker: {esc(scalar_text(blocker))}</div>' if nonempty(blocker) else ""
        items.append(
            f'<li class="stage-item"><span class="stage-code">{esc(stage_id)}</span>'
            f'<div><div class="stage-name">{esc(name)}</div>{blocker_html}</div>'
            f'{state_pill(stage.get("state"), "not recorded")}</li>'
        )
    return '<ol class="stage-list">' + "".join(items) + "</ol>"


def render_contract(plan: dict[str, Any]) -> str:
    disease = plan.get("disease", {}) if isinstance(plan.get("disease"), dict) else {}
    scope = plan.get("scope", {}) if isinstance(plan.get("scope"), dict) else {}
    external = plan.get("external_work", {}) if isinstance(plan.get("external_work"), dict) else {}
    requests = scope.get("requested_actions", [])
    request_text = ", ".join(scalar_text(item) for item in requests) if isinstance(requests, list) and requests else "Not recorded"
    return field_list_html(
        (
            ("Disease", pick(disease, "name", "label")),
            ("Subtype", disease.get("subtype")),
            ("Population", disease.get("population")),
            ("Organism", disease.get("organism")),
            ("Evidence cutoff", scope.get("evidence_cutoff"), True),
            ("Purpose", scope.get("purpose")),
            ("Data posture", scope.get("data_posture")),
            ("Requested work", request_text),
            ("External compute authorized", external.get("compute_authorized")),
            ("Experimental submission authorized", external.get("experimental_submission_authorized")),
        )
    )


def render_coverage(ledger: dict[str, Any]) -> str:
    counts = ledger.get("counts", {}) if isinstance(ledger.get("counts"), dict) else {}
    report_state = ledger.get("_report_state", {}) if isinstance(ledger.get("_report_state"), dict) else {}
    executed_sources = report_state.get("executed_sources", [])
    registered_sources = ledger.get("sources", []) if isinstance(ledger.get("sources"), list) else []
    registered_has_execution = any(
        isinstance(source, dict) and source.get("status") not in {None, "planned"}
        for source in registered_sources
    )
    source_records = registered_sources if registered_has_execution else executed_sources
    if not isinstance(source_records, list) or not source_records:
        source_records = registered_sources

    def source_detail(source: dict[str, Any]) -> str:
        parts: list[str] = []
        detail = scalar_text(source.get("detail"), empty="").strip()
        unit = scalar_text(source.get("record_unit"), empty="").strip()
        limitation = scalar_text(source.get("limitation"), empty="").strip()
        if detail:
            parts.append(detail)
        elif unit:
            parts.append(unit)
        if limitation:
            parts.append(f"Limitation: {limitation}")
        return " ".join(parts) or "Not recorded"

    rows = [
        [table_cell(esc(scalar_text(source.get("query_id"), empty="query")), source.get("query_id")),
         table_cell(esc(scalar_text(source.get("source_class"), empty="not recorded")), source.get("source_class")),
         table_cell(state_pill(source.get("status"), "not recorded"), source.get("status")),
         table_cell(esc(count_text(pick(source, "records", "record_count", default=""))), pick(source, "records", "record_count", default="")),
         table_cell(esc(source_detail(source)), source_detail(source)),
         table_cell(esc(scalar_text(source.get("retrieved_at", source.get("retrieval_time")), empty="Not recorded")), source.get("retrieved_at", source.get("retrieval_time")))]
        for source in source_records
        if isinstance(source, dict)
    ]
    table = render_table(
        "coverage-sources",
        ["Source or query", "Evidence class", "Status", "Records", "Recorded result", "Retrieved"],
        rows,
        caption="Executed evidence sources when receipts are present; otherwise registered source requests and their current state.",
        filter_label="Filter evidence sources",
        sort_labels=[(0, "Query"), (1, "Source class"), (2, "Status")],
    )
    count_body = field_list_html(
        (
            ("Normalized entities", count_text(counts.get("normalized_discovered_entities"))),
            ("Surface targets", count_text(counts.get("surface_targets"))),
            ("Excluded from surface universe", count_text(counts.get("excluded_from_surface_universe"))),
            ("Unresolved records", count_text(counts.get("unresolved_records"))),
        )
    )
    evidence_counts = report_state.get("evidence_counts", [])
    if isinstance(evidence_counts, list) and evidence_counts:
        count_body += '<h3 class="minor-heading">Evidence corpus</h3>'
        count_body += field_list_html(
            (
                (scalar_text(item.get("label"), empty="Recorded count"), count_text(item.get("value")))
                for item in evidence_counts
                if isinstance(item, dict)
            )
        )
    return f'<div class="grid-2"><div class="panel panel-white">{count_body}</div><div>{table}</div></div>'


def render_study(
    plan: dict[str, Any],
    ledger: dict[str, Any],
    collections: dict[str, list[dict[str, Any]]],
    binders: list[dict[str, Any]],
    generated_at: str,
) -> str:
    disease = plan.get("disease", {}) if isinstance(plan.get("disease"), dict) else {}
    counts = ledger.get("counts", {}) if isinstance(ledger.get("counts"), dict) else {}
    unresolved = sum(1 for record in collections.get("discovered-entities.json", []) if record.get("surface_disposition") == "unresolved")
    if "unresolved_records" in counts:
        unresolved = counts.get("unresolved_records", unresolved)
    target_count = len(collections.get("targets.json", []))
    excluded_count = len(collections.get("excluded-targets.json", []))
    intervention_count = len(collections.get("interventions.json", []))
    structure_count = len(collections.get("structures.json", []))
    opportunity_count = len(collections.get("opportunities.json", []))
    molecule_count = len(collections.get("molecular-library.json", []))
    screening_count = len(collections.get("screening-results.json", []))
    pills = '<span class="tag">Uncapped discovery ledger</span>'
    pills += state_pill(execution_label(plan), "not recorded")
    pills += state_pill(coverage_label(ledger), "not recorded")
    body = page_heading(
        "Study",
        scalar_text(pick(disease, "name", "label"), empty="Codex Surface Atlas"),
        "Review the disease, study population, searched sources, and recorded work.",
        pills=pills,
    )
    body += render_metrics(
        [
            ("Retained targets", target_count),
            ("Discovered entities", len(collections.get("discovered-entities.json", []))),
            ("Excluded", excluded_count),
            ("Unresolved", unresolved),
            ("Interventions", intervention_count),
            ("Structures", structure_count),
            ("Molecule library", molecule_count),
            ("Prospective screens", screening_count),
            ("Design opportunities", opportunity_count),
            ("Designed binders", len(binders)),
        ]
    )
    body += section("Disease and study scope", render_contract(plan), kicker="Scope")
    body += section("Search coverage", render_coverage(ledger), kicker="Evidence")
    body += section("Research stages", render_stages(plan), kicker="Execution")
    limitations = ledger.get("limitations", [])
    if not isinstance(limitations, list):
        limitations = [limitations]
    limitations_body = (
        '<ul class="link-list">' + "".join(f"<li>{esc(scalar_text(item))}</li>" for item in limitations if nonempty(item)) + "</ul>"
        if any(nonempty(item) for item in limitations)
        else '<p class="small">No limitations are recorded in the search ledger.</p>'
    )
    body += section("Recorded limitations", limitations_body, kicker="Reading guide")
    body += section(
        "Open the data library",
        '<p>Every page is backed by local JSON and CSV exports. The report keeps retained targets visible when structure or design work has not been run.</p>'
        + render_downloads(
            [
                ("Full atlas JSON", "data/atlas.json", True),
                ("Targets CSV", "data/targets.csv", True),
                ("Molecule library CSV", "data/molecular-library.csv", True),
                ("Screening results CSV", "data/screening-results.csv", True),
                ("Run manifest", "run-manifest.json", True),
            ]
        ),
        kicker="Portable output",
    )
    return body


def render_targets(profiles: list[dict[str, Any]]) -> str:
    pills = state_pill(f"{len(profiles)} retained records", "not recorded")
    body = page_heading(
        "Targets",
        "Target census",
        "Browse every retained target, compare evidence, and open its structure-review assignment.",
        pills=pills,
    )
    rows: list[list[tuple[str, Any]]] = []
    for profile in profiles:
        record = profile["record"]
        dossier = f'target-{esc(profile["slug"])}.html'
        name_html = f'<a class="table-primary" href="{dossier}">{esc(profile["name"])}</a>'
        rows.append(
            [
                table_cell(name_html, profile["name"]),
                table_cell(f'<span class="table-id">{esc(profile["id"])}</span>', profile["id"]),
                table_cell(esc(scalar_text(profile["entity_class"])), profile["entity_class"]),
                table_cell(esc(scalar_text(profile["cell_owner"])), profile["cell_owner"]),
                table_cell(esc(surface_evidence_summary(profile["surface"])), surface_evidence_summary(profile["surface"])),
                table_cell(esc(profile["priority"]["display"]), profile["priority"]["sort"]),
                table_cell(esc(scalar_text(profile["tier"], empty="Evidence only")), profile["tier"]),
                table_cell(claim_pill(record), claim_value(record)),
            ]
        )
    if not profiles:
        table = empty_state("No target records are present", "Populate targets.json after the research census stage.", "data/targets.json")
    else:
        table = render_table(
            "target-census",
            ["Target", "Stable ID", "Entity class", "Cell owner", "Surface evidence", "Priority", "Structure", "Claim"],
            rows,
            caption="Retained surface target records. Use a dossier link for the complete record.",
            filter_label="Search targets",
            sort_labels=[(0, "Name"), (2, "Entity class"), (4, "Surface evidence"), (5, "Priority"), (6, "Structure tier")],
        )
    body += section("Retained target records", table, kicker="Evidence index")
    body += section(
        "Census accounting",
        '<p>Discovery records, exclusions, and unresolved identities remain available in the data library. The target page reports only records retained in the surface target universe.</p>'
        + render_downloads([("Targets JSON", "data/targets.json", True), ("Targets CSV", "data/targets.csv", True)]),
        kicker="How to read this list",
    )
    return body


def render_record_source_block(record: dict[str, Any], *, title: str = "Sources") -> str:
    return section(title, render_source_list([record]), kicker="Evidence")


def record_artifacts(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Collect registered artifacts from a record and its validated lineage.

    Binder result records keep predicted complexes, PAE arrays, design poses,
    receipts, and parent backbones below nested observation and lineage fields.
    Recursing through JSON-safe containers keeps those files portable while the
    artifact signature prevents ordinary source or target records from being
    mistaken for files.
    """
    result: list[dict[str, Any]] = []
    seen: set[str] = set()

    def visit(value: Any) -> None:
        if isinstance(value, list):
            for item in value:
                visit(item)
            return
        if not isinstance(value, dict):
            return
        path = value.get("path")
        artifact_markers = ("sha256", "bytes", "artifact_id", "role", "media_type", "storage")
        if isinstance(path, str) and path.strip() and any(key in value for key in artifact_markers):
            normalized_path = path.strip()
            if normalized_path not in seen:
                seen.add(normalized_path)
                result.append(value)
        for nested in value.values():
            visit(nested)

    visit(record)
    return result


def render_artifact_list(record: dict[str, Any], artifact_map: dict[str, str]) -> str:
    artifacts = record_artifacts(record)
    if not artifacts:
        return '<p class="small">No local artifacts are recorded.</p>'
    items: list[str] = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        path = scalar_text(artifact.get("path"), empty="artifact")
        href = artifact_map.get(path)
        label = link_html(href, path, download=True) if href else f"<code>{esc(path)}</code>"
        hashes = []
        if nonempty(artifact.get("bytes")):
            hashes.append(f"{esc(artifact.get('bytes'))} bytes")
        if nonempty(artifact.get("sha256")):
            hashes.append(f"sha256 <code>{esc(artifact.get('sha256'))}</code>")
        items.append(f"<li>{label}{' · ' + ' · '.join(hashes) if hashes else ''}</li>")
    return '<ul class="link-list">' + "".join(items) + "</ul>" if items else '<p class="small">No local artifacts are recorded.</p>'


def render_related_table(
    records: list[dict[str, Any]],
    *,
    kind: str,
    target_id: str,
    target_name: str,
    target_links: dict[str, str] | None = None,
) -> str:
    matches = [record for record in records if related(record, target_id, target_name)]
    if not matches:
        return empty_state("No related records are present", "No records in this collection are linked to this target.")
    rows: list[list[tuple[str, Any]]] = []
    for index, record in enumerate(matches):
        preferred_keys = {
            "interventions": ("intervention_id",),
            "structures": ("structure_id",),
            "opportunities": ("opportunity_id",),
            "capabilities": ("capability_id",),
        }.get(kind, ())
        identifier = typed_record_id(record, index, kind.casefold().replace(" ", "-"), *preferred_keys)
        fallback = identifier
        if kind == "structures":
            fallback = scalar_text(pick(record, "pdb_id", "accession", "structure_id"), empty=identifier)
        name = record_name(record, fallback)
        href = target_links.get(identifier) if target_links else None
        name_html = link_html(href, name) if href else esc(name)
        action = pick(record, "action", "molecular_job", "mechanism", "role", "status")
        format_value = pick(record, "format", "molecular_format", "modality", "type", "kind")
        status = pick(record, "status", "development_status", "state")
        rows.append(
            [
                table_cell(name_html, name),
                table_cell(f'<span class="table-id">{esc(identifier)}</span>', identifier),
                table_cell(esc(scalar_text(action)), action),
                table_cell(esc(scalar_text(format_value)), format_value),
                table_cell(state_pill(status, "not recorded"), status),
                table_cell(claim_pill(record), claim_value(record)),
            ]
        )
    return render_table(
        f"related-{slugify(kind)}-{slugify(target_id)}",
        ["Name", "Stable ID", "Action", "Format", "Status", "Claim"],
        rows,
        caption=f"{kind.title()} records linked to {target_name}.",
        filter_label=f"Search {kind}",
        sort_labels=[(0, "Name"), (2, "Action"), (3, "Format"), (4, "Status")],
    )


def render_target_dossier(
    profile: dict[str, Any],
    collections: dict[str, list[dict[str, Any]]],
    artifact_map: dict[str, str],
    binders: list[dict[str, Any]] | None = None,
    binder_controls: list[dict[str, Any]] | None = None,
) -> str:
    record = profile["record"]
    pills = claim_pill(record)
    pills += f'<span class="tag">{esc(scalar_text(profile["tier"], empty="Evidence only"))}</span>'
    body = page_heading(
        "Target record",
        profile["name"],
        f"Target {profile['id']}. Review its evidence, known interactions, structures, and computed results.",
        pills=pills,
    )
    from .report_presentation import render_dossier_context
    body += render_dossier_context(sys.modules[__name__], record)
    body += section(
        "Identity and surface context",
        field_list_html(
            (
                ("Stable ID", profile["id"], True),
                ("Entity class", profile["entity_class"], False),
                ("Cell population", profile["cell_owner"], False),
                ("Topology", profile["topology"], False),
                ("Extracellular region", profile["extracellular_region"], False),
                ("Isoforms / sequence IDs", profile["isoforms"], True),
                ("Surface evidence", surface_evidence_summary(profile["surface"]), False),
                (profile.get("disease_evidence_label", "Disease context"), profile["disease_evidence"], False),
                (profile.get("risk_label", "Recorded warning assessment"), profile["normal_risk"], False),
                ("Priority", profile["priority"]["display"], False),
                ("Structure-review tier", profile["tier"], False),
            )
        ),
        kicker="Normalized record",
    )
    body += section("Interventions", render_related_table(collections.get("interventions.json", []), kind="interventions", target_id=profile["id"], target_name=profile["name"]), kicker="Treatments")
    body += section("Known molecule interactions", render_target_molecule_table(collections.get("molecular-library.json", []), profile["id"], profile["name"], known=True), kicker="Molecule library")
    body += section("Molecule lookup intentions", render_target_molecule_table(collections.get("molecular-library.json", []), profile["id"], profile["name"], known=False), kicker="Molecule library")
    body += section("Molecular screening results", render_target_screening_table(collections.get("screening-results.json", []), profile["id"], profile["name"], artifact_map), kicker="Computed hypotheses")
    body += render_target_binders(binders or [], binder_controls or [], profile["id"], profile["name"], artifact_map)
    body += section("Structures", render_related_table(collections.get("structures.json", []), kind="structures", target_id=profile["id"], target_name=profile["name"]), kicker="Structure library")
    body += section("Opportunities", render_related_table(collections.get("opportunities.json", []), kind="opportunities", target_id=profile["id"], target_name=profile["name"]), kicker="Design decisions")
    discovered = [record for record in collections.get("discovered-entities.json", []) if related(record, profile["id"], profile["name"])]
    if discovered:
        disposition = ", ".join(scalar_text(item.get("surface_disposition"), empty="not recorded") for item in discovered)
        discovery_body = field_list_html((("Linked discovery records", len(discovered), False), ("Surface dispositions", disposition, False)))
    else:
        discovery_body = empty_state("No linked discovery records are present", "The discovery ledger has no record linked to this target.")
    body += section("Discovery accounting", discovery_body, kicker="Provenance")
    body += section("Source references", render_source_list([record]), kicker="Evidence")
    body += section("Local artifacts", render_artifact_list(record, artifact_map), kicker="Downloads")
    if isinstance(profile["surface"], dict) or isinstance(record.get("evidence_score"), dict):
        evidence_detail = {
            "surface_evidence": profile["surface"],
            "evidence_score": record.get("evidence_score"),
        }
        body += section(
            "Structured surface evidence",
            f'<details class="details"><summary>Show complete evidence fields</summary><pre>{esc(pretty_json(evidence_detail))}</pre></details>',
            kicker="Evidence detail",
        )
    body += section("Complete target record", f'<details class="details"><summary>Show JSON record</summary><pre>{esc(pretty_json(record))}</pre></details>', kicker="Data")
    return body


def render_target_binders(records, controls, target_id, target_name, artifact_map):
    rows = []
    for role, candidates, anchor in (("Generated candidate", records, "designed-binders"), ("Control", controls, "binder-controls")):
        for index, record in enumerate(candidates):
            if not related(record, target_id, target_name):
                continue
            identifier = typed_record_id(record, index, "binder", "binder_id", "candidate_id", "control_id", "design_id")
            name = record_name(record, identifier)
            decision, decision_sort = binder_decision(record)
            control_class = pick(record, "class", "control_class", "type", default="") if role == "Control" else ""
            rows.append([
                table_cell(link_html(f"binders.html#{anchor}", name) + f'<span class="table-id">{esc(identifier)}</span>', name),
                table_cell(esc(role) + (f'<span class="cell-detail">{esc(scalar_text(control_class))}</span>' if control_class else ""), role),
                table_cell(binder_validation_summary(record), binder_metric(record, "ipsae_min_median")),
                table_cell(decision, decision_sort),
                table_cell(binder_artifact_links(record, artifact_map), len(record_artifacts(record))),
                table_cell(claim_pill(record), claim_value(record)),
            ])
    if not rows:
        return ""
    return section("Binder candidates and controls", render_table(
        f"target-{slugify(target_id)}-binders", ["Binder", "Role", "Computed evaluation", "Decision / execution", "Files", "Claim"], rows,
        caption=f"Generated candidates and control records linked to {target_name}. Computational evaluation does not establish binding.",
        filter_label="Search target binders", sort_labels=[(0, "Binder"), (1, "Role")]), kicker="Computed hypotheses")


def render_treatments(records: list[dict[str, Any]]) -> str:
    body = page_heading(
        "Treatments",
        "Treatment and ligand map",
        "Known ligands, drugs, biologics, cell therapies, imaging agents, and research interventions recorded for the atlas.",
        pills=state_pill(f"{len(records)} records", "not recorded"),
    )
    rows: list[list[tuple[str, Any]]] = []
    for index, record in enumerate(records):
        identifier = typed_record_id(record, index, "intervention", "intervention_id")
        name = record_name(record, identifier)
        targets = scalar_text(pick(record, "target_names", "target_ids", "targets", "target_id"), empty="Not recorded")
        rows.append(
            [
                table_cell(f'<span class="table-primary">{esc(name)}</span>', name),
                table_cell(f'<span class="table-id">{esc(identifier)}</span>', identifier),
                table_cell(esc(targets), targets),
                table_cell(esc(scalar_text(pick(record, "action", "mechanism", "role"))), pick(record, "action", "mechanism", "role")),
                table_cell(esc(scalar_text(pick(record, "format", "molecular_format", "modality", "type"))), pick(record, "format", "molecular_format", "modality", "type")),
                table_cell(state_pill(pick(record, "status", "development_status", "state"), "not recorded"), pick(record, "status", "development_status", "state")),
                table_cell(claim_pill(record), claim_value(record)),
            ]
        )
    table = render_table(
        "treatments",
        ["Intervention", "Stable ID", "Target(s)", "Action", "Format", "Status", "Claim"],
        rows,
        caption="Interventions remain separate from target evidence and design proposals.",
        filter_label="Search treatments",
        sort_labels=[(0, "Name"), (2, "Target"), (3, "Action"), (5, "Status")],
    ) if records else empty_state("No intervention records are present", "Populate interventions.json during treatment mapping.", "data/interventions.json")
    body += section("Recorded interventions", table, kicker="Treatment records")
    body += section("Treatment data", '<p>Directness, disease context, development state, dates, and source references remain in the JSON record.</p>' + render_downloads([("Interventions JSON", "data/interventions.json", True), ("Interventions CSV", "data/interventions.csv", True)]), kicker="Portable output")
    return body


def list_values(record: dict[str, Any], *keys: str) -> list[Any]:
    values: list[Any] = []
    for key in keys:
        value = record.get(key)
        if isinstance(value, list):
            values.extend(value)
        elif nonempty(value):
            values.append(value)
    return values


def molecule_category(record: dict[str, Any]) -> str:
    raw = pick(record, "category", "library_category", "panel", "source_class", "origin", "source_type", default="uncategorized")
    text = scalar_text(raw, empty="uncategorized").strip()
    lower = text.casefold().replace("_", "-").replace(" ", "-")
    if "natural" in lower:
        return "Natural product"
    if "reference" in lower or "positive-control" in lower:
        return "Reference ligand"
    if "user" in lower or "supplied" in lower or "uploaded" in lower:
        return "User-supplied"
    if "generat" in lower or "hypothesis" in lower or "designed" in lower:
        return "Generated"
    if "endogenous" in lower or "partner" in lower:
        return "Endogenous partner"
    if "approved" in lower or "drug" in lower:
        return "Approved or marketed"
    if "clinical" in lower:
        return "Clinical candidate"
    if "research" in lower:
        return "Research reagent"
    return text.replace("-", " ").replace("_", " ").strip().title() or "Uncategorized"


def molecule_format(record: dict[str, Any]) -> str:
    return scalar_text(pick(record, "molecular_format", "format", "molecule_format", "entity_class", "molecular_class", "type"))


def molecule_structure_string(record: dict[str, Any]) -> tuple[str, str]:
    fields = (
        ("Canonical SMILES", "canonical_smiles"),
        ("Isomeric SMILES", "isomeric_smiles"),
        ("Source SMILES", "source_smiles"),
        ("Connectivity SMILES", "connectivity_smiles"),
        ("SMILES", "smiles"),
        ("InChI", "inchi"),
        ("FASTA / sequence", "fasta"),
        ("Sequence", "sequence"),
    )
    for label, key in fields:
        value = record.get(key)
        if nonempty(value):
            return label, scalar_text(value, empty="")
    return "Structure string", "Not recorded"


def molecule_aliases(record: dict[str, Any]) -> str:
    return scalar_text(pick(record, "aliases", "synonyms", "alternate_names", "alias"))


def molecule_provenance(record: dict[str, Any]) -> str:
    parts: list[str] = []
    source_class = pick(record, "source_class", "source_type", "origin", "panel")
    if nonempty(source_class):
        parts.append(f"source: {scalar_text(source_class, empty='')}")
    for label, keys in (
        ("PubChem", ("pubchem_cid", "pubchem_id", "cid")),
        ("ChEBI", ("chebi_id", "chebi")),
        ("ChEMBL", ("chembl_id", "chembl")),
        ("BindingDB", ("bindingdb_id", "bindingdb")),
        ("UniProt", ("uniprot_id", "uniprot")),
        ("catalog", ("catalog_id", "supplier_id", "catalog_number")),
    ):
        value = pick(record, *keys, default="")
        if nonempty(value):
            parts.append(f"{label}: {scalar_text(value, empty='')}")
    aliases = molecule_aliases(record)
    if aliases != "Not recorded":
        parts.append(f"aliases: {aliases}")
    sources = source_links(record)
    if sources:
        parts.append("refs: " + ", ".join(label for label, _url in sources[:3]))
    return "; ".join(parts) or "Not recorded"


def molecule_flags(record: dict[str, Any], *keys: str) -> str:
    values = list_values(record, *keys)
    return scalar_text(values, empty="Not recorded")


def reference_texts(record: dict[str, Any], *keys: str) -> list[str]:
    texts: list[str] = []
    for value in list_values(record, *keys):
        if isinstance(value, dict):
            label, url = source_display(value)
            if url:
                texts.append(f"{label} ({url})")
            elif label:
                texts.append(label)
        else:
            text = scalar_text(value, empty="").strip()
            if text:
                texts.append(text)
    return texts


def molecule_known_refs(record: dict[str, Any]) -> list[str]:
    return reference_texts(
        record,
        "known_interaction_refs",
        "known_interactions",
        "interaction_refs",
        "measured_interactions",
        "binding_references",
        "known_binding_refs",
    )


def molecule_intentions(record: dict[str, Any]) -> list[str]:
    return reference_texts(
        record,
        "target_lookup_intentions",
        "intended_target_ids",
        "intended_targets",
        "target_lookup_intention",
    )


def molecule_targets(record: dict[str, Any], *, known: bool) -> list[str]:
    if known:
        keys = ("known_target_ids", "known_target_names", "known_targets", "known_target")
    else:
        keys = ("target_lookup_intentions", "intended_target_ids", "intended_targets", "target_lookup_intention")
    values: list[str] = []
    for value in list_values(record, *keys):
        if isinstance(value, dict):
            target_value = pick(value, "target_id", "target_name", "gene_symbol", "symbol", "name", "label", "id", default="")
            if nonempty(target_value):
                values.append(scalar_text(target_value, empty=""))
        else:
            text = scalar_text(value, empty="").strip()
            if text:
                values.append(text)
    return values


def molecule_artifact_links(record: dict[str, Any], artifact_map: dict[str, str]) -> str:
    artifacts = record_artifacts(record)
    links: list[str] = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        source_path = scalar_text(artifact.get("path"), empty="")
        href = artifact_map.get(source_path)
        if href:
            links.append(link_html(href, f"Download {Path(source_path).name}", download=True))
    return " · ".join(links)


def screening_value(record: dict[str, Any], *keys: str) -> Any:
    return pick(record, *keys, default="Not recorded")


def screening_repeatability(record: dict[str, Any]) -> Any:
    agreement = record.get("seed_agreement")
    if isinstance(agreement, dict):
        state = scalar_text(agreement.get("state"), empty="Not recorded")
        seed_count = exact_int(agreement.get("successful_comparable_seed_count"))
        span = agreement.get("top_score_span_kcal_mol")
        parts = [state.replace("-", " ")]
        if seed_count is not None:
            parts.append(f"{seed_count} comparable seed{'s' if seed_count != 1 else ''}")
        if isinstance(span, (int, float)):
            parts.append(f"{float(span):.3f} kcal/mol span")
        return " · ".join(parts)
    return screening_value(record, "confidence", "confidence_score", "complex_confidence", "plddt", "iptm")


def screening_pose_text(record: dict[str, Any], artifact_map: dict[str, str]) -> str:
    pose = pick(record, "pose_id", "pose", "pose_rank", "pose_name", default="")
    score = pick(record, "pose_score", "docking_score", "affinity_score", "score", default="")
    parts = []
    if nonempty(pose):
        parts.append(esc(scalar_text(pose, empty="")))
    if nonempty(score):
        scoring = scalar_text(pick(record, "scoring_function", "scoring", default="score"), empty="score")
        units = scalar_text(pick(record, "score_units", "units", default=""), empty="")
        scored = f"{scoring} {scalar_text(score, empty='')}"
        parts.append(esc(f"{scored} {units}".strip()))
    artifact = pick(record, "pose_artifact", "pose_path", "coordinate_artifact", default="")
    artifact_path = artifact.get("path") if isinstance(artifact, dict) else artifact
    if isinstance(artifact_path, str) and artifact_map.get(artifact_path):
        from .report_presentation import saved_pose_context
        description = saved_pose_context(record)
        download = link_html(artifact_map[artifact_path], "Download pose", download=True)
        if description:
            download += f'<span class="small">{esc(description)}</span>'
        parts.append(f'<div class="saved-pose">{download}</div>')
    elif nonempty(artifact):
        parts.append(esc(scalar_text(artifact, empty="")))
    return " · ".join(parts) or "Not recorded"


def screening_score_context(record: dict[str, Any]) -> str:
    scoring = scalar_text(
        pick(record, "scoring_function", "scoring", default=""), empty=""
    ).strip()
    units = scalar_text(pick(record, "score_units", "units", default=""), empty="").strip()
    if scoring and units:
        return f"{scoring} · {units}"
    if scoring:
        return f"Method: {scoring}"
    if units:
        return f"Units: {units}"
    return "Not recorded"


def screening_claim_pill() -> str:
    # Keep this fixed even if a malformed input record carries a stronger label.
    return '<span class="claim claim-proposed">computational-screening-hypothesis</span>'


def render_known_interaction_table(records: list[dict[str, Any]]) -> str:
    rows: list[list[tuple[str, Any]]] = []
    for index, record in enumerate(records):
        refs = molecule_known_refs(record)
        if not refs:
            continue
        identifier = typed_record_id(record, index, "molecule", "molecule_id")
        name = record_name(record, identifier)
        targets = molecule_targets(record, known=True)
        rows.append(
            [
                table_cell(f'<span class="table-primary">{esc(name)}</span>', name),
                table_cell(f'<span class="table-id">{esc(identifier)}</span>', identifier),
                table_cell(esc(", ".join(targets) or "Not assigned"), ", ".join(targets)),
                table_cell(esc("; ".join(refs)), "; ".join(refs)),
                table_cell(claim_pill({"claim_ceiling": "source-backed known interaction"}), "source-backed known interaction"),
            ]
        )
    if not rows:
        return empty_state("No known interaction references are recorded", "Known interaction references remain separate from target lookup intentions.")
    return render_table(
        "known-molecule-interactions",
        ["Molecule", "Stable ID", "Known target(s)", "Interaction reference(s)", "Claim"],
        rows,
        caption="Source-backed interaction references only. These rows are separate from prospective screening.",
        filter_label="Search known interactions",
        sort_labels=[(0, "Molecule"), (2, "Target"), (3, "Reference")],
    )


def render_lookup_intention_table(records: list[dict[str, Any]]) -> str:
    rows: list[list[tuple[str, Any]]] = []
    for index, record in enumerate(records):
        intentions = molecule_intentions(record)
        if not intentions:
            continue
        identifier = typed_record_id(record, index, "molecule", "molecule_id")
        name = record_name(record, identifier)
        rows.append(
            [
                table_cell(f'<span class="table-primary">{esc(name)}</span>', name),
                table_cell(f'<span class="table-id">{esc(identifier)}</span>', identifier),
                table_cell(esc(", ".join(intentions)), ", ".join(intentions)),
                table_cell(esc(molecule_category(record)), molecule_category(record)),
                table_cell('<span class="claim claim-proposed">lookup intention</span>', "lookup intention"),
            ]
        )
    if not rows:
        return empty_state("No target lookup intentions are recorded", "A library member can remain unassigned until a user selects a target or site.")
    return render_table(
        "molecule-target-intentions",
        ["Molecule", "Stable ID", "Intended target(s)", "Category", "Claim"],
        rows,
        caption="Lookup intentions are user or workflow inputs; they do not establish a target relationship.",
        filter_label="Search lookup intentions",
        sort_labels=[(0, "Molecule"), (2, "Intended target"), (3, "Category")],
    )


def render_screening_table(records: list[dict[str, Any]], artifact_map: dict[str, str], *, table_id: str = "screening-results") -> str:
    rows: list[list[tuple[str, Any]]] = []
    for index, record in enumerate(records):
        identifier = typed_record_id(
            record, index, "screening", "screening_result_id", "screening_id", "screen_id", "result_id"
        )
        run_id = pick(record, "run_id")
        role = screening_role(record)
        molecule = pick(record, "molecule_name", "molecule_id", "library_member_id", "compound_name")
        target = pick(record, "target_name", "target_id", "target")
        site = pick(record, "site_id", "site", "binding_site", "epitope", "pocket", "docking_scope")
        route = pick(record, "route", "workflow", "pipeline", "provider", "tool")
        model = pick(record, "model_version", "model", "predictor", "version")
        score_context = screening_score_context(record)
        repeatability = screening_repeatability(record)
        control_status = screening_value(record, "control_status", "controls_status", "control_state")
        failure = screening_value(record, "failure_reason", "failure", "error", "reason")
        state = pick(record, "execution_state", "state", "status", default="not recorded")
        preview = preview_controls(
            record,
            artifact_map,
            title=f"{scalar_text(molecule, empty='Screen result')} · {scalar_text(target, empty='Target')}",
            evidence=scalar_text(pick(record, "evidence_class", "claim_ceiling", "evidence_state"), empty="Computational screening hypothesis"),
            record_id=identifier,
        )
        rows.append(
            [
                table_cell(f'<span class="table-id">{esc(identifier)}</span>', identifier),
                table_cell(esc(scalar_text(run_id)), run_id),
                table_cell(esc(scalar_text(role)), role),
                table_cell(esc(scalar_text(molecule)), molecule),
                table_cell(esc(scalar_text(target)), target),
                table_cell(esc(scalar_text(site)), site),
                table_cell(esc(scalar_text(route)), route),
                table_cell(esc(scalar_text(model)), model),
                table_cell(esc(score_context), score_context),
                table_cell(screening_pose_text(record, artifact_map), pick(record, "pose_id", "pose_score", "docking_score", "pose_artifact")),
                table_cell(esc(scalar_text(repeatability)), repeatability),
                table_cell(esc(scalar_text(control_status)), control_status),
                table_cell(state_pill(state, "not recorded"), state),
                table_cell(esc(scalar_text(failure)), failure),
                table_cell(screening_claim_pill(), "computational-screening-hypothesis"),
                table_cell(preview or '<span class="small">No structure preview</span>', bool(preview)),
            ]
        )
    if not rows:
        return empty_state("No screening results are recorded", "A screen result requires a declared target construct, molecule input, route, and execution record.")
    return render_table(
        table_id,
        [
            "Screen ID",
            "Run ID",
            "Role",
            "Molecule",
            "Target",
            "Site / scope",
            "Route",
            "Model",
            "Score method / units",
            "Pose / score",
            "Repeatability / confidence",
            "Control status",
            "Execution",
            "Failure",
            "Claim",
            "Structure preview",
        ],
        rows,
        caption="Every returned pose remains a computational screening hypothesis. It is not a known interaction record.",
        filter_label="Search screen results",
        sort_labels=[
            (0, "Screen ID"),
            (1, "Run ID"),
            (2, "Role"),
            (3, "Molecule"),
            (4, "Target"),
            (5, "Site"),
            (6, "Route"),
            (10, "Confidence"),
            (12, "Execution"),
        ],
    )


def render_molecule_library(
    records: list[dict[str, Any]],
    screening_records: list[dict[str, Any]],
    artifact_map: dict[str, str],
    *,
    registration_receipt_path: str | None = None,
    registration_original_path: str | None = None,
) -> str:
    category_counts: dict[str, int] = {}
    for record in records:
        category = molecule_category(record)
        category_counts[category] = category_counts.get(category, 0) + 1
    category_text = ", ".join(f"{key}: {value}" for key, value in sorted(category_counts.items())) or "No categories recorded"
    body = page_heading(
        "Molecule library",
        "Molecule library",
        "Natural products, reference ligands, user-supplied members, and generated inputs with identity and preparation records.",
        pills=state_pill(f"{len(records)} library members", "not recorded") + state_pill(f"{len(screening_records)} prospective screens", "not recorded"),
    )
    body += section(
        "Known interactions and proposed screens",
        '<div class="panel panel-white"><p>Review cited interactions in the known-interactions table. Lookup requests identify targets to investigate. Computational screen records contain predicted poses, model settings, controls, scores, and failures.</p></div>',
        kicker="Reading guide",
    )
    body += section(
        "Library composition",
        field_list_html((("Library members", len(records), False), ("Categories", category_text, False), ("Prospective screens", len(screening_records), False))),
        kicker="Inventory",
    )
    rows: list[list[tuple[str, Any]]] = []
    for index, record in enumerate(records):
        identifier = typed_record_id(record, index, "molecule", "molecule_id")
        name = record_name(record, identifier)
        string_label, string_value = molecule_structure_string(record)
        preview = string_value if len(string_value) <= 72 else string_value[:69] + "…"
        known_count = len(molecule_known_refs(record))
        intention_count = len(molecule_intentions(record))
        identity = pick(record, "identity_state", "validation_state", "evidence_class", default="not recorded")
        downloads = molecule_artifact_links(record, artifact_map) or "Not recorded"
        rows.append(
            [
                table_cell(f'<span class="table-primary">{esc(name)}</span>', name),
                table_cell(f'<span class="table-id">{esc(identifier)}</span>', identifier),
                table_cell(esc(molecule_category(record)), molecule_category(record)),
                table_cell(esc(molecule_format(record)), molecule_format(record)),
                table_cell(state_pill(identity, "not recorded"), identity),
                table_cell(esc(molecule_provenance(record)), molecule_provenance(record)),
                table_cell(f'<span class="mono" title="{esc(string_label)}">{esc(preview)}</span>', string_value),
                table_cell(esc(molecule_flags(record, "chemistry_flags", "chemistry_review_flags")), molecule_flags(record, "chemistry_flags", "chemistry_review_flags")),
                table_cell(esc(molecule_flags(record, "preparation_flags", "preparation_state", "preparation_status")), molecule_flags(record, "preparation_flags", "preparation_state", "preparation_status")),
                table_cell(downloads if downloads != "Not recorded" else esc(downloads), downloads),
                table_cell(str(known_count), known_count),
                table_cell(str(intention_count), intention_count),
            ]
        )
    library_table = render_table(
        "molecule-library",
        ["Molecule", "Stable ID", "Category", "Format / class", "Identity", "Identity / provenance", "Structure string preview", "Chemistry flags", "Preparation", "Structure downloads", "Known refs", "Lookup intents"],
        rows,
        caption="Library members are shown before any target assignment. Structure strings are previews; complete records are in JSON.",
        filter_label="Search molecule library",
        sort_labels=[(0, "Molecule"), (2, "Category"), (3, "Format"), (4, "Identity"), (8, "Known references"), (9, "Lookup intentions")],
    ) if records else empty_state("No molecule library records are present", "Populate molecular-library.json with normalized inputs before interaction lookup or prospective screening.", "data/molecular-library.json")
    body += section("Library members", library_table, kicker="Identity and preparation")
    body += section("Known interaction references", render_known_interaction_table(records), kicker="Source-backed relationships")
    body += section("Target lookup intentions", render_lookup_intention_table(records), kicker="Requested relationships")
    body += section("Prospective screen results", render_screening_table(screening_records, artifact_map), kicker="Computed hypotheses")
    download_files: list[tuple[str, str, bool]] = [
        ("Molecule library JSON", "data/molecular-library.json", True),
        ("Molecule library CSV", "data/molecular-library.csv", True),
        ("Screening results JSON", "data/screening-results.json", True),
        ("Screening results CSV", "data/screening-results.csv", True),
    ]
    if registration_receipt_path:
        receipt_href = artifact_map.get(registration_receipt_path)
        if receipt_href:
            download_files.append(("Registration receipt", receipt_href, True))
    if registration_original_path:
        original_href = artifact_map.get(registration_original_path)
        if original_href:
            download_files.append(("Original imported library", original_href, True))
    body += section(
        "Portable molecule data",
        '<p>Identity fields, aliases, identifiers, structure strings, preparation flags, source references, and local artifacts are included in the exports.</p>'
        + render_downloads(download_files),
        kicker="Downloads",
    )
    return body


def molecule_target_match(record: dict[str, Any], target_id: str, target_name: str, *, known: bool) -> bool:
    values = molecule_targets(record, known=known)
    candidates = {normalized(target_id), normalized(target_name)}
    return any(normalized(value) in candidates for value in values)


def render_target_molecule_table(records: list[dict[str, Any]], target_id: str, target_name: str, *, known: bool) -> str:
    rows: list[list[tuple[str, Any]]] = []
    for index, record in enumerate(records):
        if not molecule_target_match(record, target_id, target_name, known=known):
            continue
        identifier = typed_record_id(record, index, "molecule", "molecule_id")
        name = record_name(record, identifier)
        if known:
            refs = molecule_known_refs(record)
            relation = "; ".join(refs) or "Known target ID recorded; interaction reference not recorded"
            claim = claim_pill({"claim_ceiling": "source-backed known interaction"})
            relation_sort = "known interaction"
        else:
            relation = "; ".join(molecule_intentions(record))
            claim = '<span class="claim claim-proposed">lookup intention</span>'
            relation_sort = "lookup intention"
        rows.append(
            [
                table_cell(f'<span class="table-primary">{esc(name)}</span>', name),
                table_cell(f'<span class="table-id">{esc(identifier)}</span>', identifier),
                table_cell(esc(molecule_category(record)), molecule_category(record)),
                table_cell(esc(relation), relation),
                table_cell(claim, relation_sort),
            ]
        )
    if not rows:
        if known:
            return empty_state("No known molecule interactions are linked", "This target has no molecule record with a source-backed known target relationship.")
        return empty_state("No molecule lookup intentions are linked", "This target has no molecule record with an intended lookup relationship.")
    section_name = "known molecule interactions" if known else "molecule lookup intentions"
    return render_table(
        f"target-{slugify(target_id)}-molecules-{'known' if known else 'intentions'}",
        ["Molecule", "Stable ID", "Category", "Reference or intention", "Claim"],
        rows,
        caption=f"{section_name.title()} linked to {target_name}.",
        filter_label=f"Search {section_name}",
        sort_labels=[(0, "Molecule"), (2, "Category"), (3, "Reference or intention")],
    )


def render_target_screening_table(records: list[dict[str, Any]], target_id: str, target_name: str, artifact_map: dict[str, str]) -> str:
    matches = [record for record in records if related(record, target_id, target_name)]
    return render_screening_table(matches, artifact_map, table_id=f"target-{slugify(target_id)}-screening")


def structure_image_artifact(record: dict[str, Any], artifact_map: dict[str, str]) -> tuple[str | None, str | None]:
    artifacts = record_artifacts(record)
    image_suffixes = {".png", ".jpg", ".jpeg", ".webp", ".svg"}
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        path = scalar_text(artifact.get("path"), empty="")
        href = artifact_map.get(path)
        if href and Path(path).suffix.casefold() in image_suffixes:
            return href, path
    return None, None


def structure_video_artifact(record: dict[str, Any], artifact_map: dict[str, str]) -> tuple[str | None, str | None]:
    for artifact in record_artifacts(record):
        path = scalar_text(artifact.get("path"), empty="")
        href = artifact_map.get(path)
        media_type = scalar_text(artifact.get("media_type"), empty="").casefold()
        if href and (Path(path).suffix.casefold() == ".mp4" or media_type == "video/mp4"):
            return href, path
    return None, None


def structure_bound_partner(record: dict[str, Any]) -> Any:
    direct = pick(record, "bound_partner", "ligand", "partner", "complex_partner", default="")
    if nonempty(direct):
        return direct
    if "apo" in normalized(record.get("interaction_class")):
        return "No bound partner (apo structure)"
    partners: list[str] = []
    for key in ("chains", "polymer_entities"):
        values = record.get(key)
        if not isinstance(values, list):
            continue
        for value in values:
            if not isinstance(value, dict):
                continue
            role = normalized(value.get("role"))
            if role in {"target", "receptor"}:
                continue
            label = scalar_text(pick(value, "label", "manifest_label", "rcsb_description", "name", default=""), empty="").strip()
            if label and label not in partners:
                partners.append(label)
    if partners:
        return ", ".join(partners)
    nonpolymers = record.get("nonpolymer_entities")
    if isinstance(nonpolymers, list):
        for value in nonpolymers:
            if not isinstance(value, dict) or normalized(value.get("role")) in {"glycan", "structuralcofactor"}:
                continue
            label = scalar_text(pick(value, "name", "comp_id", default=""), empty="").strip()
            if label and label not in partners:
                partners.append(label)
    return ", ".join(partners) if partners else "Not recorded"


def structure_resolution(record: dict[str, Any]) -> str:
    value = pick(record, "resolution", "resolution_angstrom", "resolution_a", default="")
    if not nonempty(value):
        entry = record.get("entry")
        if isinstance(entry, dict):
            value = pick(entry, "resolution_angstrom", "resolution", "resolution_a", default="")
    if isinstance(value, list):
        value = value[0] if value else ""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value:g} Å"
    text = scalar_text(value)
    return f"{text} Å" if text != "Not recorded" and "å" not in text.casefold() else text


def structure_title(record: dict[str, Any], identifier: str) -> str:
    direct = record_name(record, identifier)
    if direct != identifier:
        return direct
    entry = record.get("entry")
    if isinstance(entry, dict):
        nested = scalar_text(entry.get("title"), empty="").strip()
        if nested:
            return nested
    return identifier


def structure_target_label(record: dict[str, Any]) -> Any:
    return pick(
        record,
        "primary_target_symbol",
        "target_symbols",
        "target_names",
        "target_name",
        "target_id",
        "target",
    )


def structure_coord_links(record: dict[str, Any], artifact_map: dict[str, str]) -> list[str]:
    links: list[str] = []
    artifacts = record_artifacts(record)
    coordinate_suffixes = {".pdb", ".cif", ".mmcif", ".sdf", ".mol2", ".fasta", ".fa"}
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        path = scalar_text(artifact.get("path"), empty="")
        href = artifact_map.get(path)
        if href and Path(path).suffix.casefold() in coordinate_suffixes:
            links.append(link_html(href, f"Download {path}", download=True))
        elif href and Path(path).suffix.casefold() == ".mp4":
            links.append(link_html(href, f"Download {path}", download=True))
    return links


def render_structures(records: list[dict[str, Any]], artifact_map: dict[str, str]) -> str:
    body = page_heading(
        "Structures",
        "Structure library",
        "Inspect experimental structures and predicted models, their binding partners, and missing coordinates.",
        pills=state_pill(f"{len(records)} records", "not recorded"),
    )
    if not records:
        body += section("Structure records", empty_state("No structure records are present", "Select targets for structure review after completing the census.", "data/structures.json"), kicker="Library")
        return body
    cards: list[str] = []
    for index, record in enumerate(records):
        identifier = typed_record_id(record, index, "structure", "structure_id")
        title = structure_title(record, identifier)
        card_id = f"structure-{slugify(identifier)}"
        caption_id = f"{card_id}-caption"
        image_href, image_path = structure_image_artifact(record, artifact_map)
        video_href, video_path = structure_video_artifact(record, artifact_map)
        if image_href:
            visual = (
                f'<img src="{esc(image_href)}" alt="White-background structure render for {esc(title)}" '
                f'width="1200" height="900" loading="lazy" decoding="async" aria-describedby="{esc(caption_id)}">'
            )
        else:
            visual = f'<div class="structure-placeholder"><span class="placeholder-mark">3D</span><strong>{esc(scalar_text(pick(record, "pdb_id", "accession", "structure_id"), empty="Structure") )}</strong><span>No rendered image is recorded.</span></div>'
        video = ""
        if video_href:
            poster = f' poster="{esc(image_href)}"' if image_href else ""
            video = (
                f'<div class="structure-video"><video controls preload="metadata" playsinline '
                f'aria-label="Structure rotation for {esc(title)}" aria-describedby="{esc(caption_id)}"{poster}>'
                f'<source src="{esc(video_href)}" type="video/mp4">'
                f'{link_html(video_href, "Download the structure movie")}</video></div>'
            )
        evidence = claim_pill(record, "Structure state not classified")
        target = structure_target_label(record)
        partner = structure_bound_partner(record)
        kind = pick(record, "structure_type", "kind", "state", "evidence_class")
        resolution = structure_resolution(record)
        coord_links = structure_coord_links(record, artifact_map)
        if image_path:
            coord_links.insert(0, f'<span class="small">Render: <code>{esc(image_path)}</code></span>')
        if video_path:
            coord_links.insert(1 if image_path else 0, f'<span class="small">Movie: <code>{esc(video_path)}</code></span>')
        downloads = "<div class=\"download-row\">" + " · ".join(coord_links) + "</div>" if coord_links else '<p class="small">No portable coordinate or render artifact is available.</p>'
        preview = preview_controls(
            record,
            artifact_map,
            title=title,
            evidence=scalar_text(pick(record, "evidence_class", "claim_ceiling", "evidence_state"), empty="Structure evidence not classified"),
            record_id=identifier,
        )
        if preview:
            downloads += f'<div class="structure-preview-row">{preview}</div>'
        cards.append(
            f'<figure id="{esc(card_id)}" class="structure-card"><div class="structure-visual">{visual}</div>{video}'
            f'<figcaption id="{esc(caption_id)}" class="structure-caption">'
            f'<h3>{esc(title)}</h3><div class="label-row">{evidence}<span class="tag">{esc(scalar_text(kind, empty="Structure record"))}</span></div>'
            f'<dl class="structure-meta"><dt>ID</dt><dd class="mono">{esc(identifier)}</dd><dt>Target</dt><dd>{esc(scalar_text(target))}</dd>'
            f'<dt>Bound partner</dt><dd>{esc(scalar_text(partner))}</dd><dt>Resolution</dt><dd>{esc(scalar_text(resolution))}</dd></dl>{downloads}</figcaption></figure>'
        )
    body += section("Structure records", '<div class="structure-grid">' + "".join(cards) + "</div>", kicker="Gallery")
    body += section("Structure data", '<p>Each record preserves construct, assembly, numbering, site, evidence class, and gaps when those fields are available.</p>' + render_downloads([("Structures JSON", "data/structures.json", True), ("Structures CSV", "data/structures.csv", True)]), kicker="Portable output")
    return body


def binder_metric(record: dict[str, Any], key: str) -> Any:
    aggregate = record.get("aggregate_metrics")
    if isinstance(aggregate, dict) and nonempty(aggregate.get(key)):
        return aggregate[key]
    return record.get(key)


def binder_metric_text(value: Any, *, digits: int = 3) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return scalar_text(value)
    return f"{float(value):.{digits}f}".rstrip("0").rstrip(".")


def binder_validation_summary(record: dict[str, Any]) -> str:
    aggregate = record.get("aggregate_metrics")
    aggregate = aggregate if isinstance(aggregate, dict) else {}
    observations = record.get("cofold_observations")
    observations = observations if isinstance(observations, list) else []
    scored = aggregate.get("scored_observation_count")
    failed = aggregate.get("failed_observation_count")
    if not isinstance(scored, int):
        scored = sum(item.get("status") == "scored" for item in observations if isinstance(item, dict))
    if not isinstance(failed, int):
        failed = sum(item.get("status") == "failed" for item in observations if isinstance(item, dict))
    ipsae = binder_metric(record, "ipsae_min_median")
    recall = binder_metric(record, "target_contact_recall_median")
    return '<div class="binder-evaluation">' + field_list_html(
        (
            ("iPSAE minimum, median", binder_metric_text(ipsae)),
            ("Target-contact recall, median", binder_metric_text(recall)),
            ("Scored observations", scored),
            ("Failed observations", failed),
        )
    ) + "</div>"


def binder_sequence_html(record: dict[str, Any]) -> str:
    sequence = scalar_text(pick(record, "sequence", "protein_sequence", "binder_sequence", "seq"), empty="")
    if not sequence:
        return '<span class="small">Not recorded</span>'
    return (
        f'<details class="sequence-details"><summary>{len(sequence)} aa sequence</summary>'
        f'<code class="sequence" translate="no">{esc(sequence)}</code></details>'
    )


def binder_artifact_links(record: dict[str, Any], artifact_map: dict[str, str]) -> str:
    links: list[str] = []
    for artifact in record_artifacts(record):
        path = scalar_text(artifact.get("path"), empty="")
        href = artifact_map.get(path)
        if not href:
            continue
        role = scalar_text(artifact.get("role"), empty="artifact").replace("-", " ")
        links.append(f'<li>{link_html(href, Path(path).name, download=True)}<span class="artifact-role">{esc(role)}</span></li>')
    if not links:
        rendered = '<span class="small">No portable artifact</span>'
    else:
        rendered = (
        f'<details class="artifact-details"><summary>{len(links)} verified file'
        f'{"s" if len(links) != 1 else ""}</summary><ul class="artifact-links">'
        + "".join(links)
        + "</ul></details>"
        )
    identifier = typed_record_id(record, 0, "binder", "binder_id", "candidate_id", "design_id")
    preview = preview_controls(
        record,
        artifact_map,
        title=record_name(record, identifier),
        evidence=scalar_text(pick(record, "evidence_class", "claim_ceiling", "evidence_state"), empty="Binder evidence not classified"),
        record_id=identifier,
    )
    return rendered + (f'<div class="structure-preview-row">{preview}</div>' if preview else "")


def binder_decision(record: dict[str, Any]) -> tuple[str, str]:
    promotion = record.get("promotion")
    if isinstance(promotion, dict) and nonempty(promotion.get("decision")):
        value = scalar_text(promotion["decision"])
        rationale = scalar_text(pick(promotion, "rationale", "reason", "basis", default=""), empty="")
        detail = f'<span class="small decision-detail">{esc(rationale)}</span>' if rationale else ""
        return state_pill(value, "not recorded") + detail, value
    value = scalar_text(pick(record, "ranking_status", "status", "state", "execution_state"), empty="not recorded")
    return state_pill(value, "not recorded"), value


def render_binder_campaigns(records: list[dict[str, Any]]) -> str:
    if not records:
        return empty_state(
            "No campaign summary is recorded",
            "Candidate records may still be inspected individually.",
            "data/binders.json",
        )
    blocks: list[str] = []
    for record in records:
        counts = record.get("counts") if isinstance(record.get("counts"), dict) else {}
        blocks.append(
            '<div class="panel panel-white">'
            + field_list_html(
                (
                    ("Campaign", record.get("campaign_id"), True),
                    ("Request", record.get("request_id"), True),
                    ("Target", record.get("target_id"), True),
                    ("Execution", record.get("execution_state")),
                    ("Control calibration", record.get("control_calibration_status")),
                    ("Validated backbones", counts.get("validated_backbones")),
                    ("Designed candidates", counts.get("designed_candidates")),
                    ("Cofold observations", counts.get("cofold_observations")),
                )
            )
            + "</div>"
        )
    return '<div class="grid-2">' + "".join(blocks) + "</div>"


def render_binders(
    records: list[dict[str, Any]],
    controls: list[dict[str, Any]],
    campaigns: list[dict[str, Any]],
    artifact_map: dict[str, str],
) -> str:
    promoted = sum(
        normalized(record.get("ranking_status")) == "promoted-by-recorded-decision"
        or normalized(record.get("promotion", {}).get("decision") if isinstance(record.get("promotion"), dict) else "") == "promoted"
        for record in records
    )
    scored_observations = sum(
        sum(item.get("status") == "scored" for item in record.get("cofold_observations", []) if isinstance(item, dict))
        for record in records
        if isinstance(record.get("cofold_observations"), list)
    )
    body = page_heading(
        "Designed binders",
        "Designed binder library",
        "Compare candidate sequences and predicted complexes with target-matched controls. Trace each candidate to its backbone and evaluation records.",
        pills=state_pill(f"{len(records)} candidates", "not recorded")
        + state_pill(f"{len(controls)} controls", "not recorded")
        + claim_pill({"claim_ceiling": "computational-design-hypothesis"}),
    )
    body += render_metrics(
        [
            ("Generated candidates", len(records)),
            ("Promoted by recorded decision", promoted),
            ("Control records", len(controls)),
            ("Scored cofold observations", scored_observations),
        ]
    )
    body += section("Campaign status", render_binder_campaigns(campaigns), kicker="Execution and controls")
    if not records:
        body += section("Design results", empty_state("No designed binder records are present", "Binder requests and opportunities remain visible on Design & sources until a design result is recorded.", "design-sources.html"), kicker="Design output")
    else:
        rows: list[list[tuple[str, Any]]] = []
        for index, record in enumerate(records):
            identifier = typed_record_id(record, index, "binder", "binder_id", "candidate_id", "design_id")
            name = record_name(record, identifier)
            target = pick(record, "target_name", "target_id", "target")
            job = pick(record, "molecular_job", "job", "action", "role")
            decision, decision_sort = binder_decision(record)
            rows.append(
                [
                    table_cell(
                        f'<span class="table-primary">{esc(name)}</span><span class="table-id">{esc(identifier)}</span>',
                        name,
                    ),
                    table_cell(
                        f'<strong>{esc(scalar_text(target))}</strong><span class="cell-detail">{esc(scalar_text(job))}</span>',
                        target,
                    ),
                    table_cell(binder_sequence_html(record), pick(record, "sequence_length", default="")),
                    table_cell(binder_validation_summary(record), binder_metric(record, "ipsae_min_median")),
                    table_cell(decision, decision_sort),
                    table_cell(binder_artifact_links(record, artifact_map), len(record_artifacts(record))),
                    table_cell(claim_pill(record), claim_value(record)),
                ]
            )
        table = render_table(
            "designed-binders",
            ["Candidate", "Target and job", "Sequence", "Independent validation", "Decision", "Files", "Claim"],
            rows,
            caption="Generated candidates with recorded cofold metrics, promotion decisions, and hash-verified files.",
            filter_label="Search binder candidates",
            sort_labels=[(0, "Candidate"), (1, "Target"), (2, "Sequence length"), (3, "Median iPSAE"), (4, "Decision")],
        )
        body += section("Candidate records", table, kicker="Computational design output")

    control_rows: list[list[tuple[str, Any]]] = []
    for index, record in enumerate(controls):
        identifier = typed_record_id(record, index, "control", "candidate_id", "control_id")
        label = record_name(record, identifier)
        control_class = pick(record, "class", "control_class", "type")
        target = pick(record, "target_name", "target_id", "target")
        control_rows.append(
            [
                table_cell(f'<span class="table-primary">{esc(label)}</span><span class="table-id">{esc(identifier)}</span>', label),
                table_cell(esc(scalar_text(control_class)), control_class),
                table_cell(esc(scalar_text(target)), target),
                table_cell(binder_sequence_html(record), pick(record, "sequence_length", default="")),
                table_cell(binder_validation_summary(record), binder_metric(record, "ipsae_min_median")),
                table_cell(binder_artifact_links(record, artifact_map), len(record_artifacts(record))),
                table_cell(claim_pill(record), claim_value(record)),
            ]
        )
    controls_table = (
        render_table(
            "binder-controls",
            ["Control", "Class", "Target", "Sequence", "Independent validation", "Files", "Claim"],
            control_rows,
            caption="Target-matched positive and negative controls remain visible beside generated candidates.",
            filter_label="Search binder controls",
            sort_labels=[(0, "Control"), (1, "Class"), (2, "Target"), (4, "Median iPSAE")],
        )
        if controls
        else empty_state("No binder control records are present", "Run records should preserve the target-matched controls used for interpretation.")
    )
    body += section("Control records", controls_table, kicker="Calibration")
    body += section(
        "Design data",
        '<p>Download the recorded sequences, validation results, model details, and artifact hashes.</p>'
        + render_downloads(
            [
                ("Binders JSON", "data/binders.json", True),
                ("Binders CSV", "data/binders.csv", True),
                ("Binder controls JSON", "data/binder-controls.json", True),
                ("Binder campaigns JSON", "data/binder-campaigns.json", True),
            ]
        ),
        kicker="Portable output",
    )
    return body


def render_opportunities(records: list[dict[str, Any]]) -> str:
    if not records:
        return empty_state("No opportunity records are present", "Target × molecular-job decisions have not been recorded.", "data/opportunities.json")
    blocks: list[str] = []
    for index, record in enumerate(records):
        identifier = typed_record_id(record, index, "opportunity", "opportunity_id")
        target = pick(record, "target_name", "target_id", "target")
        job = pick(record, "molecular_job", "job", "action", "role")
        modality = pick(record, "selected_format", "modality", "molecular_format", "format")
        site = pick(record, "site", "binding_site", "epitope", "pocket")
        site_data = site if isinstance(site, dict) else {}
        site_label = pick(site_data, "site_id", "name", "label", "mode") if site_data else site
        site_label = site_label or record.get("site_id")
        rationale = pick(record, "rationale", "reason", "basis")
        risk = pick(record, "principal_risks", "leading_risk", "risk", "normal_tissue_risk")
        next_step = pick(record, "next_step", "next_action", "recommendation")
        risks = risk if isinstance(risk, list) else [risk]
        risk_html = "".join(f'<li>{esc(scalar_text(item))}</li>' for item in risks)
        fields = [("Format", modality), ("Site", site_label), ("Desired effect", record.get("desired_effect"))]
        if isinstance(record.get("result_ingestion"), dict):
            fields.append(("Result ingestion", record["result_ingestion"].get("state")))
        details = ""
        if site_data:
            details = (
                '<details class="evidence-disclosure"><summary>Site evidence and residue mapping</summary>'
                + field_list_html([(label, site_data.get(key)) for label, key in (
                    ("Site mode", "mode"), ("Evidence class", "evidence_class"),
                    ("Evidence", "evidence"), ("Numbering", "numbering_scheme"),
                    ("Excluded regions", "excluded_regions"), ("Uncertain regions", "uncertain_regions"),
                )])
                + f'<pre>{esc(json.dumps(site_data, indent=2, ensure_ascii=False))}</pre></details>'
            )
        blocks.append(
            f'<article class="opportunity"><div class="opportunity-title">{esc(scalar_text(target, empty="Target not recorded"))} · {esc(scalar_text(job, empty="Job not recorded"))}</div>'
            f'<div class="opportunity-meta mono">{esc(identifier)}</div>'
            f'<p>{esc(scalar_text(rationale))}</p>{field_list_html(fields)}'
            f'<p><strong>Recorded risks</strong></p><ul>{risk_html}</ul>'
            f'<p><strong>Next step:</strong> {esc(scalar_text(next_step))}</p>'
            f'<div class="label-row">{claim_pill(record)}</div>{details}</article>'
        )
    return "".join(blocks)


def render_capabilities(records: list[dict[str, Any]]) -> str:
    rows: list[list[tuple[str, Any]]] = []
    for index, record in enumerate(records):
        identifier = typed_record_id(record, index, "capability", "capability_id")
        name = record_name(record, identifier)
        rows.append(
            [
                table_cell(esc(name), name),
                table_cell(f'<span class="table-id">{esc(identifier)}</span>', identifier),
                table_cell(state_pill(record.get("state"), "not recorded"), record.get("state")),
                table_cell(esc(scalar_text(pick(record, "version", "tool_version", "model_version"))), pick(record, "version", "tool_version", "model_version")),
                table_cell(esc(scalar_text(pick(record, "route", "endpoint", "provider"))), pick(record, "route", "endpoint", "provider")),
                table_cell(claim_pill(record), claim_value(record)),
            ]
        )
    if not rows:
        return empty_state("No capability records are present", "Provider, viewer, and model states have not been recorded.", "data/capabilities.json")
    return render_table("capabilities", ["Capability", "Stable ID", "State", "Version", "Route", "Claim"], rows, caption="Capability states are recorded separately from scientific evidence.", filter_label="Search capabilities", sort_labels=[(0, "Capability"), (2, "State"), (3, "Version")])


def discover_handoff_files(root: Path) -> list[Path]:
    handoffs = root / "handoffs"
    if not handoffs.is_dir():
        return []
    return sorted(path for path in handoffs.rglob("*.json") if safe_workspace_file(root, path))


def safe_workspace_file(root: Path, path: Path) -> bool:
    """Return whether path is a regular, non-symlinked file below root."""
    root = root.resolve()
    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return False
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError):
        return False
    return resolved.is_file()


def copy_handoff_files(root: Path, run_dir: Path, handoffs: list[Path]) -> dict[str, str]:
    handoff_map: dict[str, str] = {}
    for source in handoffs:
        if not safe_workspace_file(root, source):
            continue
        try:
            relative = source.relative_to(root)
        except ValueError:
            continue
        pure = safe_relative(relative.as_posix())
        if pure is None:
            continue
        destination_relative = Path("data") / "handoffs" / Path(*pure.parts)
        destination = run_dir / destination_relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        handoff_map[relative.as_posix()] = destination_relative.as_posix()
    return handoff_map


def render_handoffs(handoffs: list[tuple[str, dict[str, Any]]], handoff_map: dict[str, str] | None = None) -> str:
    if not handoffs:
        return empty_state("No handoff records are present", "No binder or external-work request files were found in the atlas workspace.")
    items: list[str] = []
    for label, payload in handoffs:
        identifier = record_id(payload, 0, "handoff")
        href = (handoff_map or {}).get(label)
        label_html = link_html(href, label, download=True) if href else f"<strong>{esc(label)}</strong>"
        items.append(f'<li>{label_html} · <code>{esc(identifier)}</code> · {claim_pill(payload)}</li>')
    return '<ul class="link-list">' + "".join(items) + "</ul>"


def render_design_sources(
    plan: dict[str, Any],
    ledger: dict[str, Any],
    opportunities: list[dict[str, Any]],
    capabilities: list[dict[str, Any]],
    handoffs: list[tuple[str, dict[str, Any]]],
    handoff_map: dict[str, str] | None = None,
) -> str:
    body = page_heading(
        "Design & sources",
        "Design decisions and provenance",
        "Review selected targets and sites, tool readiness, submitted requests, and source coverage.",
        pills=state_pill(execution_label(plan), "not recorded") + state_pill(coverage_label(ledger), "not recorded"),
    )
    body += section("Targets, sites, and intended actions", render_opportunities(opportunities), kicker="Design decisions")
    body += section("Capability states", render_capabilities(capabilities), kicker="Execution")
    body += section("Binder and external-work handoffs", render_handoffs(handoffs, handoff_map), kicker="Requests")
    body += section("Source registry", render_coverage(ledger), kicker="Evidence retrieval")
    body += section(
        "Portable provenance",
        '<p>Download source identifiers, search records, file hashes, model versions, and artifact paths. Each record retains its planned or executed status.</p>'
        + render_downloads([("Full atlas JSON", "data/atlas.json", True), ("Search ledger JSON", "data/search-ledger.json", True), ("Opportunities JSON", "data/opportunities.json", True)]),
        kicker="Reading guide",
    )
    return body


def flatten_record(record: dict[str, Any], identifier: str, name: str, *, extra: dict[str, Any] | None = None) -> dict[str, str]:
    row = {
        "id": identifier,
        "name": name,
        "target": scalar_text(pick(record, "target_name", "target_id", "target"), empty=""),
        "action": scalar_text(pick(record, "action", "molecular_job", "job", "mechanism"), empty=""),
        "format": scalar_text(pick(record, "format", "molecular_format", "modality", "type"), empty=""),
        "status": scalar_text(pick(record, "status", "state", "development_status", "execution_state"), empty=""),
        "claim": claim_value(record, ""),
        "raw_json": compact_json(record),
    }
    if extra:
        row.update({key: scalar_text(value, empty="") for key, value in extra.items()})
    return row


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = ["id", "name", "target", "action", "format", "status", "claim", "raw_json"]
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(
            {
                key: "'" + value
                if isinstance(value, str) and re.match(r"^[\t\r\n ]*[=+@-]", value)
                else value
                for key, value in row.items()
            }
            for row in rows
        )


def configured_artifact_root(root: Path) -> Path | None:
    config_path = root / ".surface-atlas-local.json"
    if not config_path.is_file():
        return None
    try:
        config = read_json(config_path)
    except ValueError:
        return None
    value = config.get("artifact_root")
    if not isinstance(value, str):
        return None
    candidate = Path(value)
    return candidate.resolve() if candidate.is_dir() else None


def verified_artifact_source(root: Path, external_root: Path | None, artifact: dict[str, Any]) -> Path | None:
    path_text = artifact.get("path")
    if not isinstance(path_text, str):
        return None
    pure = safe_relative(path_text)
    if pure is None:
        return None
    roots = [root.resolve()]
    if external_root is not None:
        if artifact.get("storage") == "external-artifact-root":
            roots = [external_root, root.resolve()]
        else:
            roots.append(external_root)
    mismatch_messages: list[str] = []
    for base in roots:
        candidate = base.joinpath(*pure.parts).resolve()
        try:
            candidate.relative_to(base)
        except ValueError:
            continue
        if not candidate.is_file():
            continue
        expected_bytes = exact_int(artifact.get("bytes"))
        if expected_bytes is not None and candidate.stat().st_size != expected_bytes:
            mismatch_messages.append(f"bytes {candidate.stat().st_size} != {expected_bytes}")
            continue
        expected_hash = artifact.get("sha256")
        if isinstance(expected_hash, str) and expected_hash:
            if not re.fullmatch(r"[0-9a-fA-F]{64}", expected_hash):
                raise ValueError(f"artifact has malformed sha256: {path_text}")
            actual_hash = hashlib.sha256(candidate.read_bytes()).hexdigest()
            if actual_hash.casefold() != expected_hash.casefold():
                mismatch_messages.append(f"sha256 {actual_hash} != {expected_hash.casefold()}")
                continue
        return candidate
    if mismatch_messages:
        raise ValueError(f"artifact integrity check failed for {path_text}: {'; '.join(mismatch_messages)}")
    return None


def artifact_source_in_root(base: Path, artifact: dict[str, Any], *, label: str) -> tuple[PurePosixPath, Path]:
    """Resolve a portable artifact reference against one configured root."""

    path_text = artifact.get("path")
    if not isinstance(path_text, str):
        raise ValueError(f"{label} path is required")
    pure = safe_relative(path_text)
    if pure is None:
        raise ValueError(f"{label} path must be a safe relative path: {path_text}")
    base = base.resolve()
    candidate = base.joinpath(*pure.parts).resolve()
    try:
        candidate.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"{label} path escapes its configured root: {path_text}") from exc
    if not candidate.is_file():
        raise ValueError(f"{label} file does not exist: {path_text}")
    return pure, candidate


def copy_registration_receipt(
    root: Path,
    run_dir: Path,
    collection_metadata: dict[str, dict[str, Any]],
    *,
    atlas_id: str | None = None,
) -> dict[str, str]:
    """Copy and verify a supplied-library registration receipt.

    ``registration_receipt`` is collection metadata rather than a record
    artifact.  Its receipt binds the original collection bytes through
    ``output_artifact``; this avoids trusting a receipt that merely points at
    an unrelated file in the configured artifact root.
    """

    metadata = collection_metadata.get("molecular-library.json", {})
    reference = metadata.get("registration_receipt")
    if reference is None:
        return {}
    context = "molecular-library.json:registration_receipt"
    if not isinstance(reference, dict):
        raise ValueError(f"{context} must be an object")
    if reference.get("storage") != "external-artifact-root":
        raise ValueError(f"{context} storage must be external-artifact-root")
    external_root = configured_artifact_root(root)
    if external_root is None:
        raise ValueError(f"{context} requires a configured artifact root")
    receipt_path, receipt_source = artifact_source_in_root(
        external_root,
        reference,
        label=context,
    )
    try:
        receipt = read_json(receipt_source, required=True)
    except (OSError, ValueError) as exc:
        raise ValueError(f"{context} could not be read: {receipt_path.as_posix()}") from exc
    if receipt.get("schema_version") != REGISTRATION_RECEIPT_SCHEMA:
        raise ValueError(f"{context} has an unsupported schema_version")

    output_artifact = receipt.get("output_artifact")
    if not isinstance(output_artifact, dict):
        raise ValueError(f"{context} output_artifact must be an object")
    if output_artifact.get("storage") != "external-artifact-root":
        raise ValueError(f"{context} output_artifact storage must be external-artifact-root")
    _output_path, output_source = artifact_source_in_root(
        external_root,
        output_artifact,
        label=f"{context} output_artifact",
    )
    expected_bytes = output_artifact.get("bytes")
    if isinstance(expected_bytes, bool) or not isinstance(expected_bytes, int) or expected_bytes < 0:
        raise ValueError(f"{context} output_artifact has an invalid byte count")
    expected_hash = output_artifact.get("sha256")
    if not isinstance(expected_hash, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", expected_hash):
        raise ValueError(f"{context} output_artifact has an invalid sha256")

    receipt_data = receipt_source.read_bytes()
    try:
        output_data = output_source.read_bytes()
    except OSError as exc:
        raise ValueError(f"{context} output_artifact could not be read") from exc
    actual_hash = hashlib.sha256(output_data).hexdigest()
    if len(output_data) != expected_bytes or actual_hash.casefold() != expected_hash.casefold():
        raise ValueError(f"{context} output_artifact does not match its recorded bytes and hash")
    try:
        original_collection = json.loads(output_data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{context} output_artifact is not valid JSON") from exc
    if not isinstance(original_collection, dict):
        raise ValueError(f"{context} output_artifact must contain an object")
    if original_collection.get("schema_version") != REGISTERED_LIBRARY_SCHEMA:
        raise ValueError(f"{context} output_artifact has an unsupported schema_version")
    if atlas_id is not None and original_collection.get("atlas_id") != atlas_id:
        raise ValueError(f"{context} output_artifact atlas_id does not match the atlas")
    receipt_atlas_id = receipt.get("atlas_id")
    if not isinstance(receipt_atlas_id, str) or not receipt_atlas_id:
        raise ValueError(f"{context} receipt atlas_id is required")
    if original_collection.get("atlas_id") != receipt_atlas_id:
        raise ValueError(f"{context} receipt atlas_id does not match output_artifact")
    receipt_library_id = receipt.get("library_id")
    if not isinstance(receipt_library_id, str) or not receipt_library_id:
        raise ValueError(f"{context} receipt library_id is required")
    else:
        included_library_ids = original_collection.get("included_library_ids")
        if isinstance(included_library_ids, list):
            if receipt_library_id not in included_library_ids:
                raise ValueError(f"{context} receipt library_id is not included in output_artifact")
        elif original_collection.get("library_id") != receipt_library_id:
            raise ValueError(f"{context} receipt library_id does not match output_artifact")

    destination_root = Path("data") / "artifacts" / "registration"
    receipt_destination_relative = destination_root / "registration.json"
    output_destination_relative = destination_root / "molecular-library.json"

    def copy_verified(relative: Path, data: bytes, source: Path) -> None:
        destination = run_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if not destination.is_file() or destination.read_bytes() != data:
                raise ValueError(f"{context} collides with another report artifact")
        else:
            shutil.copy2(source, destination)

    copy_verified(receipt_destination_relative, receipt_data, receipt_source)
    copy_verified(output_destination_relative, output_data, output_source)
    return {
        str(reference["path"]): receipt_destination_relative.as_posix(),
        str(output_artifact["path"]): output_destination_relative.as_posix(),
    }


def copy_artifacts(
    root: Path,
    run_dir: Path,
    records_by_file: dict[str, list[dict[str, Any]]],
    binders: list[dict[str, Any]],
    *,
    collection_metadata: dict[str, dict[str, Any]] | None = None,
    atlas_id: str | None = None,
) -> dict[str, str]:
    artifact_map: dict[str, str] = {}
    if collection_metadata is not None:
        artifact_map.update(copy_registration_receipt(root, run_dir, collection_metadata, atlas_id=atlas_id))
    external_root = configured_artifact_root(root)
    all_records = [record for records in records_by_file.values() for record in records] + binders
    for record in all_records:
        for artifact in record_artifacts(record):
            path_text = artifact.get("path")
            if not isinstance(path_text, str) or path_text in artifact_map:
                continue
            pure = safe_relative(path_text)
            if pure is None:
                continue
            source = verified_artifact_source(root, external_root, artifact)
            if source is None:
                continue
            destination_relative = Path("data") / "artifacts" / Path(*pure.parts)
            destination = run_dir / destination_relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            artifact_map[path_text] = destination_relative.as_posix()
    return artifact_map


def load_optional_binder_data(
    root: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Load generated candidates, controls, and campaign-level status."""
    records: list[dict[str, Any]] = []
    controls: list[dict[str, Any]] = []
    campaigns: list[dict[str, Any]] = []
    paths: list[Path] = [root / name for name in OPTIONAL_BINDER_FILES]
    for directory_name in ("binders", "designs"):
        directory = root / directory_name
        if directory.is_dir():
            paths.extend(sorted(directory.rglob("*.json")))
    seen: set[Path] = set()
    for path in paths:
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        try:
            payload = read_json(path)
        except ValueError:
            continue
        if path.name == "binder-controls.json":
            control_records = payload.get("records")
            if isinstance(control_records, list):
                controls.extend(item for item in control_records if isinstance(item, dict))
            continue
        try:
            candidate_records = get_records(payload, source_name=path.name)
        except ValueError:
            continue
        if candidate_records:
            records.extend(candidate_records)
        elif any(key in payload for key in ("binder_id", "candidate_id", "sequence", "protein_sequence")):
            records.append(payload)
        control_records = payload.get("controls")
        if isinstance(control_records, list):
            controls.extend(item for item in control_records if isinstance(item, dict))
        if any(key in payload for key in ("campaign_id", "control_calibration_status", "stage_states")):
            campaigns.append(
                {
                    "source_file": path.name,
                    "campaign_id": payload.get("campaign_id"),
                    "request_id": payload.get("request_id"),
                    "target_id": payload.get("target_id"),
                    "execution_state": payload.get("execution_state"),
                    "control_calibration_status": payload.get("control_calibration_status"),
                    "counts": payload.get("counts"),
                    "stage_states": payload.get("stage_states"),
                    "claim_ceiling": payload.get("claim_ceiling"),
                }
            )
    return records, controls, campaigns


def write_data_exports(
    run_dir: Path,
    plan: dict[str, Any],
    ledger: dict[str, Any],
    collections: dict[str, list[dict[str, Any]]],
    binders: list[dict[str, Any]],
    binder_controls: list[dict[str, Any]],
    binder_campaigns: list[dict[str, Any]],
    generated_at: str,
    artifact_map: dict[str, str],
    collection_metadata: dict[str, dict[str, Any]] | None = None,
) -> None:
    data_dir = run_dir / "data"
    collections_dir = data_dir / "collections"
    collections_dir.mkdir(parents=True, exist_ok=True)
    consolidated: dict[str, Any] = {
        "schema_version": "codex-surface-report-data/v0.1",
        "generated_at": generated_at,
        "atlas_id": plan.get("atlas_id"),
        "plan": plan,
        "search_ledger": ledger,
        "collections": collections,
        "collection_metadata": collection_metadata or {},
        "designed_binders": binders,
        "binder_controls": binder_controls,
        "binder_campaigns": binder_campaigns,
        "artifact_map": artifact_map,
    }
    (data_dir / "atlas.json").write_text(pretty_json(consolidated) + "\n", encoding="utf-8")
    for filename in ("atlas-plan.json", "search-ledger.json"):
        payload = plan if filename == "atlas-plan.json" else ledger
        (data_dir / filename).write_text(pretty_json(payload) + "\n", encoding="utf-8")
    for filename, records in collections.items():
        payload = {
            "atlas_id": plan.get("atlas_id"),
            **(collection_metadata or {}).get(filename, {}),
            "records": records,
        }
        (data_dir / filename).write_text(pretty_json(payload) + "\n", encoding="utf-8")
        (collections_dir / filename).write_text(pretty_json(payload) + "\n", encoding="utf-8")
    (data_dir / "binders.json").write_text(pretty_json({"atlas_id": plan.get("atlas_id"), "records": binders}) + "\n", encoding="utf-8")
    (data_dir / "binder-controls.json").write_text(
        pretty_json({"atlas_id": plan.get("atlas_id"), "records": binder_controls}) + "\n",
        encoding="utf-8",
    )
    (data_dir / "binder-campaigns.json").write_text(
        pretty_json({"atlas_id": plan.get("atlas_id"), "records": binder_campaigns}) + "\n",
        encoding="utf-8",
    )

    target_rows = []
    for index, record in enumerate(collections.get("targets.json", [])):
        target_rows.append(
            flatten_record(
                record,
                typed_record_id(record, index, "target", "target_id", "entity_id"),
                record_name(record, typed_record_id(record, index, "target", "target_id", "entity_id")),
                extra={"entity_class": pick(record, "entity_class", "entity_type", "class"), "structure_tier": pick(record, "structure_tier", "structure_wave", "resource_tier")},
            )
        )
    write_csv(data_dir / "targets.csv", target_rows)
    molecule_rows = [
        flatten_record(
            record,
            typed_record_id(record, index, "molecule", "molecule_id"),
            record_name(record, typed_record_id(record, index, "molecule", "molecule_id")),
            extra={
                "category": molecule_category(record),
                "molecular_format": molecule_format(record),
                "identity_state": pick(record, "identity_state", "validation_state", "evidence_class"),
                "source_class": pick(record, "source_class", "source_type", "origin", "panel"),
                "structure_string": molecule_structure_string(record)[1],
                "chemistry_flags": molecule_flags(record, "chemistry_flags", "chemistry_review_flags"),
                "preparation": molecule_flags(record, "preparation_flags", "preparation_state", "preparation_status"),
                "known_interaction_refs": "; ".join(molecule_known_refs(record)),
                "target_lookup_intentions": "; ".join(molecule_intentions(record)),
            },
        )
        for index, record in enumerate(collections.get("molecular-library.json", []))
    ]
    write_csv(data_dir / "molecular-library.csv", molecule_rows)
    screening_rows = [
        flatten_record(
            record,
            typed_record_id(
                record, index, "screening", "screening_result_id", "screening_id", "screen_id", "result_id"
            ),
            record_name(
                record,
                typed_record_id(
                    record,
                    index,
                    "screening",
                    "screening_result_id",
                    "screening_id",
                    "screen_id",
                    "result_id",
                ),
            ),
            extra={
                "run_id": record.get("run_id"),
                "screen_role": screening_role(record),
                "molecule": pick(record, "molecule_name", "molecule_id", "library_member_id", "compound_name"),
                "site_id": pick(record, "site_id", "site", "binding_site", "epitope", "pocket", "docking_scope"),
                "site": pick(record, "site", "binding_site", "epitope", "pocket", "docking_scope"),
                "route": pick(record, "route", "workflow", "pipeline", "provider", "tool"),
                "model": pick(record, "model_version", "model", "predictor", "version"),
                "scoring_function": pick(record, "scoring_function", "scoring"),
                "score_units": pick(record, "score_units", "units"),
                "pose": pick(record, "pose_id", "pose", "pose_rank", "pose_name", "pose_artifact"),
                "pose_score": record.get("pose_score"),
                "score": pick(record, "pose_score", "docking_score", "affinity_score", "score"),
                "repeatability_or_confidence": screening_repeatability(record),
                "control_status": pick(record, "control_status", "controls_status", "control_state"),
                "failure_reason": pick(record, "failure_reason", "failure", "error", "reason"),
                "execution_state": pick(record, "execution_state", "state", "status"),
                "claim": "computational-screening-hypothesis",
            },
        )
        for index, record in enumerate(collections.get("screening-results.json", []))
    ]
    write_csv(data_dir / "screening-results.csv", screening_rows)
    for file_key, stem, prefix in (
        ("interventions.json", "interventions", "intervention"),
        ("structures.json", "structures", "structure"),
        ("opportunities.json", "opportunities", "opportunity"),
        ("capabilities.json", "capabilities", "capability"),
    ):
        rows = [flatten_record(record, typed_record_id(record, index, prefix, f"{prefix}_id"), record_name(record, typed_record_id(record, index, prefix, f"{prefix}_id"))) for index, record in enumerate(collections.get(file_key, []))]
        write_csv(data_dir / f"{stem}.csv", rows)
    binder_rows = [flatten_record(record, typed_record_id(record, index, "binder", "binder_id", "candidate_id", "design_id"), record_name(record, typed_record_id(record, index, "binder", "binder_id", "candidate_id", "design_id")), extra={"sequence": pick(record, "sequence", "protein_sequence", "binder_sequence", "seq")}) for index, record in enumerate(binders)]
    write_csv(data_dir / "binders.csv", binder_rows)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("atlas_directory", type=Path, help="Atlas workspace containing atlas-plan.json")
    parser.add_argument("--output-root", type=Path, help="Parent for results/<atlas_id>/<run_id>; defaults beside the atlas")
    parser.add_argument("--run-id", help="Timestamp directory name override, useful for reproducible tests")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Print a machine-readable result")
    return parser.parse_args(argv)


def _main(argv: list[str] | None, cleanup_paths: list[Path]) -> int:
    args = parse_args(argv)
    root = args.atlas_directory.resolve()
    try:
        plan = read_json(root / "atlas-plan.json", required=True)
        ledger = read_json(root / "search-ledger.json", required=True)
    except (FileNotFoundError, ValueError) as exc:
        print(f"build_report: {exc}", file=sys.stderr)
        return 1
    atlas_id = scalar_text(plan.get("atlas_id"), empty="atlas")
    if not SAFE_ID_RE.fullmatch(atlas_id):
        print("build_report: atlas-plan.json has an invalid atlas_id", file=sys.stderr)
        return 1
    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{2,63}", run_id):
        print("build_report: --run-id must contain 3-64 letters, digits, dots, underscores, or hyphens", file=sys.stderr)
        return 1

    collections: dict[str, list[dict[str, Any]]] = {}
    collection_metadata: dict[str, dict[str, Any]] = {}
    for filename in COLLECTION_FILES:
        try:
            payload = read_json(root / filename)
            records = get_records(
                payload, source_name=filename, records_required=True
            )
            validate_collection_ids(filename, records)
            if payload.get("atlas_id", atlas_id) != atlas_id:
                raise ValueError(f"{filename}: atlas_id does not match atlas-plan.json")
            if filename == "screening-results.json":
                from .report_presentation import screening_run_contexts
                screening_run_contexts(payload, records)
            collections[filename] = records
            collection_metadata[filename] = {key: value for key, value in payload.items() if key != "records"}
        except ValueError as exc:
            print(f"build_report: {exc}", file=sys.stderr)
            return 1
    binders, binder_controls, binder_campaigns = load_optional_binder_data(root)

    from .sequence_sites import validate_sequence_sites, render_sequence_sites
    from .action_comparison import validate_action_evidence, render_action_comparison, build_action_comparison
    from .research_intake import validate_optional_research, render_campaigns, render_assays
    targets = collections.get("targets.json", [])
    extension_errors = validate_sequence_sites(root, targets, collections.get("structures.json", []))
    extension_errors.extend(validate_action_evidence(targets))
    extension_errors.extend(validate_optional_research(root, atlas_id, targets))
    from .evidence_intake import reconcile_evidence, has_managed_evidence
    try:
        if ledger.get("data_kind") in {"synthetic", "public-source"} or has_managed_evidence(root, ledger):
            if not reconcile_evidence(root)["consistent"]:
                extension_errors.append("search ledger differs from reconciled source evidence")
    except (ValueError, OSError) as exc:
        extension_errors.append(str(exc))
    if extension_errors:
        print("build_report: " + "; ".join(extension_errors), file=sys.stderr)
        return 1
    research_payloads = {}
    for filename in ("binder-runs.json", "assay-results.json"):
        if (root / filename).exists():
            payload = read_json(root / filename, required=True)
            research_payloads[filename] = payload
            collections[filename] = payload["records"]
            collection_metadata[filename] = {key: value for key, value in payload.items() if key != "records"}

    output_root = (args.output_root or root.parent / "results").resolve()
    final_run_dir = output_root / atlas_id / run_id
    if final_run_dir.exists():
        print(
            "build_report: refusing to overwrite an existing report run; choose a new --run-id",
            file=sys.stderr,
        )
        return 1
    final_run_dir.parent.mkdir(parents=True, exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(prefix=f".{run_id}.", dir=final_run_dir.parent))
    cleanup_paths.append(run_dir)
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    plan, ledger = derive_report_state(root, plan, ledger, collections, binders)
    artifact_records = dict(collections)
    artifact_records["search-ledger.json"] = [ledger]
    try:
        artifact_map = copy_artifacts(
            root,
            run_dir,
            artifact_records,
            binders + binder_controls,
            collection_metadata=collection_metadata,
            atlas_id=atlas_id,
        )
    except ValueError as exc:
        print(f"build_report: {exc}", file=sys.stderr)
        return 1
    write_data_exports(
        run_dir,
        plan,
        ledger,
        collections,
        binders,
        binder_controls,
        binder_campaigns,
        generated_at,
        artifact_map,
        collection_metadata,
    )

    (run_dir / "assets").mkdir()
    source_asset_dir = Path(__file__).resolve().parent / "assets" / "report"
    for asset_name in (
        "report.css",
        "report.js",
        "presentation.css",
        "presentation.js",
        "workflows.css",
        "diagrams.css",
        "structure-preview.css",
        "structure-preview.js",
        "sequence-sites.css",
        "sequence-sites.js",
        "action-comparison.css",
        "action-comparison.js",
    ):
        shutil.copy2(source_asset_dir / asset_name, run_dir / "assets" / asset_name)
    vendor_source_dir = source_asset_dir / "vendor"
    vendor_destination = run_dir / "assets" / "vendor"
    vendor_destination.mkdir()
    for vendor_name in (
        "3Dmol-2.5.5.min.js",
        "3Dmol-LICENSE.txt",
        "3Dmol-min.js.LICENSE.txt",
        "README.md",
    ):
        shutil.copy2(vendor_source_dir / vendor_name, vendor_destination / vendor_name)

    profiles = [target_profile(record, index) for index, record in enumerate(collections.get("targets.json", []))]
    unique_slugs(profiles)
    target_hrefs = {profile["id"]: f'target-{profile["slug"]}.html' for profile in profiles}
    (run_dir / "data" / "action-comparison.json").write_text(
        pretty_json(build_action_comparison(targets, target_hrefs)) + "\n", encoding="utf-8")
    plan_for_footer = dict(plan)
    plan_for_footer["_ledger"] = ledger
    library_metadata = collection_metadata.get("molecular-library.json", {})
    registration_reference = library_metadata.get("registration_receipt")
    registration_receipt_path = (
        registration_reference.get("path")
        if isinstance(registration_reference, dict) and isinstance(registration_reference.get("path"), str)
        else None
    )
    registration_original_path = (
        "molecular-library.json"
        if registration_receipt_path and artifact_map.get("molecular-library.json")
        else None
    )

    pages: list[str] = []
    from .report_presentation import narrative_overview, render_explorer, render_screen_readout
    study_body = render_study(plan_for_footer, ledger, collections, binders, generated_at)
    for filename, current, body in (
        ("index.html", "overview", narrative_overview(sys.modules[__name__], plan_for_footer, ledger, collections, binders, artifact_map, generated_at)),
        ("explore.html", "explore", render_explorer(sys.modules[__name__], profiles, collections)),
        ("screening.html", "screening", render_screen_readout(sys.modules[__name__], collections.get("screening-results.json", []), artifact_map, profiles, collection_metadata.get("screening-results.json"))),
        ("study.html", "study", study_body),
        ("targets.html", "targets", render_targets(profiles)),
        ("action-comparison.html", "action-comparison", page_heading("Evidence and intended use", "Compare actions") + render_action_comparison(targets, target_hrefs)),
        ("sequence-sites.html", "sequence-sites", page_heading("Molecular identity", "Sequence & sites") + render_sequence_sites(targets, artifact_map)),
        ("campaigns.html", "campaigns", page_heading("Registered evidence", "Campaign runs", "Exact constructs, lineage, controls, and explicit promotion decisions.") + render_campaigns(research_payloads.get("binder-runs.json"), artifact_map, target_hrefs)),
        ("assays.html", "assays", page_heading("Returned evidence", "Assay returns", "Measurements retain units, censoring, replicates, and control outcomes.") + render_assays(research_payloads.get("assay-results.json"), artifact_map, target_hrefs)),
        ("treatments.html", "treatments", render_treatments(collections.get("interventions.json", []))),
        (
            "molecular-library.html",
            "molecular-library",
            render_molecule_library(
                collections.get("molecular-library.json", []),
                collections.get("screening-results.json", []),
                artifact_map,
                registration_receipt_path=registration_receipt_path,
                registration_original_path=registration_original_path,
            ),
        ),
        ("structures.html", "structures", render_structures(collections.get("structures.json", []), artifact_map)),
        ("binders.html", "binders", render_binders(binders, binder_controls, binder_campaigns, artifact_map)),
        (
            "design-sources.html",
            "design-sources",
            render_design_sources(plan_for_footer, ledger, collections.get("opportunities.json", []), collections.get("capabilities.json", []), []),
        ),
    ):
        (run_dir / filename).write_text(page_html(title=current.replace("-", " ").title(), current=current, atlas_id=atlas_id, plan=plan_for_footer, body=body, generated_at=generated_at), encoding="utf-8")
        pages.append(filename)
    for profile in profiles:
        filename = f'target-{profile["slug"]}.html'
        body = render_target_dossier(profile, collections, artifact_map, binders, binder_controls)
        run_count = sum(run["target_id"] == profile["id"] for run in collections.get("binder-runs.json", []))
        assay_count = sum(record["target_id"] == profile["id"] for record in collections.get("assay-results.json", []))
        if run_count or assay_count:
            body += section("Registered runs and returned measurements", render_downloads([
                (f"{run_count} independent campaign runs", "campaigns.html", False),
                (f"{assay_count} assay return records", "assays.html", False),
            ]), kicker="Exact construct provenance")
        (run_dir / filename).write_text(page_html(title=f"{profile['name']} dossier", current="targets", atlas_id=atlas_id, plan=plan_for_footer, body=body, generated_at=generated_at), encoding="utf-8")
        pages.append(filename)

    handoffs: list[tuple[str, dict[str, Any]]] = []
    handoff_paths = discover_handoff_files(root)
    for handoff_path in handoff_paths:
        try:
            handoffs.append((handoff_path.relative_to(root).as_posix(), read_json(handoff_path)))
        except ValueError:
            continue
    handoff_map = copy_handoff_files(root, run_dir, handoff_paths)
    # Regenerate Design & sources with handoffs now that the source directory is known.
    design_body = render_design_sources(plan_for_footer, ledger, collections.get("opportunities.json", []), collections.get("capabilities.json", []), handoffs, handoff_map)
    (run_dir / "design-sources.html").write_text(page_html(title="Design & sources", current="design-sources", atlas_id=atlas_id, plan=plan_for_footer, body=design_body, generated_at=generated_at), encoding="utf-8")

    manifest = {
        "schema_version": "codex-surface-report-run/v0.1",
        "atlas_id": atlas_id,
        "generated_at": generated_at,
        "run_id": run_id,
        "execution_label": execution_label(plan),
        "coverage_label": coverage_label(ledger),
        "pages": sorted(pages),
        "artifact_count": len(artifact_map),
        "registered_binder_runs": len(collections.get("binder-runs.json", [])),
        "assay_results": len(collections.get("assay-results.json", [])),
        "provider_calls": False,
        "external_urls_fetched": False,
        "claim_ceiling": plan.get("claim_ceiling", "not recorded"),
    }
    (run_dir / "run-manifest.json").write_text(pretty_json(manifest) + "\n", encoding="utf-8")

    from .export import _rename_directory_exclusive

    try:
        _rename_directory_exclusive(run_dir, final_run_dir)
    except OSError as exc:
        print(f"build_report: could not publish report without overwriting a path: {exc}", file=sys.stderr)
        return 1
    cleanup_paths.remove(run_dir)
    run_dir = final_run_dir
    result = {
        "run_directory": str(run_dir),
        "index": str(run_dir / "index.html"),
        "pages": len(pages),
        "targets": len(profiles),
        "structures": len(collections.get("structures.json", [])),
        "designed_binders": len(binders),
        "registered_binder_runs": len(collections.get("binder-runs.json", [])),
        "assay_results": len(collections.get("assay-results.json", [])),
        "provider_calls": False,
        "external_urls_fetched": False,
    }
    if args.json_output:
        print(json.dumps(result, indent=2))
    else:
        print(f"Built offline Surface Atlas report: {run_dir}")
    return 0


def main(argv: list[str] | None = None) -> int:
    cleanup_paths: list[Path] = []
    try:
        return _main(argv, cleanup_paths)
    finally:
        for path in cleanup_paths:
            shutil.rmtree(path, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
