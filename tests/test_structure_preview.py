from __future__ import annotations

import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from surface_atlas.report import build_report
from surface_atlas.schemas import STRUCTURE_SNAPSHOT_SCHEMA
from surface_atlas.structure_preview import snapshot_errors
from surface_atlas.validator import validate_workspace
from surface_atlas.workspace import initialize_atlas


REPOSITORY = Path(__file__).resolve().parents[1]


def save(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def add_snapshot(atlas: Path, *, invalid_path: str | None = None, with_sequence: bool = False) -> tuple[Path, Path | None]:
    coordinate = atlas / "media" / "target.pdb"
    coordinate.parent.mkdir(parents=True, exist_ok=True)
    coordinate.write_text(
        "ATOM      1  N   ALA A   1       0.000   0.000   0.000  1.00 20.00           N\nEND\n",
        encoding="ascii",
    )
    source_path = invalid_path or "media/target.pdb"
    source = {
        "path": source_path,
        "bytes": coordinate.stat().st_size,
        "sha256": hashlib.sha256(coordinate.read_bytes()).hexdigest(),
        "format": "pdb",
        "object_name": "target",
        "state": 1,
    }
    snapshot = {
        "schema_version": STRUCTURE_SNAPSHOT_SCHEMA,
        "preview_id": "preview-target",
        "title": "Invented target preview",
        "evidence_class": "synthetic fixture",
        "coordinate_sources": [source],
        "layers": [
            {
                "object_name": "target",
                "selection": "chain A",
                "color": "#17675D",
                "representation": "cartoon",
                "color_mode": "solid",
                "opacity": 1.0,
                "label": "Invented target chain",
            }
        ],
    }
    sequence: Path | None = None
    if with_sequence:
        sequence = atlas / "media" / "target.fasta"
        sequence.write_text(">invented-target\nACDEFG\n", encoding="ascii")
        snapshot["sequence_artifact"] = {
            "path": "media/target.fasta",
            "bytes": sequence.stat().st_size,
            "sha256": hashlib.sha256(sequence.read_bytes()).hexdigest(),
            "sequence_id": "invented-target",
            "chain": "A",
        }
    structures = json.loads((atlas / "structures.json").read_text(encoding="utf-8"))
    structures["records"] = [
        {
            "structure_id": "S-INVENTED-01",
            "target_id": "T-EMBER",
            "accession": None,
            "evidence_class": "synthetic fixture",
            "claim_ceiling": "synthetic illustration",
            "structure_snapshots": [snapshot],
        }
    ]
    save(atlas / "structures.json", structures)
    return coordinate, sequence


def test_structure_snapshot_schema_and_validation_are_versioned(tmp_path: Path) -> None:
    atlas = tmp_path / "atlas"
    initialize_atlas("preview-atlas", atlas, disease="invented disease")
    add_snapshot(atlas)
    structures = json.loads((atlas / "structures.json").read_text(encoding="utf-8"))
    snapshot = structures["records"][0]["structure_snapshots"][0]
    schema = json.loads((REPOSITORY / "schemas/v0.1/structure-snapshot.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(snapshot)
    assert snapshot_errors(snapshot) == []
    assert validate_workspace(atlas)["valid"] is True


def test_report_emits_local_preview_and_verified_sequence_handoff(tmp_path: Path) -> None:
    atlas = tmp_path / "atlas"
    initialize_atlas("preview-atlas", atlas, disease="invented disease")
    add_snapshot(atlas, with_sequence=True)
    result = build_report(atlas, output_root=tmp_path / "reports", run_id="preview")
    run = Path(result["run_directory"])
    structures = (run / "structures.html").read_text(encoding="utf-8")
    assert 'data-structure-preview="data/artifacts/media/target.pdb"' in structures
    assert "View in 3D" in structures
    assert "data-structure-sequence" in structures
    assert (run / "assets/structure-preview.css").is_file()
    assert (run / "assets/structure-preview.js").is_file()
    assert (run / "assets/vendor/3Dmol-2.5.5.min.js").is_file()
    assert "Copy Codex request" in (run / "assets/structure-preview.js").read_text(encoding="utf-8")
    all_text = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in run.rglob("*") if path.is_file())
    assert str(tmp_path) not in all_text


def test_invalid_snapshot_is_reported_and_static_report_remains_buildable(tmp_path: Path) -> None:
    atlas = tmp_path / "atlas"
    initialize_atlas("preview-atlas", atlas, disease="invented disease")
    add_snapshot(atlas, invalid_path="../outside.pdb")
    validation = validate_workspace(atlas)
    assert validation["valid"] is False
    assert any("safe relative path" in error for error in validation["errors"])
    result = build_report(atlas, output_root=tmp_path / "reports", run_id="invalid-preview")
    structures = Path(result["run_directory"]) / "structures.html"
    html = structures.read_text(encoding="utf-8")
    assert "data-structure-preview" not in html
    assert "No rendered image is recorded" in html


def test_multiple_snapshot_controls_show_titles(tmp_path: Path) -> None:
    atlas = tmp_path / "atlas"
    initialize_atlas("preview-atlas", atlas, disease="invented disease")
    add_snapshot(atlas)
    structures = json.loads((atlas / "structures.json").read_text(encoding="utf-8"))
    first = structures["records"][0]["structure_snapshots"][0]
    second = json.loads(json.dumps(first))
    second["preview_id"] = "preview-target-alt"
    second["title"] = "Invented target alternate view"
    structures["records"][0]["structure_snapshots"].append(second)
    save(atlas / "structures.json", structures)
    result = build_report(atlas, output_root=tmp_path / "reports", run_id="multiple-preview")
    html = (Path(result["run_directory"]) / "structures.html").read_text(encoding="utf-8")
    assert html.count('class="structure-preview-name"') == 2
    assert "Invented target alternate view" in html
