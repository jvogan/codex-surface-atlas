"""Exact canonical sequence selections backed by explicit PDB author numbering.

Optional target records only; no alignment, sequence guessing, or exposure inference.
"""
from __future__ import annotations

import hashlib
import html
import json
import math
import re
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA_VERSION = "codex-surface-sequence-sites/v0.1"
AA = dict(zip("ALA ARG ASN ASP CYS GLN GLU GLY HIS ILE LEU LYS MET PHE PRO SER THR TRP TYR VAL SEC PYL".split(), "ARNDCQEGHILKMFPSTWYVUO"))
TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,119}$")
HASH = re.compile(r"^[a-f0-9]{64}$")
MAX_BYTES = 8 * 1024 * 1024


def _rows(targets: Any) -> list:
    return targets.get("records", []) if isinstance(targets, dict) else targets if isinstance(targets, list) else []


def _span(value: Any, length: int) -> bool:
    return isinstance(value, dict) and type(value.get("start")) is int and type(value.get("end")) is int and 1 <= value["start"] <= value["end"] <= length


def _identity(value: Any) -> bool:
    return isinstance(value, str) and bool(TOKEN.fullmatch(value))


def _coordinate_bytes(root: Path, artifact: Any) -> bytes:
    if not isinstance(artifact, dict):
        raise ValueError("coordinates must be an artifact object")
    value = artifact.get("path")
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_./-]+", value):
        raise ValueError("unsafe coordinate artifact path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(p in ("", ".", "..") for p in value.split("/")) or path.suffix != ".pdb" or artifact.get("format") != "pdb":
        raise ValueError("coordinates require a safe relative .pdb path and pdb format")
    resolved = (root / value).resolve()
    if not resolved.is_relative_to(root.resolve()) or any(root.joinpath(*path.parts[:i]).is_symlink() for i in range(1, len(path.parts) + 1)):
        raise ValueError("coordinate artifact escapes workspace or uses a symlink")
    if type(artifact.get("bytes")) is not int or not 0 < artifact["bytes"] <= MAX_BYTES:
        raise ValueError("coordinate bytes must be between 1 and 8 MiB")
    if not isinstance(artifact.get("sha256"), str) or not HASH.fullmatch(artifact["sha256"]):
        raise ValueError("coordinate sha256 is required")
    if resolved.stat().st_size != artifact["bytes"]:
        raise ValueError("coordinate byte length mismatch")
    data = resolved.read_bytes()
    if hashlib.sha256(data).hexdigest() != artifact["sha256"]:
        raise ValueError("coordinate sha256 mismatch")
    return data


def _residues(data: bytes) -> dict[tuple, str]:
    residues: dict[tuple, str] = {}
    models = 0
    for line in data.decode("ascii").splitlines():
        if line.startswith("MODEL "):
            models += 1
            if models > 1 or line[10:14].strip() != "1":
                raise ValueError("multiple coordinate models are ambiguous")
        if not line.startswith("ATOM  "):
            continue
        if len(line) < 54:
            raise ValueError("truncated PDB atom")
        try:
            coordinates = [float(line[start:start + 8]) for start in (30, 38, 46)]
        except ValueError as exc:
            raise ValueError("PDB atom coordinates must be parseable finite numbers") from exc
        if not all(math.isfinite(value) for value in coordinates):
            raise ValueError("PDB atom coordinates must be parseable finite numbers")
        key = (line[21:22], int(line[22:26]), line[26:27].strip())
        residue = AA.get(line[17:20].strip())
        if residue is None:
            raise ValueError("unsupported PDB amino acid; no fuzzy mapping permitted")
        if key in residues and residues[key] != residue:
            raise ValueError("ambiguous coordinate residue identity")
        residues[key] = residue
    if not residues:
        raise ValueError("coordinates contain no supported protein atoms")
    return residues


def validate_sequence_sites(root: str | Path, targets: Any, structures: Any = None) -> list[str]:
    """Validate all optional target ``sequence_sites`` records, including file bytes.

    ``structures`` is reserved for callers passing their complete record context.
    Errors are strings; absence of this optional extension is valid.
    """
    errors = []
    seen = set()
    for target in _rows(targets):
        if not isinstance(target, dict) or "sequence_sites" not in target:
            continue
        identifier = target.get("target_id")
        context = f"targets.json: {identifier} sequence_sites"
        try:
            if not _identity(identifier) or identifier in seen:
                raise ValueError("missing or duplicate target identity")
            seen.add(identifier)
            record = target["sequence_sites"]
            if not isinstance(record, dict) or record.get("schema_version") != SCHEMA_VERSION:
                raise ValueError("invalid sequence-sites schema_version")
            if not _identity(record.get("accession")):
                raise ValueError("exact accession/isoform identity is required")
            if "isoform" not in record or (record["isoform"] is not None and not _identity(record["isoform"])) or not _identity(record.get("source_id")):
                raise ValueError("explicit isoform (nullable) and source_id are required")
            if type(record.get("coordinate_model")) is not int or record["coordinate_model"] != 1 or record.get("numbering") != "author":
                raise ValueError("coordinate_model must be 1 and numbering must be author")
            sequence = record.get("sequence")
            if not isinstance(sequence, str) or not re.fullmatch(r"[ACDEFGHIKLMNPQRSTVWYUO]{1,10000}", sequence):
                raise ValueError("sequence must contain 1–10000 exact uppercase amino acids")
            length = len(sequence)
            if type(record.get("length")) is not int or record["length"] != length:
                raise ValueError("canonical sequence length mismatch")
            if hashlib.sha256(sequence.encode("ascii")).hexdigest() != record.get("sequence_sha256"):
                raise ValueError("canonical sequence sha256 mismatch")
            residues = _residues(_coordinate_bytes(Path(root), record.get("coordinates")))
            mappings, gaps, extracellular, partners = (record.get(k) for k in ("mappings", "unresolved", "extracellular", "partners"))
            if any(not isinstance(v, list) for v in (mappings, gaps, extracellular, partners)):
                raise ValueError("mappings, unresolved, extracellular and partners must be arrays")
            if len(partners) > 19:
                raise ValueError("at most 19 partner chains are supported")
            covered, coordinate_keys = set(), set()
            for row in mappings:
                if not isinstance(row, dict):
                    raise ValueError("mapping must be an object")
                position = row.get("canonical_position")
                chain, number, insertion = (row.get(k) for k in ("chain", "author_residue_number", "insertion_code"))
                if type(position) is not int or not 1 <= position <= length or position in covered:
                    raise ValueError("invalid or duplicate canonical mapping position")
                if not isinstance(chain, str) or not re.fullmatch(r"[A-Za-z0-9]", chain) or type(number) is not int or not isinstance(insertion, str) or not re.fullmatch(r"[A-Za-z0-9]?", insertion):
                    raise ValueError("explicit author chain, residue number and insertion code required")
                key = (chain, number, insertion)
                if key in coordinate_keys or residues.get(key) != sequence[position - 1]:
                    raise ValueError("ambiguous or amino-acid-mismatched canonical-to-coordinate mapping")
                covered.add(position)
                coordinate_keys.add(key)
            for gap in gaps:
                if not _span(gap, length):
                    raise ValueError("invalid unresolved span")
                positions = set(range(gap["start"], gap["end"] + 1))
                if covered & positions:
                    raise ValueError("overlapping unresolved span or mapped gap")
                covered.update(positions)
            if covered != set(range(1, length + 1)):
                raise ValueError("every canonical position must be explicitly mapped or unresolved")
            for row in extracellular:
                if not _span(row, length) or not isinstance(row.get("label"), str) or not row["label"].strip() or not _identity(row.get("source_id")):
                    raise ValueError("extracellular annotation needs a valid span, label and source_id")
            partner_ids, partner_chains = set(), set()
            target_chains = {key[0] for key in coordinate_keys}
            for row in partners:
                if not isinstance(row, dict) or not _identity(row.get("partner_id")) or not _identity(row.get("accession")) or not isinstance(row.get("label"), str) or not row["label"].strip():
                    raise ValueError("partner_id, accession and label are required")
                chain = row.get("chain")
                if not isinstance(chain, str) or not re.fullmatch(r"[A-Za-z0-9]", chain) or chain not in {key[0] for key in residues} or chain in target_chains or chain in partner_chains or row["partner_id"] in partner_ids:
                    raise ValueError("missing, duplicate or ambiguous partner chain/identity")
                partner_ids.add(row["partner_id"])
                partner_chains.add(chain)
        except (ValueError, OSError, UnicodeError, TypeError, KeyError) as exc:
            errors.append(f"{context}: {exc}")
    return errors


def sequence_site_artifacts(targets: Any) -> list[dict]:
    """Return coordinate artifact descriptors for the normal verified packager."""
    return [t["sequence_sites"]["coordinates"] for t in _rows(targets) if isinstance(t, dict) and isinstance(t.get("sequence_sites"), dict) and isinstance(t["sequence_sites"].get("coordinates"), dict)]


def render_sequence_sites(targets: Any, artifact_map: dict[str, str]) -> str:
    """Render validated records. Caller MUST validate before rendering/exporting."""
    records = []
    for target in _rows(targets):
        if not isinstance(target, dict) or not isinstance(target.get("sequence_sites"), dict):
            continue
        row = target["sequence_sites"]
        href = artifact_map.get(row["coordinates"]["path"])
        if not isinstance(href, str) or not re.fullmatch(r"data/artifacts/[A-Za-z0-9_./-]+", href) or any(p in ("", ".", "..") for p in href.split("/")):
            continue
        records.append({**row, "target_id": target["target_id"], "coordinates": {**row["coordinates"], "path": href}})
    if not records:
        return '<p>No verified sequence-to-site records are packaged.</p>'
    payload = html.escape(json.dumps(records, separators=(",", ":")), quote=True)
    return ('<section class="sequence-sites" data-sequence-sites="' + payload + '">'
            '<h2>Select a canonical sequence interval</h2>'
            '<p>Intervals are one-based and inclusive. Only exact verified mappings are shown in 3D; unresolved residues remain in the FASTA. Extracellular annotations are recorded source claims, not a new surface-exposure prediction.</p>'
            '<label>Target <select data-sequence-target></select></label>'
            '<div data-sequence-panels></div></section>')
