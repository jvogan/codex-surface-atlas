"""Explicitly synthetic fixtures for offline intake demonstrations, never evidence."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from .research_intake import ASSAY_SCHEMA, BINDER_SCHEMA, IntakeError


def write_synthetic_research_inputs(directory: Path | str, atlas_id: str, target_id: str) -> dict[str, Path]:
    """Write a new input directory with synthetic run, return, and source artifact.

    The caller supplies an existing atlas and target identity. No atlas files are
    edited. Returned keys are binder_runs and assay_results.
    """
    root = Path(directory)
    if root.exists():
        raise IntakeError("synthetic input directory must be new")
    root.mkdir(parents=True)
    raw = b"SYNTHETIC TEST DATA ONLY. No computation or laboratory assay was performed.\nrow 1: candidate and target identity; row 2: protocol; row 3: censored IC50 >100 nM; row 4: failed negative control; row 5: missing replicate.\n"
    (root / "synthetic-source.txt").write_bytes(raw)
    artifact = {"path": "synthetic-source.txt", "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw), "storage": "workspace"}
    def src(locator):
        return {"artifact": copy.deepcopy(artifact), "locator": locator}
    def sequence_fields(seq):
        return {"sequence": seq, "sequence_sha256": hashlib.sha256(seq.encode()).hexdigest()}
    target = {"construct_id": "synthetic-target-construct", **sequence_fields("ACDEFGHIK"), "description": "Synthetic test construct; no tags or modifications; not a real protein reagent.", "modifications": [], "source": src("row 1")}
    def candidate(identifier, role, seq):
        result = {"candidate_id": identifier, "role": role, "construct_id": identifier + "-construct", **sequence_fields(seq), "evidence_class": "computational-design-hypothesis", "source": src("row 1"), "lineage": [], "observations": [{"observation_id": identifier + "-seed-7", "seed": 7, "status": "scored", "metrics": {"synthetic_score": 0.1}, "reason": "Synthetic test score only", "source": src("row 2")}], "promotion": {"decision": "not-promoted", "rationale": "Synthetic negative control failed", "source": src("row 4")}}
        if role != "candidate":
            result.update(acceptance_status="failed", acceptance_rule="Synthetic control rule deliberately fails")
        return result
    designed = candidate("synthetic-candidate", "candidate", "ACDEFG")
    run = {"run_id": "synthetic-run-1", "campaign_id": "synthetic-campaign", "target_id": target_id, "target_construct": target, "generator": {"name": "synthetic-generator", "version": "test-1", "source": src("row 2")}, "evaluation_protocol": {"id": "synthetic-protocol", "version": "test-1", "source": src("row 2")}, "source": src("row 1"), "stages": [{"name": "screen", "status": "completed", "reason": "Synthetic test only"}, {"name": "confirmation", "status": "not-run", "reason": "Synthetic failed control blocks advancement"}], "controls_status": "failed", "candidates": [designed, candidate("synthetic-negative-control", "negative-control", "GFEDCA")]}
    run["generator"]["seed"] = 7
    for item in run["candidates"]:
        item["description"] = "Synthetic unmodified test construct"
        item["modifications"] = []
    runs = {"schema_version": BINDER_SCHEMA, "atlas_id": atlas_id, "data_status": "synthetic", "records": [run]}
    assay = {"assay_result_id": "synthetic-assay-1", "experiment_id": "synthetic-experiment", "candidate_run_id": run["run_id"], "candidate_id": designed["candidate_id"], "campaign_id": run["campaign_id"], "target_id": target_id, "evidence_class": "laboratory-assay-observation", "candidate_construct": {"construct_id": designed["construct_id"], **sequence_fields(designed["sequence"]), "description": "Synthetic unmodified test construct", "modifications": [], "source": src("row 1")}, "target_construct": copy.deepcopy(target), "identity_source": src("row 1"), "method": {"name": "Synthetic laboratory intake test", "version": "test-1", "conditions": "No experiment performed. Synthetic units and bound exercise preservation only.", "source": src("row 2")}, "endpoint": "IC50", "reading": {"status": "measured", "value": 100.0, "relation": ">", "unit": "nM", "source": src("row 3")}, "replicates": [{"replicate_id": "synthetic-replicate-missing", "biological_sample_id": None, "technical_replicate_id": "synthetic-well-1", "reading": {"status": "not-measured", "value": None, "relation": None, "unit": "nM", "reason": "Synthetic missing reading", "source": src("row 5")}}], "controls": [{"control_id": "synthetic-assay-negative", "role": "negative", "description": "Synthetic failed control; no real measurement", "acceptance_rule": "Synthetic rule deliberately fails", "acceptance_status": "failed", "result_record_id": None, "source": src("row 4")}], "aggregation": None}
    assay["method"]["family"] = "other-laboratory-assay"
    assays = {"schema_version": ASSAY_SCHEMA, "atlas_id": atlas_id, "data_status": "synthetic", "records": [assay]}
    paths = {"binder_runs": root / "binder-runs.json", "assay_results": root / "assay-results.json"}
    for key, data in (("binder_runs", runs), ("assay_results", assays)):
        paths[key].write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return paths
