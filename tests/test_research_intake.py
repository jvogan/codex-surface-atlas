"""Every generated record in this module is explicitly synthetic test data."""
import copy
import hashlib
import json
import shutil
from html.parser import HTMLParser
from pathlib import Path

import jsonschema
import pytest

from surface_atlas.research_demo import write_synthetic_research_inputs
from surface_atlas.research_intake import (
    IntakeError, import_assays, import_binder_runs, load_json, render_assays,
    render_campaigns, validate_assays, validate_binder_runs,
    validate_optional_research,
)


@pytest.fixture
def inputs(tmp_path):
    atlas = tmp_path / "atlas"
    atlas.mkdir()
    (atlas / "atlas-plan.json").write_text(json.dumps({"atlas_id": "synthetic-atlas"}))
    (atlas / "targets.json").write_text(json.dumps({"records": [{"target_id": "synthetic-target"}]}))
    paths = write_synthetic_research_inputs(tmp_path / "inputs", "synthetic-atlas", "synthetic-target")
    return atlas, paths


def check_binders(value, paths):
    validate_binder_runs(value, paths["binder_runs"].parent, "synthetic-atlas", {"synthetic-target"})


def test_portable_round_trip_preserves_failures_and_inequalities(inputs, tmp_path):
    atlas, paths = inputs
    bundle = tmp_path / "binder-bundle"
    runs = import_binder_runs([paths["binder_runs"]], atlas, bundle)
    shutil.copytree(bundle, atlas, dirs_exist_ok=True)
    assays = import_assays(paths["assay_results"], atlas, tmp_path / "assay-bundle")
    shutil.copytree(tmp_path / "assay-bundle", atlas, dirs_exist_ok=True)
    shutil.rmtree(paths["binder_runs"].parent)
    shutil.rmtree(bundle)
    assert validate_optional_research(atlas, "synthetic-atlas") == []
    assert runs["records"][0]["stages"][1]["status"] == "not-run"
    assert runs["records"][0]["controls_status"] == "failed"
    assay = assays["records"][0]
    assert assay["endpoint"] == "IC50"
    assert assay["reading"]["relation"] == ">"
    assert assay["replicates"][0]["reading"]["value"] is None
    assert assay["controls"][0]["acceptance_status"] == "failed"
    assert "SYNTHETIC TEST DATA" in render_campaigns(runs)
    assert "SYNTHETIC TEST DATA" in render_assays(assays)


@pytest.mark.parametrize("mutation,match", [
    (lambda r: r.update(controls_status="passed"), "passed controls"),
    (lambda r: r["candidates"][0]["promotion"].update(decision="promoted"), "promotion requires passed"),
    (lambda r: r["candidates"][0].update(sequence_sha256="0" * 64), "hash mismatch"),
    (lambda r: r["candidates"].append(copy.deepcopy(r["candidates"][0])), "duplicate candidate_id"),
    (lambda r: r["candidates"][0]["observations"].append(copy.deepcopy(r["candidates"][0]["observations"][0])), "duplicate observation_id"),
    (lambda r: r["candidates"][0]["observations"][0].update(status="failed"), "cannot carry scores"),
    (lambda r: r["candidates"][0]["observations"][0].update(seed=True), "integer observation seed"),
    (lambda r: r["candidates"][0]["observations"][0]["metrics"].update(score=float("nan")), "finite number"),
    (lambda r: r["generator"].update(seed=None), "seed_gap"),
    (lambda r: r.update(target_id="unknown"), "unknown target"),
    (lambda r: r["source"].update(locator=""), "locator"),
    (lambda r: r["source"]["artifact"].update(bytes=True), "bytes"),
    (lambda r: r["source"]["artifact"].update(path="../secret"), "relative POSIX"),
    (lambda r: r["source"]["artifact"].update(path="/etc/passwd"), "relative POSIX"),
    (lambda r: r["source"]["artifact"].update(sha256="0" * 64), "integrity mismatch"),
])
def test_reject_unsafe_binder_records(inputs, mutation, match):
    _, paths = inputs
    value = load_json(paths["binder_runs"])
    mutation(value["records"][0])
    with pytest.raises(IntakeError, match=match):
        check_binders(value, paths)


@pytest.mark.parametrize("mutation,match", [
    (lambda r: r.update(candidate_run_id="unknown"), "exact run_id"),
    (lambda r: r["candidate_construct"].update(construct_id="different"), "exact construct"),
    (lambda r: r["target_construct"].update(construct_id="different"), "exact construct"),
    (lambda r: r["candidate_construct"].update(modifications=["PEGylation"]), "modification mismatch"),
    (lambda r: r.update(endpoint="iptm"), "unsupported laboratory endpoint"),
    (lambda r: r["method"].update(family="cofold-prediction"), "physical laboratory"),
    (lambda r: r["reading"].update(unit="kcal/mol"), "incompatible"),
    (lambda r: r["reading"].update(value=float("inf")), "finite numeric"),
    (lambda r: r["reading"].update(value=True), "finite numeric"),
    (lambda r: r["reading"].update(relation="approximately"), "relation"),
    (lambda r: r["reading"].update(status="failed"), "explicit null"),
    (lambda r: r.update(replicates=None), "replicate_gap"),
    (lambda r: r.update(controls=[]), "nonempty array"),
    (lambda r: r["controls"][0].update(result_record_id="unknown"), "must resolve"),
    (lambda r: r["controls"][0].update(result_record_id=r["assay_result_id"]), "itself"),
])
def test_reject_unsafe_assays(inputs, mutation, match):
    _, paths = inputs
    runs, value = load_json(paths["binder_runs"]), load_json(paths["assay_results"])
    mutation(value["records"][0])
    with pytest.raises(IntakeError, match=match):
        validate_assays(value, paths["assay_results"].parent, "synthetic-atlas", {"synthetic-target"}, runs)


def test_independent_runs_never_pool_scores_and_reject_duplicate_runs(inputs, tmp_path):
    atlas, paths = inputs
    second = load_json(paths["binder_runs"])
    second["records"][0]["run_id"] = "synthetic-run-2"
    second["records"][0]["evaluation_protocol"]["version"] = "different-version"
    second["records"][0]["candidates"][0]["observations"][0]["metrics"]["synthetic_score"] = 999
    other = paths["binder_runs"].with_name("second.json")
    other.write_text(json.dumps(second))
    result = import_binder_runs([paths["binder_runs"], other], atlas, tmp_path / "combined")
    assert [r["candidates"][0]["observations"][0]["metrics"]["synthetic_score"] for r in result["records"]] == [0.1, 999]
    with pytest.raises(IntakeError, match="duplicate run_id"):
        import_binder_runs([other, other], atlas)


def test_never_overwrites_output(inputs, tmp_path):
    atlas, paths = inputs
    out = tmp_path / "existing"
    out.mkdir()
    marker = out / "keep.txt"
    marker.write_text("keep")
    with pytest.raises(IntakeError, match="never overwritten"):
        import_binder_runs([paths["binder_runs"]], atlas, out)
    assert marker.read_text() == "keep"


def test_symlink_escape_is_rejected(inputs, tmp_path):
    _, paths = inputs
    path = paths["binder_runs"].parent / "synthetic-source.txt"
    outside = tmp_path / "outside.txt"
    path.rename(outside)
    path.symlink_to(outside)
    with pytest.raises(IntakeError, match="symlink"):
        check_binders(load_json(paths["binder_runs"]), paths)


@pytest.mark.parametrize("raw", ['{"x":NaN}', '{"x":Infinity}', '{"x":1e999}', '{"x":1,"x":2}', '[]'])
def test_strict_json(inputs, raw):
    _, paths = inputs
    path = paths["binder_runs"].parent / "invalid.json"
    path.write_text(raw)
    with pytest.raises(IntakeError):
        load_json(path)


def test_schema_shapes(inputs):
    _, paths = inputs
    schema_root = Path(__file__).parents[1] / "schemas" / "v0.1"
    for key, filename in (("binder_runs", "binder-runs.schema.json"), ("assay_results", "assay-results.schema.json")):
        schema = json.loads((schema_root / filename).read_text())
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.Draft202012Validator(schema).validate(load_json(paths[key]))


def test_optional_absence_and_malformed_collection(inputs):
    atlas, _ = inputs
    assert validate_optional_research(atlas, "synthetic-atlas") == []
    (atlas / "assay-results.json").write_text('{"schema_version":"incorrect"}')
    assert "requires valid strict" in validate_optional_research(atlas, "synthetic-atlas")[0]


def test_existing_reviewed_legacy_example_remains_valid():
    root = Path(__file__).parents[1] / "examples" / "research-case"
    assert validate_optional_research(root, "research-case-example") == []


def test_render_escapes_source_strings(inputs):
    _, paths = inputs
    value = load_json(paths["assay_results"])
    value["records"][0]["method"]["conditions"] = "<script>alert(1)</script>"
    rendered = render_assays(value)
    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered


def test_zero_and_missing_controls_are_preserved(inputs):
    _, paths = inputs
    runs, value = load_json(paths["binder_runs"]), load_json(paths["assay_results"])
    value["records"][0]["reading"].update(value=0, relation="=")
    value["records"][0].update(controls=None, control_gap="Synthetic unavailable control details")
    validate_assays(value, paths["assay_results"].parent, "synthetic-atlas", {"synthetic-target"}, runs)
    assert "= 0 nM" in render_assays(value)
    assert "unresolved" in render_assays(value)


def test_combined_dry_run_rejects_reused_construct_with_changed_identity(inputs):
    atlas, paths = inputs
    second = load_json(paths["binder_runs"])
    second["records"][0]["run_id"] = "synthetic-run-two"
    candidate = second["records"][0]["candidates"][0]
    candidate["sequence"] = "ACDEFA"
    candidate["sequence_sha256"] = hashlib.sha256(candidate["sequence"].encode()).hexdigest()
    other = paths["binder_runs"].with_name("other.json")
    other.write_text(json.dumps(second))
    with pytest.raises(IntakeError, match="construct_id reused"):
        import_binder_runs([paths["binder_runs"], other], atlas)


def test_lineage_cycles_rejected(inputs):
    _, paths = inputs
    value = load_json(paths["binder_runs"])
    run = value["records"][0]
    a, b = run["candidates"]
    for child, parent in ((a, b), (b, a)):
        child["lineage"] = [{"run_id": run["run_id"], "candidate_id": parent["candidate_id"], "sequence_sha256": parent["sequence_sha256"], "source": copy.deepcopy(parent["source"])}]
    with pytest.raises(IntakeError, match="cycle"):
        check_binders(value, paths)


@pytest.mark.parametrize("filename", ["binders.json", "binder-runs.json", "assay-results.json", "designs.json", "designs/nested.json"])
def test_optional_broken_symlink_is_not_silently_absent(inputs, filename):
    atlas, _ = inputs
    path = atlas / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.symlink_to(atlas / "nonexistent")
    assert validate_optional_research(atlas, "synthetic-atlas")


def test_nested_unregistered_legacy_record_rejected(inputs):
    atlas, _ = inputs
    directory = atlas / "designs"
    directory.mkdir()
    (directory / "unregistered.json").write_text(json.dumps({"candidate_id": "test", "sequence": "ACD"}))
    assert "register a recognized collection" in validate_optional_research(atlas, "synthetic-atlas")[0]


def test_malformed_types_raise_intake_error(inputs):
    _, paths = inputs
    value = load_json(paths["binder_runs"])
    value["records"][0]["target_id"] = []
    with pytest.raises(IntakeError, match="malformed"):
        check_binders(value, paths)


def test_synthetic_assay_cannot_be_relabelled_research(inputs):
    _, paths = inputs
    runs, value = load_json(paths["binder_runs"]), load_json(paths["assay_results"])
    value["data_status"] = "research"
    with pytest.raises(IntakeError, match="synthetic candidate"):
        validate_assays(value, paths["assay_results"].parent, "synthetic-atlas", {"synthetic-target"}, runs)


def test_complete_report_copies_and_links_intake_artifacts_after_source_removal(tmp_path, capsys):
    from surface_atlas.example import create_example
    from surface_atlas.report_builder import main as report_main
    from surface_atlas.validator import validate_workspace
    atlas = tmp_path / "full-atlas"
    create_example(atlas)
    atlas_id = load_json(atlas / "atlas-plan.json")["atlas_id"]
    target_id = load_json(atlas / "targets.json")["records"][0]["target_id"]
    paths = write_synthetic_research_inputs(tmp_path / "new-inputs", atlas_id, target_id)
    import_binder_runs([paths["binder_runs"]], atlas, tmp_path / "new-binders")
    shutil.copytree(tmp_path / "new-binders", atlas, dirs_exist_ok=True)
    import_assays(paths["assay_results"], atlas, tmp_path / "new-assays")
    shutil.copytree(tmp_path / "new-assays", atlas, dirs_exist_ok=True)
    shutil.rmtree(paths["binder_runs"].parent)
    assert validate_workspace(atlas)["valid"]
    output_root = tmp_path / "reports"
    assert report_main([str(atlas), "--output-root", str(output_root), "--run-id", "intake-e2e", "--json"]) == 0
    capsys.readouterr()
    report = output_root / atlas_id / "intake-e2e"
    data = load_json(report / "data" / "atlas.json")
    for path, copied in data["artifact_map"].items():
        assert (report / copied).read_bytes() == (atlas / path).read_bytes()
    class Links(HTMLParser):
        def __init__(self):
            super().__init__()
            self.hrefs = []
        def handle_starttag(self, tag, attrs):
            if tag == "a":
                self.hrefs.extend(value for key, value in attrs if key == "href")
    for page in ("campaigns.html", "assays.html"):
        rendered = (report / page).read_text()
        assert "SYNTHETIC TEST DATA" in rendered
        parser = Links()
        parser.feed(rendered)
        sources = [href for href in parser.hrefs if "research-artifacts/" in href]
        assert sources
        assert all((report / href).is_file() for href in sources)
        assert any(href.startswith("target-") for href in parser.hrefs)
    assert "Promoted candidates: 0" in (report / "campaigns.html").read_text()
    assert "not reported; no aggregate calculated" in (report / "assays.html").read_text()
    for filename in ("binder-runs.json", "assay-results.json"):
        assert load_json(report / "data" / filename)["data_status"] == "synthetic"
    # Report construction fails closed after a registered assay identity changes.
    assays = load_json(atlas / "assay-results.json")
    assays["records"][0]["candidate_construct"]["construct_id"] = "wrong"
    (atlas / "assay-results.json").write_text(json.dumps(assays))
    assert report_main([str(atlas), "--output-root", str(output_root), "--run-id", "must-not-publish"]) == 1
    assert not (output_root / atlas_id / "must-not-publish").exists()


def test_legacy_only_invalid_collection_blocks_report(tmp_path):
    from surface_atlas.example import create_example
    from surface_atlas.report_builder import main as report_main
    atlas = tmp_path / "legacy-atlas"
    create_example(atlas)
    (atlas / "binders.json").write_text("{broken")
    assert report_main([str(atlas), "--output-root", str(tmp_path / "reports"), "--run-id", "invalid-legacy"]) == 1


def test_untrusted_link_maps_cannot_inject_html(inputs):
    _, paths = inputs
    value = load_json(paths["binder_runs"])
    rendered = render_campaigns(value, {"synthetic-source.txt": 'javascript:alert(1)'}, {"synthetic-target": '//evil.example/path'})
    assert 'href="javascript:' not in rendered
    assert 'href="//evil' not in rendered


def test_artifact_link_special_characters_are_url_encoded(inputs):
    _, paths = inputs
    value = load_json(paths["binder_runs"])
    rendered = render_campaigns(value, {"synthetic-source.txt": "data/artifacts/file #1?.txt"})
    assert 'href="data/artifacts/file%20%231%3F.txt"' in rendered
