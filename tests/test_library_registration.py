from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath

import pytest

from surface_atlas.library_registration import LibraryRegistrationError, register_library


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def registration_manifest(inputs: list[dict], *, atlas_id: str = "atlas-test", library_id: str = "supplied-panel") -> dict:
    return {
        "schema_version": "surface-atlas-supplied-library-registration/v1",
        "atlas_id": atlas_id,
        "library_id": library_id,
        "purpose": "Provider-free synthetic registration test.",
        "inputs": inputs,
    }


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def artifact_path(bundle: Path, artifact: dict) -> Path:
    path = PurePosixPath(artifact["path"])
    assert not path.is_absolute() and ".." not in path.parts
    return bundle.joinpath(*path.parts)


def assert_registration_is_portable(value: object, private_root: Path) -> None:
    serialized = json.dumps(value)
    assert private_root.as_posix() not in serialized
    assert "CASE-INPUT-FILENAME" not in serialized


def test_registers_sdf_and_smiles_with_exact_portable_sources(tmp_path: Path) -> None:
    private = tmp_path / "private-inputs"
    private.mkdir()
    sdf_data = (
        "Supplied stereoisomer\n  SurfaceAtlas\n\n"
        "  1  0  0  0  0  0            999 V2000\n"
        "    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n"
        "M  END\n>  <ID>\nSDF-001\n\n>  <NAME>\nSupplied stereoisomer\n\n"
        ">  <SMILES>\nC[C@H](O)C\n\n>  <FORMAL_CHARGE>\n0\n\n$$$$\n"
    ).encode()
    sdf = private / "CASE-INPUT-FILENAME.sdf"
    sdf.write_bytes(sdf_data)
    smiles_data = b'C/C=C\\C SMI-001 "stereochemical alkene"\n'
    smiles = private / "CASE-INPUT-FILENAME.smi"
    smiles.write_bytes(smiles_data)
    manifest = tmp_path / "request" / "manifest.json"
    write_json(manifest, registration_manifest([
        {"input_library_id": "sdf-panel", "format": "sdf", "molecular_class": "small-molecule", "path": str(sdf)},
        {"input_library_id": "smiles-panel", "format": "smiles", "molecular_class": "natural-product", "path": str(smiles)},
    ]))

    bundle = tmp_path / "registered"
    result = register_library(manifest, bundle)
    library, receipt = load(bundle / "molecular-library.json"), load(bundle / "registration.json")
    records = {row["molecule_id"]: row for row in library["records"]}

    assert result["registered_records"] == 2
    assert records["SDF-001"]["source_smiles"] == "C[C@H](O)C"
    assert records["SMI-001"]["source_smiles"] == "C/C=C\\C"
    assert records["SMI-001"]["name"] == "stereochemical alkene"
    for record, original in ((records["SDF-001"], sdf_data), (records["SMI-001"], smiles_data)):
        source_artifact = record["source_artifact"]
        assert source_artifact["storage"] == "external-artifact-root"
        assert source_artifact["sha256"] == digest(original)
        assert artifact_path(bundle, source_artifact).read_bytes() == original
        assert "CASE-INPUT-FILENAME" not in source_artifact["path"]
        assert record["known_target_ids"] == [] and record["known_interaction_refs"] == []
        assert "target_id" not in record
    assert records["SDF-001"]["source_record_artifact"]["path"].endswith(".sdf")
    assert receipt["output_artifact"]["path"] == "molecular-library.json"
    assert receipt["output_artifact"]["sha256"] == digest((bundle / "molecular-library.json").read_bytes())
    assert receipt["provider_calls"] == receipt["network_calls"] == 0
    assert_registration_is_portable({"library": library, "receipt": receipt}, private)


def test_csv_fasta_sidecar_and_base_artifacts_are_preserved(tmp_path: Path) -> None:
    base_root = tmp_path / "base-bundle"
    base_artifact_data = b"BASE ARTIFACT\n"
    base_artifact_relative = PurePosixPath("libraries/base-input/source.sdf")
    base_artifact = base_root.joinpath(*base_artifact_relative.parts)
    base_artifact.parent.mkdir(parents=True)
    base_artifact.write_bytes(base_artifact_data)
    base_library = base_root / "molecular-library.json"
    base_record = {
        "molecule_id": "base-parent", "name": "Existing parent", "panel": "existing",
        "source_artifact": {"path": base_artifact_relative.as_posix(), "storage": "external-artifact-root",
                            "bytes": len(base_artifact_data), "sha256": digest(base_artifact_data)},
        "known_target_ids": [], "known_interaction_refs": [],
    }
    write_json(base_library, {
        "schema_version": "codex-surface-molecular-library/v0.1", "atlas_id": "atlas-test",
        "library_id": "base-library", "purpose": "Existing library", "custom_metadata": {"reviewed": True},
        "records": [base_record], "record_count": 1, "panel_counts": {"existing": 1},
    })

    inputs = tmp_path / "inputs"
    inputs.mkdir()
    csv_source = inputs / "children.csv"
    csv_source.write_text(
        "smiles,id,name,parent_id,formal_charge,preparation_state\n"
        "CCO,child-ethanol,Prepared ethanol,base-parent,0,prepared-microstate\n", encoding="utf-8"
    )
    fasta = inputs / "binders.fasta"
    fasta.write_text(">pep-01 cyclic peptide\nACDEFGHIK\n", encoding="utf-8")
    sidecar = inputs / "modifications.json"
    write_json(sidecar, {"records": {"pep-01": {"cyclization": "head-to-tail", "construct_boundaries": "1-9"}}})
    manifest = tmp_path / "manifest.json"
    write_json(manifest, registration_manifest([
        {"input_library_id": "csv-children", "format": "csv", "molecular_class": "metabolite", "path": str(csv_source)},
        {"input_library_id": "fasta-binders", "format": "fasta", "molecular_class": "modified-peptide",
         "path": str(fasta), "modification_sidecar": str(sidecar)},
    ], library_id="registration-batch"))

    bundle = tmp_path / "merged"
    register_library(manifest, bundle, base_library=base_library)
    library, receipt = load(bundle / "molecular-library.json"), load(bundle / "registration.json")
    records = {row["molecule_id"]: row for row in library["records"]}

    assert library["library_id"] == "base-library"
    assert library["custom_metadata"] == {"reviewed": True}
    assert library["record_count"] == 3
    assert library["included_library_ids"] == ["base-library", "registration-batch", "csv-children", "fasta-binders"]
    assert records["base-parent"] == base_record
    assert records["child-ethanol"]["parent_molecule_id"] == "base-parent"
    assert records["child-ethanol"]["formal_charge"] == "0"
    assert records["pep-01"]["sequence"] == "ACDEFGHIK"
    assert records["pep-01"]["construct_boundaries"] == "1-9"
    assert records["pep-01"]["modifications"] == {"cyclization": "head-to-tail"}
    assert artifact_path(bundle, base_record["source_artifact"]).read_bytes() == base_artifact_data
    assert artifact_path(bundle, receipt["base_library_artifact"]).read_bytes() == base_library.read_bytes()
    assert artifact_path(bundle, records["pep-01"]["modification_sidecar_artifact"]).read_bytes() == sidecar.read_bytes()
    assert_registration_is_portable({"library": library, "receipt": receipt}, tmp_path)


def test_duplicate_ids_and_parse_errors_leave_no_partial_directory(tmp_path: Path) -> None:
    first = tmp_path / "first.smi"
    second = tmp_path / "second.csv"
    first.write_text("CCO duplicate-id Ethanol\n", encoding="utf-8")
    second.write_text("smiles,id,name\nCCN,duplicate-id,Ethanamine\n", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    write_json(manifest, registration_manifest([
        {"format": "smiles", "molecular_class": "small-molecule", "path": str(first)},
        {"format": "csv", "molecular_class": "small-molecule", "path": str(second)},
    ]))
    output = tmp_path / "output"
    with pytest.raises(LibraryRegistrationError, match="duplicate molecule_id"):
        register_library(manifest, output)
    assert not output.exists()
    assert not list(tmp_path.glob(".output.tmp-*"))

    malformed = tmp_path / "malformed.sdf"
    malformed.write_text("not a MOL block\n$$$$\n", encoding="utf-8")
    write_json(manifest, registration_manifest([
        {"format": "sdf", "molecular_class": "small-molecule", "path": str(malformed)},
    ]))
    with pytest.raises(LibraryRegistrationError, match="MOL block terminator"):
        register_library(manifest, output)
    assert not output.exists()


def test_existing_output_and_symlink_or_special_inputs_are_rejected(tmp_path: Path) -> None:
    source = tmp_path / "source.smi"
    source.write_text("CCO item Ethanol\n", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    write_json(manifest, registration_manifest([
        {"format": "smiles", "molecular_class": "small-molecule", "path": str(source)},
    ]))
    output = tmp_path / "output"
    output.mkdir()
    marker = output / "keep.txt"
    marker.write_text("keep", encoding="utf-8")
    with pytest.raises(LibraryRegistrationError, match="must not already exist"):
        register_library(manifest, output)
    assert marker.read_text(encoding="utf-8") == "keep"

    alias = tmp_path / "alias.smi"
    alias.symlink_to(source)
    write_json(manifest, registration_manifest([
        {"format": "smiles", "molecular_class": "small-molecule", "path": str(alias)},
    ]))
    with pytest.raises(LibraryRegistrationError, match="symlink"):
        register_library(manifest, tmp_path / "symlink-output")


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO requires POSIX")
def test_special_input_is_rejected_without_blocking(tmp_path: Path) -> None:
    fifo = tmp_path / "input.smi"
    os.mkfifo(fifo)
    manifest = tmp_path / "manifest.json"
    write_json(manifest, registration_manifest([
        {"format": "smiles", "molecular_class": "small-molecule", "path": str(fifo)},
    ]))
    with pytest.raises(LibraryRegistrationError, match="regular file"):
        register_library(manifest, tmp_path / "output")


def test_base_mismatch_or_unresolved_artifact_fails_closed(tmp_path: Path) -> None:
    source = tmp_path / "source.smi"
    source.write_text("CCO item Ethanol\n", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    write_json(manifest, registration_manifest([
        {"format": "smiles", "molecular_class": "small-molecule", "path": str(source)},
    ]))
    base = tmp_path / "base.json"
    write_json(base, {
        "schema_version": "codex-surface-molecular-library/v0.1", "atlas_id": "other-atlas",
        "library_id": "base", "records": [],
    })
    with pytest.raises(LibraryRegistrationError, match="atlas_id differs"):
        register_library(manifest, tmp_path / "mismatch", base_library=base)
    assert not (tmp_path / "mismatch").exists()

    write_json(base, {
        "schema_version": "codex-surface-molecular-library/v0.1", "atlas_id": "atlas-test", "library_id": "base",
        "records": [{"molecule_id": "base-item", "source_artifact": {
            "path": "libraries/missing.sdf", "storage": "external-artifact-root",
            "bytes": 1, "sha256": "0" * 64,
        }}],
    })
    with pytest.raises(LibraryRegistrationError, match="base artifact"):
        register_library(manifest, tmp_path / "missing-artifact", base_library=base)
    assert not (tmp_path / "missing-artifact").exists()


def test_duplicate_csv_headers_are_rejected_without_output(tmp_path: Path) -> None:
    source = tmp_path / "input.csv"
    source.write_text("smiles,id,id\nCCO,item,other\n", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    write_json(manifest, registration_manifest([
        {"format": "csv", "molecular_class": "small-molecule", "path": str(source)},
    ]))
    with pytest.raises(LibraryRegistrationError, match="duplicate headers"):
        register_library(manifest, tmp_path / "output")
    assert not (tmp_path / "output").exists()


def test_smiles_names_preserve_apostrophes_backslashes_and_optional_outer_quotes(tmp_path: Path) -> None:
    source = tmp_path / "input.smi"
    source.write_text(
        "CCO item-one O'Brien 3'-prime\\label\n"
        'CCN item-two "O\'Brien 5\' analogue"\n',
        encoding="utf-8",
    )
    manifest = tmp_path / "manifest.json"
    write_json(manifest, registration_manifest([
        {"format": "smiles", "molecular_class": "small-molecule", "path": str(source)},
    ]))

    bundle = tmp_path / "output"
    register_library(manifest, bundle)
    records = {row["molecule_id"]: row for row in load(bundle / "molecular-library.json")["records"]}

    assert records["item-one"]["name"] == "O'Brien 3'-prime\\label"
    assert records["item-two"]["name"] == "O'Brien 5' analogue"


def test_base_artifact_ancestor_symlink_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "source.smi"
    source.write_text("CCO item Ethanol\n", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    write_json(manifest, registration_manifest([
        {"format": "smiles", "molecular_class": "small-molecule", "path": str(source)},
    ]))

    outside = tmp_path / "outside"
    outside.mkdir()
    artifact_data = b"outside artifact\n"
    (outside / "source.sdf").write_bytes(artifact_data)
    base_root = tmp_path / "base-bundle"
    (base_root / "libraries").mkdir(parents=True)
    (base_root / "libraries" / "linked").symlink_to(outside, target_is_directory=True)
    base = base_root / "molecular-library.json"
    write_json(base, {
        "schema_version": "codex-surface-molecular-library/v0.1",
        "atlas_id": "atlas-test",
        "library_id": "base",
        "records": [{
            "molecule_id": "base-item",
            "source_artifact": {
                "path": "libraries/linked/source.sdf",
                "storage": "external-artifact-root",
                "bytes": len(artifact_data),
                "sha256": digest(artifact_data),
            },
        }],
    })

    output = tmp_path / "output"
    with pytest.raises(LibraryRegistrationError, match="symlink"):
        register_library(manifest, output, base_library=base)
    assert not output.exists()


def test_conflicting_base_artifact_integrity_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "source.smi"
    source.write_text("CCO item Ethanol\n", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    write_json(manifest, registration_manifest([
        {"format": "smiles", "molecular_class": "small-molecule", "path": str(source)},
    ]))

    base_root = tmp_path / "base-bundle"
    artifact_data = b"base artifact\n"
    artifact_path = base_root / "libraries" / "shared.sdf"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_bytes(artifact_data)
    base = base_root / "molecular-library.json"
    first_reference = {
        "path": "libraries/shared.sdf",
        "storage": "external-artifact-root",
        "bytes": len(artifact_data),
        "sha256": digest(artifact_data),
    }
    second_reference = dict(first_reference, sha256="f" * 64)
    write_json(base, {
        "schema_version": "codex-surface-molecular-library/v0.1",
        "atlas_id": "atlas-test",
        "library_id": "base",
        "records": [
            {"molecule_id": "base-one", "source_artifact": first_reference},
            {"molecule_id": "base-two", "source_record_artifact": second_reference},
        ],
    })

    output = tmp_path / "output"
    with pytest.raises(LibraryRegistrationError, match="conflicts with another reference"):
        register_library(manifest, output, base_library=base)
    assert not output.exists()


@pytest.mark.parametrize(
    ("container", "reference"),
    [
        ("record", {"source_artifact": {"path": "libraries/source.sdf"}}),
        ("record", {"source_record_artifact": {"path": "libraries/record.sdf"}}),
        ("record", {"modification_sidecar_artifact": {"path": "libraries/sidecar.json"}}),
        ("root", {"artifacts": [{"path": "libraries/extra.dat"}]}),
    ],
)
def test_known_path_only_base_artifacts_are_rejected(
    tmp_path: Path, container: str, reference: dict,
) -> None:
    source = tmp_path / "source.smi"
    source.write_text("CCO item Ethanol\n", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    write_json(manifest, registration_manifest([
        {"format": "smiles", "molecular_class": "small-molecule", "path": str(source)},
    ]))
    base_value = {
        "schema_version": "codex-surface-molecular-library/v0.1",
        "atlas_id": "atlas-test",
        "library_id": "base",
        "records": [{"molecule_id": "base-item"}],
        # This path-only field is deliberately exempt because hashing the receipt
        # would create a cycle in the library and receipt pair.
        "registration_receipt": {"path": "registration.json", "storage": "external-artifact-root"},
    }
    if container == "record":
        base_value["records"][0].update(reference)
    else:
        base_value.update(reference)
    base = tmp_path / "base.json"
    write_json(base, base_value)

    output = tmp_path / "output"
    with pytest.raises(LibraryRegistrationError, match="base artifact"):
        register_library(manifest, output, base_library=base)
    assert not output.exists()
