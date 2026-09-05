"""Preserve source details in structure and screening report views."""
import json
from pathlib import Path

from surface_atlas.report_builder import screening_pose_text, structure_resolution


EXAMPLE = Path(__file__).resolve().parents[1] / "examples/research-case"


def test_deposited_resolutions_match_the_packaged_coordinate_fields():
    records = json.loads((EXAMPLE / "structures.json").read_text())["records"]
    for record in records:
        field = record.get("resolution_source_field")
        if not field:
            continue
        coordinates = next(a for a in record["artifacts"] if a["path"].endswith(".cif"))
        line = next(line for line in (EXAMPLE / coordinates["path"]).read_text().splitlines()
                    if line.startswith(field + " "))
        assert record["resolution_angstrom"] == float(line.split()[1])
        assert structure_resolution(record).endswith(" Å")


def test_full_screening_table_links_the_saved_pose_with_its_own_context():
    record = json.loads((EXAMPLE / "screening-results.json").read_text())["records"][0]
    path = record["pose_artifact"]["path"]
    html = screening_pose_text(record, {path: "data/artifacts/pose.sdf"})
    assert 'href="data/artifacts/pose.sdf"' in html
    assert "NP011-seed41-mode1" in html
    assert "Seed 11" in html
    assert "-11.74094 kcal/mol" in html
    assert "sha256" not in html
