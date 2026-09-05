import copy
import json

from surface_atlas.report import build_report
from surface_atlas.workspace import initialize_atlas


def test_synthetic_report_is_labeled_on_every_page_and_does_not_promote_stages(tmp_path):
    atlas = tmp_path / "atlas"
    initialize_atlas("illustrative-atlas", atlas, disease="An invented example")
    plan_file = atlas / "atlas-plan.json"
    plan = json.loads(plan_file.read_text())
    plan["data_kind"] = "synthetic"
    stages = copy.deepcopy(plan["stages"])
    plan_file.write_text(json.dumps(plan))
    result = build_report(atlas, output_root=tmp_path / "reports", run_id="example")
    from pathlib import Path
    output = Path(result["run_directory"])
    for page in output.glob("*.html"):
        text = page.read_text()
        assert 'class="example-notice"' in text
        assert "All targets and records are invented" in text
        assert "no research or model execution" in text
    exported = json.loads((output / "data" / "atlas-plan.json").read_text())
    assert exported["stages"] == stages


def test_planned_screening_record_does_not_claim_design_execution(tmp_path):
    atlas = tmp_path / "atlas"
    initialize_atlas("planned-atlas", atlas, disease="A research question")
    screen_path = atlas / "screening-results.json"
    screen = json.loads(screen_path.read_text())
    screen["records"] = [{"screening_result_id": "planned-01", "execution_state": "planned"}]
    screen_path.write_text(json.dumps(screen))
    result = build_report(atlas, output_root=tmp_path / "reports", run_id="planned")
    from pathlib import Path
    text = Path(result["index"]).read_text()
    assert "Design results and atlas build executed" not in text
    assert "Atlas with screening or design records" in text
