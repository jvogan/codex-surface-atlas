from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


INITIALIZER = "init"
BUILDER = "report"

def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def run_json(*arguments: object) -> tuple[subprocess.CompletedProcess[str], dict]:
    result = subprocess.run(
        [sys.executable, "-m", "surface_atlas", *(str(argument) for argument in arguments)],
        check=False,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout) if result.stdout.strip().startswith("{") else {}
    return result, payload


class OfflineReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "atlas"
        result, payload = run_json(
            INITIALIZER,
            "report-test",
            self.root,
            "--disease",
            "test disease",
            "--json",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(payload["research_target_cap"], None)
        self.output_root = Path(self.temporary.name) / "results"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def build(self, run_id: str = "20260904T010000Z") -> tuple[subprocess.CompletedProcess[str], dict]:
        return run_json(
            BUILDER,
            self.root,
            "--output-root",
            self.output_root,
            "--run-id",
            run_id,
            "--json",
        )

    def test_empty_workspace_builds_offline_report_with_clear_empty_states(self) -> None:
        result, payload = self.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        run_dir = Path(payload["run_directory"])
        self.assertEqual(payload["provider_calls"], False)
        self.assertEqual(payload["external_urls_fetched"], False)
        for filename in (
            "index.html",
            "study.html",
            "targets.html",
            "treatments.html",
            "molecular-library.html",
            "structures.html",
            "binders.html",
            "design-sources.html",
            "run-manifest.json",
            "assets/report.css",
            "assets/report.js",
            "data/atlas.json",
            "data/targets.csv",
            "data/molecular-library.json",
            "data/molecular-library.csv",
            "data/screening-results.json",
            "data/screening-results.csv",
            "data/binder-controls.json",
            "data/binder-campaigns.json",
        ):
            self.assertTrue((run_dir / filename).is_file(), filename)
        targets_html = (run_dir / "targets.html").read_text(encoding="utf-8")
        self.assertIn("No target records are present", targets_html)
        self.assertIn("Targets", targets_html)
        css = (run_dir / "assets/report.css").read_text(encoding="utf-8")
        self.assertIn("body {", css)
        self.assertIn("background: #ffffff", css)
        self.assertIn("--panel: #ffffff", css)
        self.assertNotIn("gradient(", css)
        self.assertNotIn("backdrop-filter", css)
        script = (run_dir / "assets/report.js").read_text(encoding="utf-8")
        self.assertIn('var queryKey = table.id + "-q"', script)
        self.assertIn("window.history.replaceState", script)
        all_report_text = "".join(path.read_text(encoding="utf-8") for path in run_dir.rglob("*.html"))
        self.assertNotRegex(all_report_text, r"<script[^>]+src=\"https?://")
        self.assertIn('<meta name="theme-color" content="#FFFFFF">', all_report_text)
        self.assertTrue(load(run_dir / "run-manifest.json")["provider_calls"] is False)

    def test_report_does_not_publish_source_workspace_basename(self) -> None:
        private_basename = "internal-workspace-marker"
        moved_root = self.root.with_name(private_basename)
        self.root.rename(moved_root)
        self.root = moved_root

        result, payload = self.build("portable-report")
        self.assertEqual(result.returncode, 0, result.stderr)
        run_dir = Path(payload["run_directory"])
        manifest = load(run_dir / "run-manifest.json")
        self.assertNotIn("source_workspace_name", manifest)
        marker = private_basename.encode("utf-8")
        for path in run_dir.rglob("*"):
            if path.is_file():
                self.assertNotIn(marker, path.read_bytes(), path.relative_to(run_dir).as_posix())

    def test_populated_report_links_dossiers_structures_and_binders(self) -> None:
        targets = load(self.root / "targets.json")
        targets["records"] = [
            {
                "target_id": "T-CDH17",
                "preferred_name": "CDH17",
                "entity_class": "adhesion molecule",
                "cell_owner": "malignant epithelial",
                "surface_evidence": {
                    "decision": "retained",
                    "reason_code": "positive-surfaceome-evidence",
                    "tcsa_global_membership": True,
                    "reviewed_uniprot": {"gpi_anchored": True},
                    "reasons": ["Complete structured evidence stays in the dossier and export."],
                },
                "disease_evidence": "fictional example cohort",
                "normal_tissue_risk": "gut epithelium",
                "structure_tier": "structure-a",
                "evidence_score": {"score": 73.78, "maximum": 100, "components": [{"component": "surface", "points": 40}]},
                "claim_ceiling": "observed evidence",
                "source_refs": [{"title": "Example source", "url": "https://example.org/source"}],
            }
        ]
        save(self.root / "targets.json", targets)

        discovered = load(self.root / "discovered-entities.json")
        discovered["records"] = [{"entity_id": "E-CDH17", "surface_disposition": "surface-target", "target_id": "T-CDH17"}]
        save(self.root / "discovered-entities.json", discovered)

        interventions = load(self.root / "interventions.json")
        interventions["records"] = [
            {
                "intervention_id": "I-001",
                "name": "Example antibody",
                "target_id": "T-CDH17",
                "action": "binding",
                "molecular_format": "antibody",
                "status": "research",
                "claim_ceiling": "inferred from literature",
            }
        ]
        save(self.root / "interventions.json", interventions)

        molecular_library = load(self.root / "molecular-library.json")
        molecular_library["records"] = [
            {
                "molecule_id": "M-001",
                "name": "Reference ligand",
                "panel": "reference-ligand",
                "molecular_class": "small molecule",
                "source_class": "curated-known-interactor",
                "identity_state": "resolved",
                "pubchem_cid": 12345,
                "source_smiles": "CCO",
                "known_target_ids": ["T-CDH17"],
                "known_interaction_refs": [{"title": "Measured interaction", "url": "https://example.org/interaction"}],
                "chemistry_flags": ["tautomer-review"],
                "preparation_state": "neutralized",
            },
            {
                "molecule_id": "M-002",
                "name": "Natural product input",
                "panel": "natural-product",
                "molecular_class": "polyphenol",
                "identity_state": "resolved",
                "source_smiles": "C1=CC=CC=C1",
                "target_lookup_intentions": ["T-CDH17"],
                "chemistry_flags": ["assay-interference-review"],
                "preparation_flags": ["protonation-review"],
            },
            {
                "molecule_id": "M-003",
                "name": "User peptide input",
                "panel": "user-supplied",
                "molecular_format": "modified peptide",
                "sequence": "ACDEFGHIK",
                "modifications": ["N-terminal acetylation"],
                "target_lookup_intentions": ["T-CDH17"],
            },
            {
                "molecule_id": "M-004",
                "name": "Generated hypothesis",
                "panel": "generated",
                "molecular_class": "small molecule",
                "source_smiles": "C=O",
                "identity_state": "proposed",
            },
        ]
        save(self.root / "molecular-library.json", molecular_library)

        screening_results = load(self.root / "screening-results.json")
        screening_results["records"] = [
            {
                "screening_id": "SCR-001",
                "molecule_id": "M-002",
                "target_id": "T-CDH17",
                "site": "extracellular loop",
                "route": "DiffDock",
                "model_version": "diffdock-test-1",
                "pose_id": "pose-01",
                "pose_score": -7.2,
                "confidence": 0.61,
                "seed_agreement": {
                    "state": "concordant",
                    "successful_comparable_seed_count": 3,
                    "top_score_span_kcal_mol": 0.218,
                },
                "control_status": "negative control passed",
                "execution_state": "executed",
                "failure_reason": None,
                "evidence_class": "computational-screening-hypothesis",
            },
            {
                "screening_id": "SCR-002",
                "molecule_id": "M-003",
                "target_id": "T-CDH17",
                "site": "blind extracellular construct",
                "route": "co-fold",
                "model_version": "cofold-test-1",
                "pose": "none returned",
                "confidence": None,
                "control_status": "control failed",
                "execution_state": "failed",
                "failure_reason": "No valid complex returned",
                "evidence_class": "computational-screening-hypothesis",
            },
        ]
        save(self.root / "screening-results.json", screening_results)

        structures = load(self.root / "structures.json")
        render_path = self.root / "media" / "cdh17.svg"
        render_path.parent.mkdir(exist_ok=True)
        render_path.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20"></svg>\n', encoding="utf-8")
        render_hash = hashlib.sha256(render_path.read_bytes()).hexdigest()
        movie_path = self.root / "media" / "cdh17.mp4"
        movie_path.write_bytes(b"test-mp4")
        movie_hash = hashlib.sha256(movie_path.read_bytes()).hexdigest()
        structures["records"] = [
            {
                "structure_id": "S-001",
                "target_id": "T-CDH17",
                "pdb_id": "6ULM",
                "kind": "experimental apo",
                "entry": {"resolution_angstrom": [2.8]},
                "chains": [
                    {"role": "target", "label": "CDH17"},
                    {"role": "binder", "label": "Example minibinder"},
                ],
                "claim_ceiling": "experimental structure",
                "artifacts": [
                    {"path": "media/cdh17.svg", "sha256": render_hash, "bytes": render_path.stat().st_size},
                    {"path": "media/cdh17.mp4", "sha256": movie_hash, "bytes": movie_path.stat().st_size, "media_type": "video/mp4"},
                ],
            }
        ]
        save(self.root / "structures.json", structures)

        opportunities = load(self.root / "opportunities.json")
        opportunities["records"] = [
            {
                "opportunity_id": "O-001",
                "target_id": "T-CDH17",
                "molecular_job": "payload delivery",
                "modality": "miniprotein binder",
                "binding_site": "extracellular loop",
                "rationale": "Surface access and internalization evidence are recorded.",
                "leading_risk": "normal gut exposure",
                "next_step": "review construct and controls",
                "claim_ceiling": "proposed design",
            }
        ]
        save(self.root / "opportunities.json", opportunities)

        capabilities = load(self.root / "capabilities.json")
        capabilities["records"] = [{"capability_id": "C-001", "name": "Structure viewer", "state": "visible", "version": "0.1", "claim_ceiling": "observed capability"}]
        save(self.root / "capabilities.json", capabilities)

        binders = {
            "schema_version": "codex-surface-binder-collection/v0.1",
            "atlas_id": "report-test",
            "campaign_id": "CAMP-SYNTHETIC-001",
            "request_id": "REQ-SYNTHETIC-001",
            "target_id": "T-CDH17",
            "execution_state": "complete",
            "control_calibration_status": "passed",
            "counts": {
                "validated_backbones": 8,
                "designed_candidates": 1,
                "controls": 1,
                "promoted_candidates": 1,
                "cofold_observations": 3,
            },
            "records": [
                {
                    "binder_id": "B-001",
                    "candidate_name": "CDH17 loop binder 01",
                    "target_id": "T-CDH17",
                    "molecular_job": "payload delivery",
                    "sequence": "ACDEFGHIKLMNPQRSTVWY",
                    "sequence_length": 20,
                    "ranking_status": "promoted-by-recorded-decision",
                    "promotion": {"decision": "promoted", "rationale": "Recorded finalist decision"},
                    "aggregate_metrics": {
                        "ipsae_min_median": 0.812,
                        "target_contact_recall_median": 0.734,
                        "scored_observation_count": 2,
                        "failed_observation_count": 0,
                    },
                    "cofold_observations": [
                        {
                            "status": "scored",
                            "artifacts": [
                                {
                                    "role": "predicted-complex",
                                    "path": "media/binder-complex.cif",
                                    "sha256": "BINDER_HASH",
                                    "bytes": "BINDER_BYTES",
                                }
                            ],
                        },
                        {"status": "scored", "artifacts": []},
                    ],
                    "claim_ceiling": "computational-design-hypothesis",
                }
            ],
            "controls": [
                {
                    "candidate_id": "control-positive-synthetic-chain-c",
                    "name": "Deposited positive control",
                    "class": "deposited-positive",
                    "target_id": "T-CDH17",
                    "sequence": "ACDEFGHIK",
                    "aggregate_metrics": {
                        "ipsae_min_median": 0.9,
                        "target_contact_recall_median": 0.85,
                    },
                    "cofold_observations": [{"status": "scored", "artifacts": []}],
                    "claim_ceiling": "computational-design-hypothesis",
                }
            ],
        }
        binder_complex = self.root / "media" / "binder-complex.cif"
        binder_complex.write_text("data_BINDER\n#\n", encoding="utf-8")
        binder_artifact = binders["records"][0]["cofold_observations"][0]["artifacts"][0]
        binder_artifact["sha256"] = hashlib.sha256(binder_complex.read_bytes()).hexdigest()
        binder_artifact["bytes"] = binder_complex.stat().st_size
        save(self.root / "binders.json", binders)

        result, payload = self.build("20260904T010001Z")
        self.assertEqual(result.returncode, 0, result.stderr)
        run_dir = Path(payload["run_directory"])
        self.assertEqual(payload["targets"], 1)
        self.assertEqual(payload["structures"], 1)
        self.assertEqual(payload["designed_binders"], 1)
        self.assertTrue((run_dir / "data/molecular-library.csv").is_file())
        self.assertTrue((run_dir / "data/screening-results.csv").is_file())
        self.assertIn("0.218 kcal/mol span", (run_dir / "molecular-library.html").read_text(encoding="utf-8"))
        targets_text = (run_dir / "targets.html").read_text(encoding="utf-8")
        self.assertIn("Retained · TCSA surfaceome + UniProt GPI anchor", targets_text)
        self.assertIn("73.78 / 100", targets_text)
        self.assertNotIn("{&quot;decision&quot;", targets_text)
        molecule_text = (run_dir / "molecular-library.html").read_text(encoding="utf-8")
        self.assertIn("Natural product", molecule_text)
        self.assertIn("Reference ligand", molecule_text)
        self.assertIn("User-supplied", molecule_text)
        self.assertIn("Generated", molecule_text)
        self.assertIn("Measured interaction", molecule_text)
        self.assertIn("Target lookup intentions", molecule_text)
        self.assertIn("DiffDock", molecule_text)
        self.assertIn("negative control passed", molecule_text)
        self.assertIn("computational-screening-hypothesis", molecule_text)
        self.assertIn("data-page-size=\"50\"", molecule_text)
        self.assertIn('aria-live="polite"', molecule_text)
        self.assertNotIn("known binder", molecule_text.casefold())
        target_page = next(run_dir.glob("target-*.html"))
        target_text = target_page.read_text(encoding="utf-8")
        self.assertIn("CDH17", target_text)
        self.assertIn("Example antibody", target_text)
        self.assertIn("6ULM", target_text)
        self.assertIn("Known molecule interactions", target_text)
        self.assertIn("Molecule lookup intentions", target_text)
        self.assertIn("SCR-001", target_text)
        self.assertIn("Structured surface evidence", target_text)
        self.assertIn('"components"', target_text.replace("&quot;", '"'))
        structures_text = (run_dir / "structures.html").read_text(encoding="utf-8")
        self.assertIn("data/artifacts/media/cdh17.svg", structures_text)
        self.assertIn("data/artifacts/media/cdh17.mp4", structures_text)
        self.assertIn("<img", structures_text)
        self.assertIn('<video controls preload="metadata"', structures_text)
        self.assertIn("playsinline", structures_text)
        self.assertIn('width="1200" height="900"', structures_text)
        self.assertNotIn("autoplay", structures_text)
        self.assertIn("Example minibinder", structures_text)
        self.assertIn("2.8 Å", structures_text)
        binders_text = (run_dir / "binders.html").read_text(encoding="utf-8")
        self.assertIn("CDH17 loop binder 01", binders_text)
        self.assertIn("ACDEFGHIKLMNPQRSTVWY", binders_text)
        self.assertIn("Independent validation", binders_text)
        self.assertIn("0.812", binders_text)
        self.assertIn("0.734", binders_text)
        self.assertIn("Recorded finalist decision", binders_text)
        self.assertIn("Deposited positive control", binders_text)
        self.assertIn("Control calibration</dt><dd>passed", binders_text)
        self.assertIn("data/artifacts/media/binder-complex.cif", binders_text)
        self.assertTrue((run_dir / "data" / "artifacts" / "media" / "binder-complex.cif").is_file())
        self.assertEqual(len(load(run_dir / "data" / "binder-controls.json")["records"]), 1)
        self.assertEqual(len(load(run_dir / "data" / "binder-campaigns.json")["records"]), 1)
        design_text = (run_dir / "design-sources.html").read_text(encoding="utf-8")
        self.assertIn("payload delivery", design_text)
        self.assertIn("Structure viewer", design_text)

    def test_target_table_keeps_all_records_and_adds_pagination(self) -> None:
        targets = load(self.root / "targets.json")
        targets["records"] = [
            {
                "target_id": f"T-{index:03d}",
                "preferred_name": f"Target {index:03d}",
                "structure_tier": "retained-unmodeled",
                "surface_evidence": "recorded",
            }
            for index in range(55)
        ]
        save(self.root / "targets.json", targets)
        result, payload = self.build("20260904T010002Z")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(payload["targets"], 55)
        run_dir = Path(payload["run_directory"])
        targets_html = (run_dir / "targets.html").read_text(encoding="utf-8")
        self.assertEqual(targets_html.count('class="table-primary"'), 55)
        self.assertIn('data-page-size="50"', targets_html)
        self.assertIn("Previous", targets_html)
        self.assertIn("Next", targets_html)

    def test_molecule_library_supports_large_inventory_pagination(self) -> None:
        library = load(self.root / "molecular-library.json")
        library["records"] = [
            {
                "molecule_id": f"M-{index:04d}",
                "name": f"Member {index:04d}",
                "panel": "natural-product" if index % 2 else "user-supplied",
                "source_smiles": "CCO",
                "identity_state": "resolved",
            }
            for index in range(125)
        ]
        save(self.root / "molecular-library.json", library)
        result, payload = self.build("20260904T010005Z")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(payload["targets"], 0)
        run_dir = Path(payload["run_directory"])
        library_html = (run_dir / "molecular-library.html").read_text(encoding="utf-8")
        self.assertEqual(library_html.count('class="table-primary"'), 125)
        self.assertIn('data-page-size="50"', library_html)
        self.assertIn('data-table-filter="molecule-library"', library_html)
        self.assertIn('data-table-next="molecule-library"', library_html)
        exported = load(run_dir / "data/molecular-library.json")
        self.assertEqual(len(exported["records"]), 125)

    def test_builder_refuses_overwrite_and_missing_plan(self) -> None:
        result, _ = self.build("20260904T010003Z")
        self.assertEqual(result.returncode, 0, result.stderr)
        result, _ = self.build("20260904T010003Z")
        self.assertEqual(result.returncode, 1)
        self.assertIn("refusing to overwrite", result.stderr)

        missing = Path(self.temporary.name) / "missing"
        missing.mkdir()
        result, _ = run_json(BUILDER, missing, "--output-root", self.output_root, "--run-id", "20260904T010004Z", "--json")
        self.assertEqual(result.returncode, 1)
        self.assertIn("required atlas file is missing", result.stderr)

    def test_report_derives_executed_evidence_state_and_copies_external_coordinates(self) -> None:
        plan = load(self.root / "atlas-plan.json")
        plan["external_work"]["compute_authorized"] = True
        plan["external_work"]["experimental_submission_authorized"] = False
        save(self.root / "atlas-plan.json", plan)
        save(self.root / "query-plan.json", {"schema_version": "test/query-plan", "source_registry": [{"source": "PubMed"}]})

        discovered = load(self.root / "discovered-entities.json")
        discovered["records"] = [
            {"entity_id": "E-1", "surface_disposition": "surface-target", "target_id": "T-1"},
            {"entity_id": "E-2", "surface_disposition": "unresolved"},
        ]
        save(self.root / "discovered-entities.json", discovered)
        targets = load(self.root / "targets.json")
        targets["records"] = [{"target_id": "T-1", "preferred_name": "Target 1", "structure_tier": "structure-a"}]
        save(self.root / "targets.json", targets)

        external = Path(self.temporary.name) / "external-artifacts"
        coordinate = external / "coordinates" / "rcsb" / "1abc.cif"
        coordinate.parent.mkdir(parents=True)
        coordinate.write_text("data_1ABC\n#\n", encoding="utf-8")
        coordinate_hash = hashlib.sha256(coordinate.read_bytes()).hexdigest()
        save(
            self.root / ".surface-atlas-local.json",
            {"schema_version": "test/local-storage", "artifact_root": str(external)},
        )
        receipt_dir = external / "receipts"
        receipt_dir.mkdir()
        save(
            receipt_dir / "literature.receipt.json",
            {
                "schema_version": "codex-surface-literature-compiler-receipt/v0.1",
                "generated_at": "2026-09-04T01:00:00Z",
                "counts": {
                    "unique_record_count": 2570,
                    "emitted_membership_count": 2616,
                    "duplicate_query_membership_count": 46,
                    "missing_or_merged_pmid_count": 24,
                },
            },
        )
        save(
            receipt_dir / "reconciliation.receipt.json",
            {
                "schema_version": "codex-surface-target-reconciliation-receipt/v0.1",
                "generated_at": "2026-09-04T02:00:00Z",
                "discovered_entity_count": 2,
                "surface_target_count": 1,
                "excluded_count": 0,
                "unresolved_count": 1,
                "disposition_accounting_complete": True,
            },
        )
        structures = load(self.root / "structures.json")
        structures["records"] = [
            {
                "structure_id": "S-1ABC",
                "target_id": "T-1",
                "accession": "1ABC",
                "source_database": "RCSB Protein Data Bank",
                "retrieval_date": "2026-09-04",
                "source_coordinate": {
                    "path": "coordinates/rcsb/1abc.cif",
                    "bytes": coordinate.stat().st_size,
                    "sha256": coordinate_hash,
                    "storage": "external-artifact-root",
                },
            }
        ]
        save(self.root / "structures.json", structures)

        result, payload = self.build("20260904T010006Z")
        self.assertEqual(result.returncode, 0, result.stderr)
        run_dir = Path(payload["run_directory"])
        study = (run_dir / "study.html").read_text(encoding="utf-8")
        self.assertIn("Evidence and structure atlas executed", study)
        self.assertIn("Searched in-scope target census", study)
        self.assertIn("Unique literature records", study)
        self.assertIn("2,570", study)
        self.assertIn("External compute authorized</dt><dd>Yes", study)
        self.assertIn("Experimental submission authorized</dt><dd>No", study)
        self.assertNotIn(str(external), study)
        self.assertTrue((run_dir / "data" / "artifacts" / "coordinates" / "rcsb" / "1abc.cif").is_file())
        structures_html = (run_dir / "structures.html").read_text(encoding="utf-8")
        self.assertIn("data/artifacts/coordinates/rcsb/1abc.cif", structures_html)
        derived_plan = load(run_dir / "data" / "atlas-plan.json")
        derived_stages = {item["stage_id"]: item for item in derived_plan["stages"]}
        self.assertEqual(derived_stages["G2"]["state"], "complete")
        self.assertEqual(derived_stages["G6"]["state"], "complete")
        self.assertEqual(derived_stages["G10"]["state"], "in-progress")
        self.assertNotIn("external-work-not-authorized", derived_stages["G10"].get("blocked_by", []))
        derived_ledger = load(run_dir / "data" / "search-ledger.json")
        self.assertEqual(derived_ledger["coverage_state"], "complete_within_recorded_scope")
        self.assertTrue(derived_ledger["_report_state"]["census_accounting_validated"])

    def test_report_rejects_external_artifact_that_fails_registered_integrity(self) -> None:
        external = Path(self.temporary.name) / "bad-external-artifacts"
        coordinate = external / "coordinates" / "rcsb" / "bad.cif"
        coordinate.parent.mkdir(parents=True)
        coordinate.write_text("data_BAD\n#\n", encoding="utf-8")
        save(self.root / ".surface-atlas-local.json", {"artifact_root": str(external)})
        structures = load(self.root / "structures.json")
        structures["records"] = [
            {
                "structure_id": "S-BAD",
                "source_coordinate": {
                    "path": "coordinates/rcsb/bad.cif",
                    "bytes": coordinate.stat().st_size,
                    "sha256": "0" * 64,
                    "storage": "external-artifact-root",
                },
            }
        ]
        save(self.root / "structures.json", structures)
        result, _payload = self.build("20260904T010007Z")
        self.assertEqual(result.returncode, 1)
        self.assertIn("artifact integrity check failed", result.stderr)


if __name__ == "__main__":
    unittest.main()
