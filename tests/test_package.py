from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
import surface_atlas.installer as installer_module

from surface_atlas.example import create_example
from surface_atlas.installer import SkillInstallError, install_skill, uninstall_skill
from surface_atlas.report import build_report
from surface_atlas.validator import validate_workspace
from surface_atlas.workspace import WorkspaceError, initialize_atlas
from surface_atlas.schemas import COLLECTION_SCHEMAS


REPOSITORY = Path(__file__).resolve().parents[1]
SYNTHETIC = REPOSITORY / "examples" / "synthetic-atlas"


def test_documented_examples_and_skill_templates_match_packaged_resources() -> None:
    package = REPOSITORY / "src" / "surface_atlas"
    pairs = ((SYNTHETIC, package / "assets/synthetic-atlas"),
             (package / "skill/assets", package / "assets/templates"))
    for documented, bundled in pairs:
        left = {path.name: path.read_bytes() for path in documented.iterdir() if path.is_file()}
        right = {path.name: path.read_bytes() for path in bundled.iterdir() if path.is_file()}
        assert left == right, "documented examples and installable resources differ"


def test_init_preserves_quoted_backslash_and_placeholder_like_disease_text(tmp_path: Path) -> None:
    destination = tmp_path / "atlas"
    disease = 'A "quoted" disease __PROFILE__\\segment\nsecond line'
    result = initialize_atlas("quoted-atlas", destination, disease=disease)
    assert result.atlas_id == "quoted-atlas"
    plan = json.loads((destination / "atlas-plan.json").read_text(encoding="utf-8"))
    assert plan["disease"]["name"] == disease
    assert plan["resource_profile"]["name"] == "standard"
    assert validate_workspace(destination)["valid"] is True


def test_init_refuses_existing_destination(tmp_path: Path) -> None:
    destination = tmp_path / "already-there"
    destination.mkdir()
    with pytest.raises(WorkspaceError, match="refusing to overwrite"):
        initialize_atlas("safe-atlas", destination, disease="Synthetic disease")


def test_synthetic_example_validates_and_has_only_fictional_ids(tmp_path: Path) -> None:
    destination = tmp_path / "synthetic"
    result = create_example(destination)
    assert result.targets == 3
    validation = validate_workspace(destination)
    assert validation["valid"] is True, validation
    target_ids = {
        record["target_id"]
        for record in json.loads((destination / "targets.json").read_text(encoding="utf-8"))["records"]
    }
    assert target_ids == {"T-EMBER", "T-LANTERN", "T-ORBIT"}
    plan = json.loads((destination / "atlas-plan.json").read_text(encoding="utf-8"))
    assert plan["data_kind"] == "synthetic"
    library = json.loads((destination / "molecular-library.json").read_text(encoding="utf-8"))
    assert library["records"][0]["source_smiles"] is None
    structures = json.loads((destination / "structures.json").read_text(encoding="utf-8"))
    assert all(record["accession"] is None for record in structures["records"])
    all_text = "\n".join(path.read_text(encoding="utf-8") for path in destination.rglob("*") if path.is_file())
    assert "/Users/" not in all_text
    assert "/Volumes/" not in all_text
    assert "PRIVATE_CASE_MARKER" not in all_text


def test_report_builds_offline_pages_from_synthetic_example(tmp_path: Path) -> None:
    result = build_report(SYNTHETIC, output_root=tmp_path / "reports", run_id="synthetic-test")
    run_directory = Path(result["run_directory"])
    assert (run_directory / "index.html").is_file()
    assert (run_directory / "targets.html").is_file()
    assert (run_directory / "assets" / "presentation.css").is_file()
    manifest = json.loads((run_directory / "run-manifest.json").read_text(encoding="utf-8"))
    assert manifest["provider_calls"] is False
    assert manifest["external_urls_fetched"] is False
    report_text = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in run_directory.rglob("*") if path.is_file())
    assert "/Users/" not in report_text
    assert "/Volumes/" not in report_text


def test_skill_install_uninstall_is_manifest_bound_and_safe(tmp_path: Path) -> None:
    destination = tmp_path / "skill"
    installed = install_skill(destination)
    assert installed["installed"] is True
    assert (destination / "SKILL.md").is_file()
    assert (destination / ".surface-atlas-skill.json").is_file()
    repeat = install_skill(destination)
    assert repeat["already_installed"] is True

    (destination / "user-note.txt").write_text("keep me", encoding="utf-8")
    with pytest.raises(SkillInstallError, match="unmanaged"):
        uninstall_skill(destination)
    assert (destination / "user-note.txt").is_file()

    (destination / "user-note.txt").unlink()
    (destination / "SKILL.md").write_text("edited", encoding="utf-8")
    with pytest.raises(SkillInstallError, match="modified"):
        uninstall_skill(destination)
    assert destination.is_dir()

    # A new clean destination can be removed completely through the managed API.
    clean = tmp_path / "clean-skill"
    install_skill(clean)
    removed = uninstall_skill(clean)
    assert removed["removed"] is True
    assert not clean.exists()


def test_skill_uninstall_rejects_unmanaged_empty_directory(tmp_path: Path) -> None:
    destination = tmp_path / "skill"
    install_skill(destination)
    (destination / "user-directory").mkdir()
    with pytest.raises(SkillInstallError, match="unmanaged"):
        uninstall_skill(destination)
    assert (destination / "user-directory").is_dir()
    assert (destination / "SKILL.md").is_file()


def test_skill_uninstall_rejects_forged_managed_hashes(tmp_path: Path) -> None:
    destination = tmp_path / "skill"
    install_skill(destination)
    skill = destination / "SKILL.md"
    skill.write_text("unrelated user content", encoding="utf-8")
    manifest_path = destination / ".surface-atlas-skill.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for entry in manifest["managed_files"]:
        if entry["path"] == "SKILL.md":
            entry["sha256"] = hashlib.sha256(skill.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(SkillInstallError, match="different package build"):
        uninstall_skill(destination)
    assert skill.read_text(encoding="utf-8") == "unrelated user content"


def test_skill_manifest_symlink_is_rejected(tmp_path: Path) -> None:
    destination = tmp_path / "skill"
    install_skill(destination)
    manifest_path = destination / ".surface-atlas-skill.json"
    saved_manifest = tmp_path / "saved-manifest.json"
    saved_manifest.write_bytes(manifest_path.read_bytes())
    manifest_path.unlink()
    manifest_path.symlink_to(saved_manifest)

    with pytest.raises(SkillInstallError, match="must not be a symlink"):
        uninstall_skill(destination)
    assert (destination / "SKILL.md").is_file()


def test_non_utf8_skill_manifest_is_rejected_cleanly(tmp_path: Path) -> None:
    destination = tmp_path / "skill"
    install_skill(destination)
    (destination / ".surface-atlas-skill.json").write_bytes(b"\xff\xfe")
    with pytest.raises(SkillInstallError, match="invalid JSON"):
        uninstall_skill(destination)


def test_packaged_skill_symlink_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "source"
    source.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("outside", encoding="utf-8")
    (source / "SKILL.md").symlink_to(outside)
    monkeypatch.setattr(installer_module, "_skill_source", lambda: source)
    with pytest.raises(SkillInstallError, match="contain a symlink"):
        install_skill(tmp_path / "destination")
    assert not (tmp_path / "destination").exists()


def test_skill_destination_symlink_is_rejected(tmp_path: Path) -> None:
    installed = tmp_path / "installed"
    install_skill(installed)
    alias = tmp_path / "alias"
    alias.symlink_to(installed, target_is_directory=True)
    with pytest.raises(SkillInstallError, match="must not be a symlink"):
        install_skill(alias)


def test_skill_uninstall_rejects_dangling_destination_symlink(tmp_path: Path) -> None:
    destination = tmp_path / "missing-skill"
    destination.symlink_to(tmp_path / "does-not-exist", target_is_directory=True)

    with pytest.raises(SkillInstallError, match="non-directory skill destination"):
        uninstall_skill(destination)
    assert destination.is_symlink()


def test_skill_result_preserves_user_relative_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = install_skill(Path("relative-skill"))
    assert result["destination"] == "relative-skill"


def test_uninstall_failure_restores_visible_installation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "skill"
    install_skill(destination)

    def fail_remove(_path: object) -> None:
        raise PermissionError("simulated removal failure")

    monkeypatch.setattr(installer_module.shutil, "rmtree", fail_remove)
    with pytest.raises(SkillInstallError, match="could not remove"):
        uninstall_skill(destination)
    assert (destination / "SKILL.md").is_file()
    assert not list(tmp_path.glob(".surface-atlas-uninstall-*"))


def test_schema_documents_are_valid_json_and_match_workspace_versions() -> None:
    schema_dir = REPOSITORY / "schemas" / "v0.1"
    plan_schema = json.loads((schema_dir / "atlas-plan.schema.json").read_text(encoding="utf-8"))
    ledger_schema = json.loads((schema_dir / "search-ledger.schema.json").read_text(encoding="utf-8"))
    collection_schema = json.loads((schema_dir / "collection.schema.json").read_text(encoding="utf-8"))
    assert plan_schema["properties"]["schema_version"]["const"] == "codex-surface-atlas-plan/v0.1"
    assert ledger_schema["properties"]["schema_version"]["const"] == "codex-surface-search-ledger/v0.1"
    assert set(collection_schema["properties"]["schema_version"]["enum"]) == set(COLLECTION_SCHEMAS.values())
    for schema in (plan_schema, ledger_schema, collection_schema):
        Draft202012Validator.check_schema(schema)
    for path in SYNTHETIC.glob("*.json"):
        schema = plan_schema if path.name == "atlas-plan.json" else ledger_schema if path.name == "search-ledger.json" else collection_schema
        Draft202012Validator(schema).validate(json.loads(path.read_text(encoding="utf-8")))


def test_research_example_matches_schemas_and_names_the_disease(tmp_path: Path) -> None:
    example = REPOSITORY / "examples/research-case"
    schema_dir = REPOSITORY / "schemas/v0.1"
    schemas = {
        name: Draft202012Validator(json.loads((schema_dir / f"{name}.schema.json").read_text()))
        for name in ("atlas-plan", "search-ledger", "collection", "structure-snapshot")
    }
    for path in example.glob("*.json"):
        value = json.loads(path.read_text())
        if path.stem in ("atlas-plan", "search-ledger"):
            schemas[path.stem].validate(value)
        elif path.name in COLLECTION_SCHEMAS:
            schemas["collection"].validate(value)
        for record in value.get("records", []):
            for snapshot in record.get("structure_snapshots", []):
                schemas["structure-snapshot"].validate(snapshot)
    result = build_report(example, output_root=tmp_path / "reports", run_id="research-schema-test")
    directory = Path(result["run_directory"])
    disease = json.loads((example / "atlas-plan.json").read_text())["disease"]["name"]
    assert f"<h1>{disease}</h1>" in (directory / "index.html").read_text()
    assert disease in (directory / "study.html").read_text()
