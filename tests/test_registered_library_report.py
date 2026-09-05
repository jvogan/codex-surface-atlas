from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from surface_atlas.example import create_example
from surface_atlas.library_registration import register_library
from surface_atlas.report import ReportError, build_report
from surface_atlas.validator import validate_workspace


REPOSITORY = Path(__file__).resolve().parents[1]
SYNTHETIC = REPOSITORY / "examples" / "synthetic-atlas"


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def registration_manifest(source: Path) -> dict[str, Any]:
    return {
        "schema_version": "surface-atlas-supplied-library-registration/v1",
        "atlas_id": "synthetic-surface-atlas",
        "library_id": "registered-example",
        "inputs": [
            {
                "input_library_id": "supplied-compounds",
                "format": "smiles",
                "molecular_class": "small-molecule",
                "path": str(source),
            }
        ],
    }


def registered_atlas(tmp_path: Path) -> tuple[Path, Path]:
    source = tmp_path / "private-inputs" / "CASE-INPUT-FILENAME.smi"
    source.parent.mkdir()
    source.write_text("C M-001\n", encoding="utf-8")
    manifest = tmp_path / "registration.json"
    save(manifest, registration_manifest(source))
    bundle = tmp_path / "registered-library"
    register_library(manifest, bundle)

    atlas = tmp_path / "atlas"
    create_example(atlas)
    shutil.copy2(bundle / "molecular-library.json", atlas / "molecular-library.json")
    save(atlas / ".surface-atlas-local.json", {"artifact_root": str(bundle)})
    return atlas, bundle


@pytest.mark.parametrize(
    "field",
    ["artifacts", "source_artifact", "source_record_artifact", "modification_sidecar_artifact"],
)
def test_validator_rejects_nested_registered_artifact_tampering(tmp_path: Path, field: str) -> None:
    atlas = Path(shutil.copytree(SYNTHETIC, tmp_path / "atlas"))
    external = tmp_path / "external"
    external.mkdir()
    bad_file = external / "tampered.bin"
    bad_data = b"tampered"
    bad_file.write_bytes(bad_data)
    save(atlas / ".surface-atlas-local.json", {"artifact_root": str(external)})

    library = load(atlas / "molecular-library.json")
    bad_artifact = {
        "path": bad_file.name,
        "storage": "external-artifact-root",
        "bytes": len(bad_data),
        "sha256": "0" * 64,
    }
    record = library["records"][0]
    if field == "artifacts":
        record.setdefault("lineage", {})[field] = [bad_artifact]
    else:
        record.setdefault("lineage", {})[field] = bad_artifact
    save(atlas / "molecular-library.json", library)

    result = validate_workspace(atlas)

    assert result["valid"] is False
    assert any(field in error and "hash" in error for error in result["errors"])


def test_validator_does_not_treat_arbitrary_path_payload_as_an_artifact(tmp_path: Path) -> None:
    atlas = Path(shutil.copytree(SYNTHETIC, tmp_path / "atlas"))
    library = load(atlas / "molecular-library.json")
    library["records"][0]["arbitrary_evidence"] = {
        "path": "missing-not-an-artifact.bin",
        "bytes": 1,
        "sha256": "f" * 64,
    }
    save(atlas / "molecular-library.json", library)

    result = validate_workspace(atlas)

    assert result["valid"] is True, result


def test_report_copies_and_exposes_verified_registration_receipt(tmp_path: Path) -> None:
    atlas, bundle = registered_atlas(tmp_path)

    validation = validate_workspace(atlas)
    assert validation["valid"] is True, validation
    result = build_report(atlas, output_root=tmp_path / "reports", run_id="registered-library")
    run = Path(result["run_directory"])

    source_receipt = bundle / "registration.json"
    source_library = bundle / "molecular-library.json"
    copied_receipt = run / "data" / "artifacts" / "registration" / "registration.json"
    copied_library = run / "data" / "artifacts" / "registration" / "molecular-library.json"
    assert copied_receipt.read_bytes() == source_receipt.read_bytes()
    assert hashlib.sha256(copied_receipt.read_bytes()).hexdigest() == hashlib.sha256(source_receipt.read_bytes()).hexdigest()
    assert copied_library.read_bytes() == source_library.read_bytes()
    html = (run / "molecular-library.html").read_text(encoding="utf-8")
    assert 'href="data/artifacts/registration/registration.json"' in html
    assert 'href="data/artifacts/registration/molecular-library.json"' in html
    assert "Registration receipt" in html
    assert "Original imported library" in html

    original_library = load(atlas / "molecular-library.json")
    exported_library = load(run / "data" / "molecular-library.json")
    assert exported_library["registration_receipt"] == original_library["registration_receipt"]

    report_text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in run.rglob("*")
        if path.is_file()
    )
    assert str(tmp_path) not in report_text
    assert "CASE-INPUT-FILENAME" not in report_text


def test_enriched_current_library_keeps_original_receipt_and_snapshot(tmp_path: Path) -> None:
    atlas, bundle = registered_atlas(tmp_path)
    current_path = atlas / "molecular-library.json"
    current = load(current_path)
    current["records"][0]["known_target_ids"] = ["T-EMBER"]
    current["records"][0]["annotations"] = {"reviewed": True}
    save(current_path, current)

    validation = validate_workspace(atlas)
    assert validation["valid"] is True, validation
    result = build_report(atlas, output_root=tmp_path / "reports", run_id="enriched-library")
    run = Path(result["run_directory"])

    original_snapshot = run / "data" / "artifacts" / "registration" / "molecular-library.json"
    assert original_snapshot.read_bytes() == (bundle / "molecular-library.json").read_bytes()
    assert original_snapshot.read_bytes() != current_path.read_bytes()
    exported = load(run / "data" / "molecular-library.json")
    assert exported["records"][0]["known_target_ids"] == ["T-EMBER"]
    assert exported["records"][0]["annotations"] == {"reviewed": True}
    html = (run / "molecular-library.html").read_text(encoding="utf-8")
    assert 'href="data/artifacts/registration/registration.json"' in html
    assert 'href="data/artifacts/registration/molecular-library.json"' in html


def test_report_rejects_tampered_original_registered_collection(tmp_path: Path) -> None:
    atlas, bundle = registered_atlas(tmp_path)
    original = load(bundle / "molecular-library.json")
    original["records"][0]["annotations"] = {"tampered": True}
    save(bundle / "molecular-library.json", original)

    validation = validate_workspace(atlas)
    assert validation["valid"] is False
    assert any("output hash" in error for error in validation["errors"])
    with pytest.raises(ReportError, match="registration_receipt"):
        build_report(atlas, output_root=tmp_path / "reports", run_id="tampered-original")


def test_report_rejects_registration_receipt_that_does_not_bind_library_bytes(tmp_path: Path) -> None:
    atlas, bundle = registered_atlas(tmp_path)
    receipt = load(bundle / "registration.json")
    receipt["output_artifact"]["sha256"] = "0" * 64
    save(bundle / "registration.json", receipt)

    with pytest.raises(ReportError, match="registration_receipt"):
        build_report(atlas, output_root=tmp_path / "reports", run_id="bad-registration")
